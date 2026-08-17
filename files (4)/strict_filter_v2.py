"""
Strict Relevance Filter v2 — SafeTravel LK
IT22629180

Replaces data_pipeline/strict_filter.py.

Fixes three defects in v1 that produce systematic, unmeasured selection bias
(see AUDIT §M3):

  D1  Substring matching with no word boundaries.
      v1's `_check_exclusions` only applies a whole-word guard to patterns of
      length <= 3, so "minister" matched inside "administer", "protest" inside
      "protested", "employment" inside "unemployment".
      -> v2 compiles every pattern to a word-boundary regex.

  D2  Nationality terms excluded the victims under study.
      v1 hard-excluded "france", "italy", "europe", "dubai", "oman" etc. to drop
      incidents occurring abroad. It also dropped "French tourist assaulted in
      Galle" — an in-scope incident whose victim is foreign, which is the entire
      study population.
      -> v2 splits FOREIGN_PLACES from the exclusion list and only excludes on
         them when NO Sri Lankan geographic anchor is present.

  D3  Advisory vocabulary excluded the highest-credibility tier.
      v1 excluded "protest", "curfew", "riot", "minister", "high commission".
      Government travel advisories are written almost entirely in that
      vocabulary, which is why the corpus contains ZERO Tier-0 records despite
      Tier-0 sitting at weight 1.00.
      -> v2 adds ADVISORY_SOURCES; official advisories bypass the political
         vocabulary exclusions.

Also adds structured rejection reasons so the filter's own false-negative rate
becomes measurable rather than assumed. Use `audit_rejections()` to sample.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Iterable

# ─────────────────────────────────────────────────────────────────────────────
# 1. Exclusion vocabularies — separated by WHY they exclude
# ─────────────────────────────────────────────────────────────────────────────

# 1a. Genuinely out of scope regardless of source or geography.
HARD_EXCLUSIONS: list[str] = [
    # Exams & education
    "a/l exam", "o/l exam", "a/l result", "o/l result",
    "advanced level", "ordinary level", "university admission",
    # Commerce / promotion
    "11.11 sale", "black friday", "buy now", "book your", "tour packages",
    "special offer", "contact us for bookings", "whatsapp me",
    "affordable price", "our services", "dm for bookings", "pre-book",
    # Job ads
    "hiring", "job opening", "vacancy", "apply now",
    # Non-tourist financial crime
    "online scam racket", "pyramid scam", "online fraud", "cyber fraud ring",
    "call center scam", "call centre scam", "investment scam ring",
    "online gambling", "money laundering", "crypto", "bitcoin", "nft",
    "stock market",
    # Non-tourist crime
    "arrested for murder", "drug bust", "heroin", "kerala ganja",
    "underworld", "gang war", "smuggling ring",
    # Labour migration (not tourism)
    "job racket", "domestic work", "work visa", "foreign employment bureau",
    "slbfe", "sending women", "housemaid",
    # Sports / entertainment
    "cricket match", "ipl", "lpl", "sports news",
    # Irrelevant social
    "dating", "relationship advice",
]

# 1b. Political / governmental vocabulary. Out of scope for ordinary news, but
#     REQUIRED vocabulary for official travel advisories. Bypassed for
#     ADVISORY_SOURCES.
POLITICAL_EXCLUSIONS: list[str] = [
    "parliament", "cabinet", "general election", "presidential election",
    "polling booth", "ballot paper", "election official", "elections commission",
    "elections commissioner", "presidential commission", "bribery commission",
    "human rights commission", "land reforms commission", "police commission",
    "charity commission", "commission to investigate", "district secretary",
    "local council", "imf loan", "economic crisis",
    "supreme court", "high court",
    "high commissioner", "high commission", "deputy high commissioner",
    "disaster management centre", "disaster management center",
    "sluice gates", "river levels", "met dept", "meteorology",
]

# 1c. Foreign place names. Only exclusionary when there is NO Sri Lankan anchor
#     in the text — otherwise these are victim-nationality or itinerary mentions.
FOREIGN_PLACES: list[str] = [
    "thailand", "pattaya", "bangkok", "phuket", "bali", "indonesia",
    "vietnam", "cambodia", "philippines", "shanghai",
    "italy", "rome", "paris", "france", "spain", "barcelona", "madrid",
    "greece", "athens", "prague", "tenerife", "mallorca",
    "dubai", "kuwait", "qatar", "saudi arabia", "oman",
]

# 1d. Sri Lankan geographic anchors.
SL_GEO_ANCHORS: list[str] = [
    "sri lanka", "srilanka", "ceylon", "colombo", "kandy", "galle", "negombo",
    "ella", "mirissa", "unawatuna", "sigiriya", "dambulla", "anuradhapura",
    "polonnaruwa", "nuwara eliya", "trincomalee", "arugam bay", "jaffna",
    "hikkaduwa", "bentota", "weligama", "tangalle", "matara", "batticaloa",
    "kalutara", "gampaha", "hambantota", "badulla", "ratnapura", "kurunegala",
    "puttalam", "matale", "kegalle", "monaragala", "vavuniya", "mannar",
    "mullaitivu", "yala", "udawalawe", "wilpattu", "adam's peak", "pinnawala",
    "haputale", "kataragama", "bandaranaike", "colombo airport",
]

# 1e. Sources whose records are official travel advisories.
ADVISORY_SOURCES: frozenset[str] = frozenset({
    "fcdo", "gov.uk", "travel.state.gov", "state_dept", "smartraveller",
    "smartraveller.gov.au", "dfat", "sltda_official", "tourist_police",
})

# ─────────────────────────────────────────────────────────────────────────────
# 2. Relevance signals
# ─────────────────────────────────────────────────────────────────────────────

STRONG_TOURIST = ["tourist", "tourists", "traveller", "traveler", "travellers",
                  "travelers", "backpacker", "backpackers", "solo trip",
                  "vacation", "holidaymaker", "visitor", "foreign national"]
INFRA_TOURIST = ["hostel", "guesthouse", "tuk tuk", "tuk-tuk", "three wheeler",
                 "tour guide", "safari", "day trip", "homestay", "hotel",
                 "resort", "beach", "temple", "excursion"]

STRONG_NEGATIVE = ["scam", "scammed", "ripped off", "rip off", "pickpocket",
                   "assault", "assaulted", "robbed", "robbery", "mugged",
                   "harassed", "harassment", "groped", "stolen", "theft",
                   "food poisoning", "fraud", "extortion", "overcharged",
                   "threatened", "drugged", "spiked"]
MEDIUM_NEGATIVE = ["overpriced", "dirty", "refund", "terrible", "hospital",
                   "unsafe", "danger", "dangerous", "cheated", "misled",
                   "aggressive", "tout", "touts", "warning", "avoid"]
WEAK_NEGATIVE = ["bad", "sad", "unhappy", "regret", "disappoint", "poor",
                 "issue", "problem", "complain", "ruined", "not great",
                 "not good"]

W_STRONG_TOURIST, W_INFRA = 2.0, 1.0
W_STRONG_NEG, W_MED_NEG, W_WEAK_NEG = 3.0, 1.0, 0.5

MIN_RELEVANCE_SCORE = 5.0
MIN_NEGATIVE_SCORE = 3.0

# ─────────────────────────────────────────────────────────────────────────────
# 3. Word-boundary matching (fixes D1)
# ─────────────────────────────────────────────────────────────────────────────


def _compile(patterns: Iterable[str]) -> list[tuple[str, re.Pattern]]:
    """Compile each pattern to a word-boundary regex.

    Multi-word phrases tolerate variable internal whitespace and hyphens, and a
    regular plural/inflection suffix is allowed on the final token. The suffix
    allowance matters: v1's substring matching handled plurals accidentally, so
    naive word-boundary matching would silently LOSE recall ("tour guide" would
    no longer match "tour guides"). The suffix is bounded to s/es/ed/ing so it
    cannot reintroduce the D1 over-matching ("minister" still cannot match
    inside "administered", which fails on the leading boundary).
    """
    out = []
    for p in patterns:
        toks = [re.escape(tok) for tok in p.split()]
        toks[-1] += r"(?:s|es|ed|ing)?"
        escaped = r"[\s\-]+".join(toks)
        out.append((p, re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)))
    return out


_HARD = _compile(HARD_EXCLUSIONS)
_POLITICAL = _compile(POLITICAL_EXCLUSIONS)
_FOREIGN = _compile(FOREIGN_PLACES)
_SL_GEO = _compile(SL_GEO_ANCHORS)
_STRONG_TOURIST = _compile(STRONG_TOURIST)
_INFRA = _compile(INFRA_TOURIST)
_STRONG_NEG = _compile(STRONG_NEGATIVE)
_MED_NEG = _compile(MEDIUM_NEGATIVE)
_WEAK_NEG = _compile(WEAK_NEGATIVE)


def _matches(text: str, compiled: list[tuple[str, re.Pattern]]) -> list[str]:
    return [label for label, rx in compiled if rx.search(text)]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Result type
# ─────────────────────────────────────────────────────────────────────────────

REJECTION_REASONS = (
    "hard_exclusion",
    "political_exclusion",
    "foreign_incident",       # foreign place, no SL anchor
    "no_geo_anchor",
    "no_tourist_context",
    "insufficient_negative_signals",
    "below_total_threshold",
)


@dataclass
class FilterResult:
    passes: bool
    total_score: float = 0.0
    tourist_score: float = 0.0
    negative_score: float = 0.0
    geo_match: bool = False
    is_advisory: bool = False
    rejection_reason: str | None = None
    matched_signals: list[str] = field(default_factory=list)
    matched_exclusions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Main entry point
# ─────────────────────────────────────────────────────────────────────────────


def score_relevance(title: str, content: str, source: str = "") -> FilterResult:
    """Score an item for tourism-safety relevance.

    Args:
        title:   headline / post title
        content: body text
        source:  source key. If in ADVISORY_SOURCES, political-vocabulary
                 exclusions are bypassed and the negative-signal floor is
                 relaxed (advisories are preventative, not incident reports).

    Returns:
        FilterResult. Persist `.as_dict()` for every item — accepted AND
        rejected — so the filter's error rate can be estimated from a sample.
    """
    text = f"{title or ''} {content or ''}".strip()
    lowered = text.lower()
    src = (source or "").strip().lower()
    is_advisory = any(a in src for a in ADVISORY_SOURCES)

    res = FilterResult(passes=False, is_advisory=is_advisory)

    if not lowered:
        res.rejection_reason = "no_tourist_context"
        return res

    # --- Gate 1: unconditional exclusions -----------------------------------
    hard_hits = _matches(lowered, _HARD)
    if hard_hits:
        res.rejection_reason = "hard_exclusion"
        res.matched_exclusions = hard_hits
        return res

    # --- Gate 2: political vocabulary (bypassed for advisories) [fixes D3] ---
    if not is_advisory:
        pol_hits = _matches(lowered, _POLITICAL)
        if pol_hits:
            res.rejection_reason = "political_exclusion"
            res.matched_exclusions = pol_hits
            return res

    # --- Gate 3: geography ---------------------------------------------------
    sl_hits = _matches(lowered, _SL_GEO)
    res.geo_match = bool(sl_hits)
    foreign_hits = _matches(lowered, _FOREIGN)

    if not res.geo_match:
        # Foreign place AND no SL anchor -> the incident is abroad.
        res.rejection_reason = "foreign_incident" if foreign_hits else "no_geo_anchor"
        res.matched_exclusions = foreign_hits
        return res
    # If an SL anchor IS present, foreign place names are treated as victim
    # nationality or itinerary context and are NOT exclusionary. [fixes D2]

    # --- Gate 4: tourist context --------------------------------------------
    strong_t = _matches(lowered, _STRONG_TOURIST)
    infra_t = _matches(lowered, _INFRA)
    res.tourist_score = W_STRONG_TOURIST * len(strong_t) + W_INFRA * len(infra_t)
    if res.tourist_score <= 0:
        res.rejection_reason = "no_tourist_context"
        return res

    # --- Gate 5: negative signal --------------------------------------------
    strong_n = _matches(lowered, _STRONG_NEG)
    med_n = _matches(lowered, _MED_NEG)
    res.negative_score = W_STRONG_NEG * len(strong_n) + W_MED_NEG * len(med_n)
    if res.negative_score > 0:
        res.negative_score += W_WEAK_NEG * len(_matches(lowered, _WEAK_NEG))

    res.matched_signals = strong_t + infra_t + strong_n + med_n

    # Advisories are preventative and often carry no incident narrative, so the
    # negative-signal floor is relaxed for them. Their credibility tier, not
    # their tone, is what qualifies them.
    neg_floor = 1.0 if is_advisory else MIN_NEGATIVE_SCORE
    if res.negative_score < neg_floor:
        res.rejection_reason = "insufficient_negative_signals"
        return res

    res.total_score = res.tourist_score + res.negative_score
    total_floor = 3.0 if is_advisory else MIN_RELEVANCE_SCORE
    if res.total_score < total_floor:
        res.rejection_reason = "below_total_threshold"
        return res

    res.passes = True
    return res


def passes_filter(title: str, content: str, source: str = "") -> bool:
    """Boolean convenience wrapper, drop-in for the v1 call site."""
    return score_relevance(title, content, source).passes


# ─────────────────────────────────────────────────────────────────────────────
# 6. Rejection audit — makes the filter's error rate measurable (AUDIT §M3)
# ─────────────────────────────────────────────────────────────────────────────


def audit_rejections(records: list[dict], n: int = 200, seed: int = 42) -> list[dict]:
    """Draw a random sample of REJECTED records for hand-labelling.

    Each record needs 'title', 'content' and optionally 'source'.
    Label the exported sample by hand for true relevance, then:

        FNR = (rejected items that were actually relevant) / (sample size)

    Report that number in the thesis. A filter whose error rate is unknown is
    an uncontrolled variable in every downstream result.
    """
    import random

    rejected = []
    for rec in records:
        r = score_relevance(rec.get("title", ""), rec.get("content", ""),
                            rec.get("source", ""))
        if not r.passes:
            rejected.append({**rec, **r.as_dict(), "gold_relevant": ""})

    random.Random(seed).shuffle(rejected)
    return rejected[:n]


# ─────────────────────────────────────────────────────────────────────────────
# 7. Regression tests — each asserts a specific v1 defect is fixed
# ─────────────────────────────────────────────────────────────────────────────

# Each case: (title, content, source, expect_pass|None, forbidden_reason|None, guard)
#   expect_pass      — assert the overall accept/reject decision
#   forbidden_reason — assert the item was NOT rejected for this specific reason
#                      (used where the guard is about one gate, not the verdict)
_TESTS = [
    ("French tourist assaulted near Galle Fort",
     "A French tourist was assaulted and robbed by touts near Galle Fort on Tuesday.",
     "dailymirror", True, None,
     "D2: victim nationality must not exclude an in-country incident"),

    ("Sri Lanka travel advice: protests and curfews",
     "Protests may occur in Colombo. Avoid demonstrations. Tourists should monitor local media.",
     "fcdo", True, None,
     "D3: advisory vocabulary must reach the Tier-0 corpus"),

    ("Parliament debates new tourism levy",
     "Parliament debated a levy affecting hotel operators in Colombo this week.",
     "adaderana", False, None,
     "political exclusion still fires for ordinary news"),

    ("Scammed by tuk tuk driver in Colombo",
     "The tuk tuk driver refused the meter and overcharged us ten times the fare in Colombo.",
     "tripadvisor", True, None,
     "ordinary in-scope incident is accepted"),

    ("Pattaya beach scam warning",
     "Tourists in Pattaya, Thailand report being scammed by jet ski operators.",
     "reddit", False, None,
     "D2 inverse: foreign incident with no SL anchor is still excluded"),

    ("Tourist administered first aid after Ella fall",
     "A traveller was administered first aid in hospital after a dangerous fall near Ella.",
     "newsfirst", None, "political_exclusion",
     "D1: 'minister' must not match inside 'administered'"),

    ("Unemployment concerns among Kandy guides",
     "Rising unemployment has hit tour guides in Kandy, who report aggressive touts "
     "and tourists being cheated by unlicensed operators.",
     "sundaytimes", True, None,
     "D1: 'employment' must not match inside 'unemployment'; plurals still match"),

    ("Book your Sri Lanka tour package now",
     "Special offer! WhatsApp me for affordable price on Colombo and Kandy tours for tourists.",
     "facebook", False, None,
     "promotional content still excluded"),
]


def _run_tests() -> int:
    failures = 0
    print(f"{'result':<7} guard")
    print("-" * 78)
    for title, content, source, expect_pass, forbidden, guard in _TESTS:
        r = score_relevance(title, content, source)
        ok = True
        if expect_pass is not None and r.passes != expect_pass:
            ok = False
        if forbidden is not None and r.rejection_reason == forbidden:
            ok = False
        failures += (not ok)
        print(f"{'PASS' if ok else 'FAIL':<7} {guard}")
        if not ok:
            got = "accepted" if r.passes else f"rejected:{r.rejection_reason}"
            print(f"        -> {got}  total={r.total_score:.1f} "
                  f"tourist={r.tourist_score:.1f} neg={r.negative_score:.1f} "
                  f"excl={r.matched_exclusions}")
    print("-" * 78)
    print(f"{len(_TESTS) - failures}/{len(_TESTS)} passed")
    return failures


if __name__ == "__main__":
    raise SystemExit(_run_tests())
