"""
Strict Relevance Filter — SafeTravel LK Research Engine
IT22629180

Every report MUST pass this filter before being stored.
Criteria:
  1. Must NOT match hard exclusion patterns
  2. Must explicitly mention Sri Lanka geography
  3. Must be in a TOURIST context (visitor/traveller perspective)
  4. Must contain a strong NEGATIVE EXPERIENCE signal
  5. Must achieve a minimum RELEVANCE SCORE (prevents marginal/ambiguous records)

Scoring approach prevents false positives from broad single-word matches
like "bad", "problem", "issue" which previously let irrelevant data through.
"""

# ── 1. HARD EXCLUSION PATTERNS ──────────────────────────────────────────────
# These disqualify an item immediately regardless of other signals.
HARD_EXCLUSIONS = [
    # Exams & Education
    "a/l exam", "o/l exam", "a/l result", "o/l result",
    "advanced level", "ordinary level", "university admission",
    # Commerce
    "11.11 sale", "black friday", "buy now",
    # Politics & Government
    "parliament", "president rajapaksa", "gotabaya", "ranil", "anura",
    "imf loan", "economic crisis", "protest", "riot", "tear gas", "curfew",
    "tamil eelam", "tamilawareness", "justicefor", "srilankapolitics",
    "general election", "presidential election", "cabinet", "minister",
    "supreme court", "high court",
    # Criminal non-tourist activity
    "arrested for murder", "drug bust", "heroin", "ganja", "cannabis",
    "smuggling", "kerala ganja", "underworld", "gang war", "shooting",
    # Sports & Entertainment
    "cricket match", "ipl", "lpl", "sports news",
    # Irrelevant social
    "dating", "relationship advice", "girlfriend", "boyfriend",
    # Finance / crypto
    "crypto", "bitcoin", "stock market", "nft",
    # Job ads / tour promotions
    "hiring", "job opening", "vacancy", "apply now",
    "book your", "tour packages", "special offer", "contact us for bookings",
    "whatsapp me", "affordable price", "our services", "dm for bookings",
    "pre-book", "whatsapp link",
    # Cybercrime / financial fraud (NOT tourist scams)
    "online scam racket", "pyramid scam", "online fraud", "cyber fraud ring",
    "call center scam", "investment scam ring", "online gambling",
    "money laundering", "financial crime",
    # Police arrests of non-tourists
    "foreign nationals arrested", "foreigners arrested",
    "racket busted", "arrested for online", "arrested for fraud",
    "nationals arrested", "chinese nationals", "indian nationals",
    "suspects arrested", "suspects detained", "police raid", "special raid",
    "cid arrested",
    # Immigration/visa issues (not tourist safety)
    "residing in", "on visa", "overstaying", "illegal stay",
    # Government / diplomatic noise
    "high commissioner", "high commission", "deputy high commissioner",
    "land reforms commission", "elections commissioner", "elections commission",
    "presidential commission", "bribery commission", "human rights commission",
    "police commission", "cabinet sub committee", "french embassy",
    "un high commissioner", "charity commission", "commission to investigate",
    "commissioner of", "lrc director", "election official", "polling booth",
    "ballot paper", "annulled as a group", "district secretary", "local council",
    # Weather / disaster (non-safety for tourists)
    "disaster management", "affected by floods", "heavy showers", "met dept",
    "meteorology", "sluice gates", "evacuation drills", "river levels",
    "dmc reported", "disaster management center", "disaster management centre",
    "port agreement", "haj pilgrimage",
    # Other countries (not Sri Lanka)
    "thailand", "pattaya", "bangkok", "phuket", "bali", "indonesia",
    "europe", "italy", "rome", "paris", "france", "spain", "barcelona",
    "madrid", "tenerife", "mallorca", "greece", "athens", "prague",
    "shanghai", "vietnam", "cambodia", "philippines",
    "dubai", "kuwait", "qatar", "saudi arabia", "oman", "middle east",
    # Labour migration (not tourist experiences)
    "employment", "job racket", "domestic work", "work visa", "sending women",
]

# ── 2. GEOGRAPHIC GATE — Sri Lanka must be explicitly mentioned ──────────────
SL_GEOGRAPHY = [
    "sri lanka", "lankan", "srilanka",
    # Major cities & destinations
    "colombo", "kandy", "galle", "ella", "sigiriya", "negombo",
    "mirissa", "hikkaduwa", "unawatuna", "nuwara eliya", "arugam bay",
    "arugam", "bentota", "jaffna", "dambulla", "polonnaruwa",
    "trincomalee", "pinnawala", "yala", "weligama", "tangalle",
    "anuradhapura", "haputale", "badulla", "matara", "mount lavinia",
    "pettah", "fort colombo", "katunayake", "bandaranaike",
    # Cultural references unique to Sri Lanka
    "ceylon", "serendib",
]

# ── 3. STRONG TOURIST CONTEXT SIGNALS ────────────────────────────────────────
# These clearly establish the person is a visitor/tourist.
# Weighted higher — each match adds +2 to relevance score.
STRONG_TOURIST_SIGNALS = [
    "tourist", "tourists", "tourism", "traveler", "traveller",
    "traveling", "travelling", "travel to", "travel in",
    "backpacker", "backpacking", "solo travel", "solo trip",
    "vacation", "holiday",
    "trip to sri lanka", "trip to colombo", "trip to kandy",
    "visited sri lanka", "visiting sri lanka",
    "my visit", "our visit", "first visit",
    "solo female", "female traveller", "female traveler",
    "as a tourist", "as tourists", "fellow tourists",
    "foreigner", "foreigners", "expat traveler",
]

# ── 4. TOURISM INFRASTRUCTURE SIGNALS ────────────────────────────────────────
# Establishes tourist context through venues/services used.
# Each match adds +1 to relevance score.
TOURIST_INFRASTRUCTURE = [
    "hostel", "guesthouse", "guest house", "hotel in", "stayed at", "accommodation",
    "tuk tuk", "tuk-tuk", "three-wheeler", "tuktuk",
    "tour guide", "tour operator", "guided tour", "guided tour",
    "sightseeing", "itinerary", "day trip", "cultural triangle",
    "safari", "surf", "surfing", "diving", "snorkeling", "whale watching",
    "airport taxi", "airport transfer",
    "booking.com", "airbnb", "hostelworld", "tripadvisor review",
    "visa on arrival", "tourist visa",
]

# ── 5. HIGH-WEIGHT NEGATIVE SIGNALS ──────────────────────────────────────────
# Specific, unambiguous negative tourist experiences.
# Each match adds +3 to relevance score (strongest evidence).
HIGH_WEIGHT_NEGATIVES = [
    # Scams
    "scam", "scammed", "scamming", "fraud", "fraudulent",
    "ripped off", "rip off", "ripoff", "swindle", "swindled",
    "overcharged", "tourist price", "double price", "inflated price",
    "gem scam", "gem shop scam", "fake guide", "commission shop",
    "tuk tuk scam", "taxi scam", "airport scam",
    "refused meter", "no meter",
    "bait and switch", "not as advertised", "fake monk",
    "cheated", "deceived",
    # Theft & Crime
    "pickpocket", "pickpocketed", "mugged", "robbery", "robbed",
    "stolen", "theft", "bag snatched", "phone stolen",
    # Physical danger
    "attacked", "assault", "harassed", "harassment", "stalked",
    "threatened", "unsafe", "dangerous",
    # Health incidents
    "food poisoning", "drugged", "spiked drink",
    # Specific warnings
    "avoid", "beware", "watch out", "don't trust", "do not trust",
    "stay away", "tourist warning", "travel warning", "travel advisory",
]

# ── 6. MEDIUM-WEIGHT NEGATIVE SIGNALS ─────────────────────────────────────────
# General negative experiences — need supporting context to count.
# Each match adds +1 to relevance score.
MEDIUM_WEIGHT_NEGATIVES = [
    "overpriced", "charged extra", "fake", "counterfeit", "forged", "bogus",
    "con", "dirty", "cockroach", "bed bugs",
    "refund", "no refund", "wouldn't refund",
    "lied", "false advertising",
    "injury", "accident", "hospital", "sick",
    "uncomfortable", "followed", "rude", "aggressive",
    "terrible", "awful", "nightmare", "worst", "horrible",
    "disgusting", "outrageous", "shocking",
    "stray dog", "bitten", "rabies",
    "delay", "cancel", "scary", "frighten", "creepy",
    "police report", "reported to police",
]

# ── 7. WEAK / AMBIGUOUS NEGATIVE SIGNALS ──────────────────────────────────────
# These alone are NOT sufficient. Must appear alongside stronger signals.
# Each match adds +0.5 to relevance score only when combined with other signals.
WEAK_NEGATIVES = [
    "bad", "sad", "unhappy", "regret", "disappoint",
    "poor", "issue", "problem", "complain",
    "ruined", "ill", "not great", "not good",
]

# ── MINIMUM RELEVANCE THRESHOLDS ──────────────────────────────────────────────
MIN_RELEVANCE_SCORE = 5.0   # Must reach this to be stored
MIN_NEGATIVE_SCORE = 3.0    # Must have at least this much from negative signals alone


def _check_exclusions(text: str) -> bool:
    """Returns True if text should be EXCLUDED (fails hard exclusion check)."""
    for excl in HARD_EXCLUSIONS:
        if excl in text:
            if len(excl) <= 3:
                # Short patterns: only match as whole word to avoid 'uk' in 'tuk-tuk'
                if f" {excl} " in f" {text} " or text.startswith(excl + " ") or text.endswith(" " + excl):
                    return True
            else:
                return True
    return False


def score_relevance(title: str, content: str) -> dict:
    """
    Returns a detailed relevance scoring dict.
    Use this for debugging / audit logs.

    Returns:
        {
            "passes": bool,
            "total_score": float,
            "negative_score": float,
            "tourist_score": float,
            "geo_match": bool,
            "excluded": bool,
            "matched_signals": list[str],
            "rejection_reason": str | None,
        }
    """
    text = f"{title} {content}".lower().strip()

    result = {
        "passes": False,
        "total_score": 0.0,
        "negative_score": 0.0,
        "tourist_score": 0.0,
        "geo_match": False,
        "excluded": False,
        "matched_signals": [],
        "rejection_reason": None,
    }

    # Step 1: Hard exclusion
    if _check_exclusions(text):
        result["excluded"] = True
        result["rejection_reason"] = "hard_exclusion"
        return result

    # Step 2: Geographic gate — must mention Sri Lanka
    if not any(geo in text for geo in SL_GEOGRAPHY):
        result["rejection_reason"] = "no_sri_lanka_geography"
        return result
    result["geo_match"] = True

    # Step 3: Score tourist context
    tourist_score = 0.0
    for sig in STRONG_TOURIST_SIGNALS:
        if sig in text:
            tourist_score += 2.0
            result["matched_signals"].append(f"[TOURIST+2] {sig}")
    for sig in TOURIST_INFRASTRUCTURE:
        if sig in text:
            tourist_score += 1.0
            result["matched_signals"].append(f"[INFRA+1] {sig}")
    result["tourist_score"] = tourist_score

    # Step 4: Score negative signals
    negative_score = 0.0
    for sig in HIGH_WEIGHT_NEGATIVES:
        if sig in text:
            negative_score += 3.0
            result["matched_signals"].append(f"[NEG+3] {sig}")
    for sig in MEDIUM_WEIGHT_NEGATIVES:
        if sig in text:
            negative_score += 1.0
            result["matched_signals"].append(f"[NEG+1] {sig}")
    # Weak negatives only contribute if there's already some negative score
    if negative_score > 0:
        for sig in WEAK_NEGATIVES:
            if sig in text:
                negative_score += 0.5
                result["matched_signals"].append(f"[NEG+0.5] {sig}")
    result["negative_score"] = negative_score

    # Step 5: Total score
    total_score = tourist_score + negative_score
    result["total_score"] = total_score

    # Step 6: Decision
    if tourist_score == 0:
        result["rejection_reason"] = "no_tourist_context"
        return result
    if negative_score < MIN_NEGATIVE_SCORE:
        result["rejection_reason"] = f"insufficient_negative_signals (score={negative_score:.1f}, min={MIN_NEGATIVE_SCORE})"
        return result
    if total_score < MIN_RELEVANCE_SCORE:
        result["rejection_reason"] = f"low_total_relevance_score (score={total_score:.1f}, min={MIN_RELEVANCE_SCORE})"
        return result

    result["passes"] = True
    return result


def passes_strict_filter(title: str, content: str) -> bool:
    """
    Returns True only if the item is:
      - NOT on the hard exclusion list
      - Explicitly about SRI LANKA (geographic gate)
      - Has a TOURIST context (strong or infrastructure signals)
      - Has sufficient NEGATIVE EXPERIENCE signals (scored)
      - Achieves minimum RELEVANCE SCORE (prevents marginal matches)
    """
    return score_relevance(title, content)["passes"]
