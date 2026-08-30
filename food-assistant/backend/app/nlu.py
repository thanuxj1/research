"""Query understanding.

This module turns a free-text query into a structured `AnalyzedQuery`: typo
corrections, negation-scoped facet constraints, a clean dense query, and an
expanded sparse token bag.

It exists because the previous /search handler inferred intent with bare
substring tests against the raw query, which produced inverted results for any
negated request:

    "I don't want seafood"  ->  'seafood' in query  ->  returned ONLY seafood
    "not vegetarian"        ->  'vegetarian' in query -> filtered TO vegetarian

Stdlib only, deliberately: the whole layer is unit-testable without the ML
stack installed.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .data.taxonomy import (
    CONJUNCTIONS,
    FACET_CATEGORY,
    FACET_DIET,
    FACET_MEAL,
    FACET_PRICE,
    FACET_SPICE,
    FACET_TAG,
    MAX_FILLER_SKIP,
    MAX_PHRASE_TOKENS,
    NEGATION_CUE_PHRASES,
    NEGATION_CUES,
    PHRASES_BY_LENGTH,
    PRICE_ORDER,
    SCOPE_BREAKERS,
    SPARSE_EXPANSIONS,
    SPICE_ORDER,
)

# Cues that negate the phrase *preceding* them ("gluten free", "nut allergy").
SUFFIX_NEGATION_CUES: frozenset[str] = frozenset(
    {"free", "allergy", "allergies", "allergic", "intolerance", "intolerant"}
)

STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "of", "for", "to", "in", "on", "at", "is", "are", "am",
        "be", "was", "were", "i", "me", "my", "we", "our", "you", "your", "it",
        "its", "this", "that", "these", "those", "and", "or", "as", "with",
        "some", "any", "what", "which", "who", "whom", "how", "when", "where",
        "want", "wants", "wanted", "like", "likes", "need", "needs", "looking",
        "look", "find", "show", "give", "get", "please", "would", "could",
        "should", "can", "will", "do", "does", "did", "have", "has", "had",
        "something", "anything", "there", "here", "s", "t", "m", "re", "ve",
        "ll", "d", "food", "foods", "dish", "dishes", "eat", "eating", "try",
        "good", "nice", "really", "very", "much", "more", "most", "also",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")

# ---------------------------------------------------------------------------
# Budget vocabulary
# ---------------------------------------------------------------------------
# Currency units a Sri Lankan user would actually type. `_normalize` has already
# stripped the punctuation, so "Rs." arrives as "rs" and "500/=" as "500".
CURRENCY_TOKENS: frozenset[str] = frozenset(
    {"rs", "rupees", "rupee", "lkr", "slr", "rupiya", "rupiyal"}
)

# Cues that put a *ceiling* on the price.
BUDGET_MAX_CUES: frozenset[str] = frozenset(
    {"under", "below", "less", "max", "maximum", "upto", "within", "cheaper",
     "atmost", "most", "up", "beneath", "underneath"}
)

# Cues that put a *floor* on the price.
BUDGET_MIN_CUES: frozenset[str] = frozenset(
    {"over", "above", "more", "least", "minimum", "min", "atleast", "exceeding",
     "beyond", "upwards"}
)

# Cues meaning "approximately", which imply a band on both sides.
BUDGET_AROUND_CUES: frozenset[str] = frozenset(
    {"around", "about", "approximately", "roughly", "circa", "ish", "approx"}
)

BUDGET_RANGE_CUES: frozenset[str] = frozenset({"between", "from"})

# Words that imply a ceiling without stating a comparator: "budget 1500" and
# "spend 800" are ceilings in every phrasing worth supporting. They stay in
# `BUDGET_FILLER` as well, and `_scan_budget_cue` checks cues before filler, so a
# nearer explicit comparator still wins - "budget of at least 2000" is a floor.
BUDGET_IMPLIED_MAX_CUES: frozenset[str] = frozenset(
    {"budget", "spend", "spending", "afford"}
)

# Tokens allowed to sit between a cue and its amount. "than" and "to" are the
# load-bearing ones: they are what makes "less than 500" and "up to 500" work.
BUDGET_FILLER: frozenset[str] = frozenset(
    {"than", "to", "of", "a", "an", "the", "is", "are", "be", "cost", "costs",
     "costing", "price", "priced", "prices", "for", "only", "just", "me", "spend",
     "spending", "pay", "paying", "budget", "worth"}
)

# How wide "around 500" is taken to be, each side.
BUDGET_AROUND_TOLERANCE = 0.25

# A dish price in LKR outside this range is not a budget - it is a year, a house
# number, or a quantity that happened to sit next to a currency word.
BUDGET_MIN_PLAUSIBLE = 10
BUDGET_MAX_PLAUSIBLE = 200_000
# Without an explicit currency word, require an amount large enough to be money:
# "less than 3 chillies" must not become a Rs 3 budget.
BUDGET_MIN_UNCUED = 20

_MONEY_SUFFIX_RE = re.compile(r"^(\d+)([a-z]+)$")
_MONEY_PREFIX_RE = re.compile(r"^([a-z]+)(\d+)$")

# Digit-group separators, removed while they are still visible. `_normalize`
# strips punctuation, and once "1,000" has become "1 000" no amount of guesswork
# downstream can tell it apart from "top 10 500". A plain space is deliberately
# not a separator for that reason; the non-breaking and thin spaces are, since
# they only turn up in a number pasted from already-formatted text.
_AMOUNT_SEPARATOR_RE = re.compile("(?<=\\d)[,\\u00a0\\u202f\\u2009](?=\\d)")
# "300-800 rupees" is rewritten to "from 300 to 800", which the range pass
# already understands. A hyphen between two numbers is a range in every query
# worth supporting, and the alternative - rejoining split digit groups by
# adjacency - silently turned it into Rs 300,800 and then discarded it as
# implausible.
_AMOUNT_RANGE_RE = re.compile(r"(?<!\d)(\d+)\s*[-–—]\s*(\d+)(?!\d)")

# Tokens that carry budget phrasing rather than dish content. Stripped before
# dish-name matching so "kottu under 600 rupees" still reads as a kottu lookup:
# left in, the four extra tokens dilute the content query enough to lose the
# name match entirely, and with it a bonus worth more than any other signal.
# Verified against the corpus - no dish name contains any of these words.
BUDGET_NOISE: frozenset[str] = (
    CURRENCY_TOKENS
    | BUDGET_MAX_CUES
    | BUDGET_MIN_CUES
    | BUDGET_AROUND_CUES
    | BUDGET_RANGE_CUES
    | BUDGET_IMPLIED_MAX_CUES
    | {"than"}
)

# Tokens that may sit between a negation cue and the phrase it governs.
# Conjunctions and scope breakers are excluded: they carry meaning for scoping
# and must be seen by `_is_negated`, not skipped over.
_SCOPE_FILLER: frozenset[str] = (STOPWORDS | {"much", "many", "too"}) - CONJUNCTIONS - SCOPE_BREAKERS


# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------
@dataclass
class Constraints:
    """Compiled, polarity-resolved constraints.

    `spice_floor`/`spice_ceiling` and the price equivalents are inclusive
    ordinal bounds on the taxonomy scales. Tag/category exclusions are split by
    the caller into hard filters (allergens) and soft penalties (preferences).
    """

    diet: str | None = None  # 'veg' | 'nonveg'
    spice_floor: int | None = None
    spice_ceiling: int | None = None
    price_floor: int | None = None
    price_ceiling: int | None = None
    # Numeric budget in LKR, parsed from phrasing like "under 500 rupees". Kept
    # separate from `price_floor`/`price_ceiling`: those are ordinals over the
    # dataset's Low/Medium/High column, which is an XGBoost feature and must not
    # be overloaded with rupee amounts. Both stay soft signals, so a stated
    # figure narrows the ranking without ever emptying the page.
    max_price_lkr: int | None = None
    min_price_lkr: int | None = None
    meal_times: set[str] = field(default_factory=set)
    categories_include: set[str] = field(default_factory=set)
    categories_exclude: set[str] = field(default_factory=set)
    tags_include: set[str] = field(default_factory=set)
    tags_exclude: set[str] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not any(
            (
                self.diet,
                self.spice_floor is not None,
                self.spice_ceiling is not None,
                self.price_floor is not None,
                self.price_ceiling is not None,
                self.max_price_lkr is not None,
                self.min_price_lkr is not None,
                self.meal_times,
                self.categories_include,
                self.categories_exclude,
                self.tags_include,
                self.tags_exclude,
            )
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "diet": self.diet,
            "spice_floor": self.spice_floor,
            "spice_ceiling": self.spice_ceiling,
            "price_floor": self.price_floor,
            "price_ceiling": self.price_ceiling,
            "max_price_lkr": self.max_price_lkr,
            "min_price_lkr": self.min_price_lkr,
            "meal_times": sorted(self.meal_times),
            "categories_include": sorted(self.categories_include),
            "categories_exclude": sorted(self.categories_exclude),
            "tags_include": sorted(self.tags_include),
            "tags_exclude": sorted(self.tags_exclude),
        }


@dataclass
class NameMatch:
    name: str
    kind: str  # 'exact' | 'partial' | 'fuzzy'
    score: float


@dataclass
class AnalyzedQuery:
    raw: str
    normalized: str
    corrected: str
    corrections: list[tuple[str, str]]
    tokens: list[str]
    negated_spans: list[str]
    matched_phrases: list[tuple[str, bool]]  # (phrase, negated)
    constraints: Constraints
    dense_query: str
    sparse_tokens: list[str]
    name_matches: list[NameMatch]
    # Readable echo of any amount found ("up to Rs 500"), so the UI can show what
    # it understood. A misread budget silently reshapes the results otherwise.
    budget_mentions: list[str] = field(default_factory=list)

    @property
    def is_lookup(self) -> bool:
        """True when the query looks like a specific dish lookup, not a browse."""
        return any(m.kind in ("exact", "fuzzy") for m in self.name_matches) or (
            bool(self.name_matches) and len(self.tokens) <= 4
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "raw": self.raw,
            "corrected": self.corrected,
            "corrections": [{"from": a, "to": b} for a, b in self.corrections],
            "matched_phrases": [
                {"phrase": p, "negated": n} for p, n in self.matched_phrases
            ],
            "negated_terms": self.negated_spans,
            "constraints": self.constraints.as_dict(),
            "budget": self.budget_mentions,
            "is_lookup": self.is_lookup,
            "name_matches": [
                {"name": m.name, "kind": m.kind, "score": round(m.score, 3)}
                for m in self.name_matches
            ],
            "sparse_terms": self.sparse_tokens,
        }


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------
class QueryAnalyzer:
    """Builds `AnalyzedQuery` objects. Construct once, reuse per request."""

    def __init__(
        self,
        dish_names: Sequence[str],
        extra_vocabulary: Iterable[str] = (),
        fuzzy_threshold: float = 0.82,
    ) -> None:
        self.dish_names = list(dish_names)
        self.fuzzy_threshold = fuzzy_threshold
        self._normalized_names = {name: _normalize(name) for name in self.dish_names}

        vocab: set[str] = set()
        for name in self.dish_names:
            vocab.update(_WORD_RE.findall(_normalize(name)))
        for phrase in _all_lexicon_phrases():
            vocab.update(phrase.split())
        for term in extra_vocabulary:
            vocab.update(_WORD_RE.findall(term.lower()))
        vocab -= {t for t in vocab if len(t) < 3}
        self.vocabulary = vocab
        # difflib wants a list; cache it rather than rebuilding per query.
        self._vocab_list = sorted(vocab)

    # -- public ------------------------------------------------------------
    def analyze(self, raw: str) -> AnalyzedQuery:
        normalized = _normalize(_normalize_amounts(raw))
        normalized = _canonicalize_cue_phrases(normalized)

        tokens = _WORD_RE.findall(normalized)
        tokens, corrections = self._correct(tokens)
        corrected = " ".join(tokens)

        spans = _scan_phrases(tokens)

        include: list[tuple[str, str]] = []
        exclude: list[tuple[str, str]] = []
        matched_phrases: list[tuple[str, bool]] = []
        negated_spans: list[str] = []
        negated_token_idx: set[int] = set()

        previous_negated = False
        for start, end, phrase, pairs in spans:
            negated = _is_negated(tokens, start, previous_negated) or _has_suffix_cue(
                tokens, end
            )
            previous_negated = negated
            matched_phrases.append((phrase, negated))
            if negated:
                exclude.extend(pairs)
                negated_spans.append(phrase)
                negated_token_idx.update(range(start, end))
            else:
                include.extend(pairs)

        constraints = _compile(include, exclude)
        max_lkr, min_lkr, budget_mentions = _parse_budget(tokens)
        constraints.max_price_lkr = max_lkr
        constraints.min_price_lkr = min_lkr

        return AnalyzedQuery(
            raw=raw,
            normalized=normalized,
            corrected=corrected,
            corrections=corrections,
            tokens=tokens,
            negated_spans=negated_spans,
            matched_phrases=matched_phrases,
            constraints=constraints,
            budget_mentions=budget_mentions,
            # The dense encoder receives clean natural language. Note that
            # bi-encoders handle negation poorly, which is precisely why the
            # constraint layer above exists to enforce it explicitly.
            dense_query=corrected if corrected else _normalize(raw),
            sparse_tokens=_build_sparse_bag(tokens, negated_token_idx, constraints),
            name_matches=self._match_names(normalized, tokens, negated_token_idx),
        )

    # -- internals ---------------------------------------------------------
    def _correct(self, tokens: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
        """Conservative spell correction against the corpus vocabulary."""
        out: list[str] = []
        corrections: list[tuple[str, str]] = []
        for token in tokens:
            if (
                len(token) < 4
                or token in self.vocabulary
                or token in STOPWORDS
                or token in NEGATION_CUES
                or token in CURRENCY_TOKENS
                # Anything containing a digit, not just a pure integer: the old
                # `isdigit()` test left "500lkr" and "1500rs" exposed to fuzzy
                # correction against dish names, which would destroy the amount.
                or any(char.isdigit() for char in token)
            ):
                out.append(token)
                continue
            candidates = difflib.get_close_matches(
                token, self._vocab_list, n=1, cutoff=self.fuzzy_threshold
            )
            if candidates and candidates[0] != token:
                corrections.append((token, candidates[0]))
                out.append(candidates[0])
            else:
                out.append(token)
        return out, corrections

    def _match_names(
        self,
        normalized_query: str,
        tokens: list[str],
        negated_idx: set[int] | None = None,
    ) -> list[NameMatch]:
        """Detect dish-name lookups: exact, containment, and fuzzy (typo) hits."""
        query = normalized_query.strip()
        if not query:
            return []
        negated = negated_idx or set()

        # Negated spans are blanked rather than deleted, so a dish name cannot be
        # matched *across* the hole. Without this, "no seafood kottu" contains the
        # literal phrase "seafood kottu" and Seafood Kottu earns a name bonus for
        # the one dish the user ruled out.
        positive_query = " ".join(
            "\x00" if i in negated else token for i, token in enumerate(tokens)
        )

        # Only content words survive here: a dish name never contains a stopword,
        # a negation cue, an amount, or budget phrasing (all verified against the
        # corpus), and leaving them in makes containment against the real name
        # fail - "kottu under 600 rupees" would lose its name match entirely.
        content = [
            t
            for i, t in enumerate(tokens)
            if i not in negated
            and t not in STOPWORDS
            and t not in BUDGET_NOISE
            and t not in NEGATION_CUES
            and not any(char.isdigit() for char in t)
        ]
        content_query = " ".join(content)
        matches: list[NameMatch] = []

        for name, norm_name in self._normalized_names.items():
            if not norm_name:
                continue
            if norm_name == query or norm_name == content_query:
                matches.append(NameMatch(name, "exact", 1.0))
                continue
            # Containment in either direction, but require the shorter side to be
            # substantial so single stopword-ish tokens don't match everything.
            # The full (positive) query is used for this direction because dish
            # names may themselves contain stopwords - "Rice and Curry".
            if len(norm_name) >= 4 and _contains_phrase(positive_query, norm_name):
                matches.append(NameMatch(name, "partial", 0.8))
                continue
            if len(content_query) >= 4 and _contains_phrase(norm_name, content_query):
                matches.append(NameMatch(name, "partial", 0.7))
                continue
            ratio = difflib.SequenceMatcher(None, content_query, norm_name).ratio()
            if ratio >= self.fuzzy_threshold:
                matches.append(NameMatch(name, "fuzzy", ratio))

        rank = {"exact": 3, "fuzzy": 2, "partial": 1}
        matches.sort(key=lambda m: (rank[m.kind], m.score), reverse=True)
        return matches[:8]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_CONTRACTION_FIXES: tuple[tuple[str, str], ...] = (
    ("can't", "cannot"),
    ("won't", "will not"),
    ("shan't", "shall not"),
)

# Generic negative contraction: doesn't / didn't / isn't / haven't / wouldn't ...
_NT_RE = re.compile(r"n't\b")


def _normalize(text: str) -> str:
    """Lowercase, expand negative contractions, strip punctuation, collapse space.

    Contractions must be expanded *before* punctuation is stripped. Otherwise
    "don't want seafood" becomes "don t want seafood", the negation cue is
    destroyed, and the query silently inverts into a request *for* seafood.

    `&` becomes "and" so the "Sauces & Sides" category is reachable by typing
    "sauces and sides".
    """
    lowered = text.lower().replace("\u2019", "'").replace("\u02bc", "'")
    for source, target in _CONTRACTION_FIXES:
        lowered = lowered.replace(source, target)
    lowered = _NT_RE.sub(" not", lowered)
    lowered = lowered.replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_amounts(text: str) -> str:
    """Repair written amounts *before* punctuation is stripped.

    Two rewrites, both of which are impossible once `_normalize` has run, because
    the character that distinguishes the cases is gone by then:

    * "1,000" -> "1000". Left alone, tokenisation yields ``["1", "000"]`` and the
      amount reads as Rs 1 - a 1000x error that silently returns only the
      cheapest dishes.
    * "300-800" -> "from 300 to 800", which the range pass already understands.

    Doing this here rather than rejoining adjacent digit groups downstream is
    what stops "top 10 500" becoming a Rs 10,500 budget.
    """
    text = _AMOUNT_SEPARATOR_RE.sub("", text)
    return _AMOUNT_RANGE_RE.sub(r"from \1 to \2", text)


def _canonicalize_cue_phrases(text: str) -> str:
    """Collapse multi-word negation cues to a single canonical cue token."""
    padded = f" {text} "
    for phrase, replacement in NEGATION_CUE_PHRASES:
        padded = padded.replace(f" {phrase} ", f" {replacement} ")
    return padded.strip()


def _is_negated(tokens: Sequence[str], start: int, previous_negated: bool) -> bool:
    """Is the facet phrase beginning at `start` inside a negation scope?

    Looks backwards from the phrase, skipping up to `MAX_FILLER_SKIP` filler
    tokens, and decides from the first meaningful token it finds:

      * negation cue      -> negated            ("without any *coconut*")
      * conjunction       -> inherit the previous phrase's polarity
                             ("no eggs or *dairy*" excludes both)
      * scope breaker     -> not negated        ("not spicy but *seafood*")
      * anything else     -> not negated

    This replaced a fixed 4-token window, which over-captured: in
    "not vegetarian dinner" the window reached past "vegetarian" and negated
    "dinner" as well, silently dropping the meal-time the user asked for.

    A cue token at the phrase's own start is not looked at, which is what lets
    the lexicon entry "non vegetarian" resolve to non-vegetarian instead of
    negating itself.
    """
    index = start - 1
    skipped = 0
    while index >= 0 and tokens[index] in _SCOPE_FILLER and skipped < MAX_FILLER_SKIP:
        index -= 1
        skipped += 1
    if index < 0:
        return False

    token = tokens[index]
    if token in SCOPE_BREAKERS:
        return False
    if token in NEGATION_CUES:
        return True
    if token in CONJUNCTIONS:
        return previous_negated
    return False


def _has_suffix_cue(tokens: Sequence[str], end: int) -> bool:
    """True for postfix negation like "gluten free" / "nut allergy"."""
    for j in (end, end + 1):
        if j < len(tokens) and tokens[j] in SUFFIX_NEGATION_CUES:
            return True
    return False


def _scan_phrases(
    tokens: Sequence[str],
) -> list[tuple[int, int, str, list[tuple[str, str]]]]:
    """Greedy longest-match phrase scan.

    Returns (start, end, phrase, pairs). Matched spans do not overlap, so
    "tea time" is consumed as one unit and the bare "tea" -> Drinks alias never
    gets a chance to fire on it.
    """
    results: list[tuple[int, int, str, list[tuple[str, str]]]] = []
    i = 0
    n = len(tokens)
    while i < n:
        matched = False
        max_len = min(MAX_PHRASE_TOKENS, n - i)
        for length, bucket in PHRASES_BY_LENGTH:
            if length > max_len:
                continue
            candidate = " ".join(tokens[i : i + length])
            pairs = bucket.get(candidate)
            if pairs is not None:
                results.append((i, i + length, candidate, list(pairs)))
                i += length
                matched = True
                break
        if not matched:
            i += 1
    return results


def _compile(
    include: Sequence[tuple[str, str]],
    exclude: Sequence[tuple[str, str]],
) -> Constraints:
    """Resolve (facet, value) polarity pairs into ordinal bounds and sets."""
    c = Constraints()

    inc_spice = [v for f, v in include if f == FACET_SPICE]
    exc_spice = [v for f, v in exclude if f == FACET_SPICE]
    floors: list[int] = []
    ceilings: list[int] = []
    for value in inc_spice:
        rank = SPICE_ORDER[value]
        if rank == 0:
            floors.append(0)
            ceilings.append(0)
        elif rank == 1:  # "mild" -> anything up to Low
            ceilings.append(1)
        elif rank == 2:  # "medium spice" -> target Medium
            floors.append(2)
            ceilings.append(2)
        else:  # spicy / very spicy -> at least Medium, prefer hotter
            floors.append(max(2, rank - 1))
    for value in exc_spice:
        rank = SPICE_ORDER[value]
        if rank >= 2:
            # "not spicy" / "no chili" -> cap at Low
            ceilings.append(1)
        else:
            # "not mild" -> want some heat
            floors.append(2)
    if ceilings:
        c.spice_ceiling = min(ceilings)
    if floors:
        c.spice_floor = max(floors)
    # A stated aversion to heat outranks a stated desire for it.
    if c.spice_floor is not None and c.spice_ceiling is not None and c.spice_floor > c.spice_ceiling:
        c.spice_floor = None

    inc_price = [v for f, v in include if f == FACET_PRICE]
    p_floors: list[int] = []
    p_ceilings: list[int] = []
    for value in inc_price:
        rank = PRICE_ORDER[value]
        if rank == 0:
            p_ceilings.append(0)
        elif rank == 1:
            p_floors.append(1)
            p_ceilings.append(1)
        else:
            p_floors.append(2)
    if p_ceilings:
        c.price_ceiling = min(p_ceilings)
    if p_floors:
        c.price_floor = max(p_floors)
    if c.price_floor is not None and c.price_ceiling is not None and c.price_floor > c.price_ceiling:
        c.price_floor = None

    inc_diet = {v for f, v in include if f == FACET_DIET}
    exc_diet = {v for f, v in exclude if f == FACET_DIET}
    if exc_diet:
        # "no meat" -> veg ; "not vegetarian" -> nonveg
        if "nonveg" in exc_diet:
            c.diet = "veg"
        elif "veg" in exc_diet:
            c.diet = "nonveg"
    elif len(inc_diet) == 1:
        c.diet = next(iter(inc_diet))
    # Contradictory diet mentions leave the facet unconstrained rather than
    # guessing.

    c.meal_times = {v for f, v in include if f == FACET_MEAL}
    c.categories_include = {v for f, v in include if f == FACET_CATEGORY}
    c.categories_exclude = {v for f, v in exclude if f == FACET_CATEGORY}
    c.tags_include = {v for f, v in include if f == FACET_TAG}
    c.tags_exclude = {v for f, v in exclude if f == FACET_TAG}
    # An explicit exclusion always wins over an incidental inclusion.
    c.tags_include -= c.tags_exclude
    c.categories_include -= c.categories_exclude
    return c


def _build_sparse_bag(
    tokens: Sequence[str],
    negated_idx: set[int],
    constraints: Constraints,
) -> list[str]:
    """Token bag for BM25.

    Negated spans are dropped: BM25 is purely lexical, so leaving "seafood" in
    the bag for "no seafood" would actively retrieve the excluded dishes. Their
    synonym expansions are dropped with them.
    """
    bag: list[str] = []
    for i, token in enumerate(tokens):
        if i in negated_idx or token in STOPWORDS or token in NEGATION_CUES:
            continue
        # Amounts and currency units are dropped: no dish name or description
        # contains "500" or "rupees", so they can only ever add noise to BM25.
        if token in CURRENCY_TOKENS or any(char.isdigit() for char in token):
            continue
        bag.append(token)
        for expansion in SPARSE_EXPANSIONS.get(token, ()):
            bag.append(expansion)

    for category in constraints.categories_include:
        bag.extend(_WORD_RE.findall(category.lower()))
    for tag in constraints.tags_include:
        bag.extend(tag.split("_"))

    seen: set[str] = set()
    ordered: list[str] = []
    for token in bag:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def _contains_phrase(haystack: str, needle: str) -> bool:
    """Whole-word containment, so "tea" does not match "instead"."""
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


# ---------------------------------------------------------------------------
# Budget parsing
# ---------------------------------------------------------------------------
def _merge_money_tokens(tokens: Sequence[str]) -> list[str]:
    """Split an amount away from a unit written flush against it.

    `[a-z0-9]+` keeps "500lkr" and "rs500" as single tokens, so the amount and
    its unit are separated here.

    Thousands separators are *not* repaired at this stage. They were, by
    rejoining adjacent 3-digit groups, and that could not distinguish "1,000"
    from "top 10 500" or from the "300-800" of a hyphenated range - by the time a
    token list exists, the character that told them apart has been stripped.
    `_normalize_amounts` handles it on the raw text instead.
    """
    out: list[str] = []
    for token in tokens:
        suffix = _MONEY_SUFFIX_RE.match(token)
        if suffix and suffix.group(2) in CURRENCY_TOKENS:
            out.extend([suffix.group(1), suffix.group(2)])
            continue
        prefix = _MONEY_PREFIX_RE.match(token)
        if prefix and prefix.group(1) in CURRENCY_TOKENS:
            out.extend([prefix.group(1), prefix.group(2)])
            continue
        out.append(token)
    return out


def _currency_near(tokens: Sequence[str], index: int) -> bool:
    """Is there a currency word immediately around this amount?

    The forward walk stops at another number. Without that, the "rupees" in
    "top 10 500 rupees" is within reach of the 10 as well as the 500, and the
    query lands on a Rs 10 ceiling - the most restrictive bound wins, so the
    wrong reading is the one that survives.
    """
    if index > 0 and tokens[index - 1] in CURRENCY_TOKENS:
        return True
    for j in range(index + 1, min(index + 3, len(tokens))):
        if tokens[j] in CURRENCY_TOKENS:
            return True
        if tokens[j].isdigit():
            break
    return False


def _scan_budget_cue(tokens: Sequence[str], index: int) -> tuple[str | None, bool]:
    """The comparator governing the amount at `index`, and whether it is negated.

    Looks backwards first, skipping `BUDGET_FILLER`, then forwards for trailing
    forms like "500 max" and "Rs 500 or less".

    The negation check is what makes "no more than 500" work. "more" is a
    *minimum* cue, so read literally that phrase would set a Rs 500 floor and
    return exactly the dishes the user was trying to avoid. A negation cue in
    front of the comparator flips its direction instead.
    """
    kind: str | None = None
    negated = False

    # Backwards.
    j = index - 1
    skipped = 0
    while j >= 0 and skipped <= MAX_FILLER_SKIP:
        token = tokens[j]
        if token in BUDGET_MAX_CUES:
            kind = "max"
            break
        if token in BUDGET_MIN_CUES:
            kind = "min"
            break
        if token in BUDGET_AROUND_CUES:
            kind = "around"
            break
        if token in BUDGET_RANGE_CUES:
            kind = "range"
            break
        if token in BUDGET_IMPLIED_MAX_CUES:
            # Checked after the explicit comparators, and only reached when none
            # of them sits nearer the amount, so "budget of at least 2000" is
            # still a floor.
            kind = "max"
            break
        if token in BUDGET_FILLER or token in CURRENCY_TOKENS:
            j -= 1
            skipped += 1
            continue
        break

    if kind is not None:
        # Keep walking back past the cue for a negation.
        k = j - 1
        steps = 0
        while k >= 0 and steps <= MAX_FILLER_SKIP:
            token = tokens[k]
            if token in NEGATION_CUES:
                negated = True
                break
            if token in BUDGET_FILLER or token in BUDGET_MAX_CUES or token in BUDGET_MIN_CUES:
                k -= 1
                steps += 1
                continue
            break
        return kind, negated

    # Forwards, for "500 max" / "500 rupees or less".
    j = index + 1
    skipped = 0
    while j < len(tokens) and skipped <= MAX_FILLER_SKIP:
        token = tokens[j]
        if token in BUDGET_MAX_CUES:
            return "max", False
        if token in BUDGET_MIN_CUES:
            return "min", False
        if token in CURRENCY_TOKENS or token in BUDGET_FILLER or token in CONJUNCTIONS:
            j += 1
            skipped += 1
            continue
        break

    return None, False


def _parse_budget(tokens: Sequence[str]) -> tuple[int | None, int | None, list[str]]:
    """Numeric budget bounds in LKR, plus human-readable mentions.

    Returns `(max_lkr, min_lkr, mentions)`. Where several bounds are stated the
    most restrictive wins, so "under 800, ideally under 500" lands on 500.

    A bare amount with a currency word and no comparator ("kottu for 500 rupees")
    is read as a ceiling: users state what they are willing to spend far more
    often than what they insist on spending.
    """
    merged = _merge_money_tokens(tokens)
    maxima: list[int] = []
    minima: list[int] = []
    mentions: list[str] = []
    consumed: set[int] = set()

    # Ranges first: "between 300 and 800" needs both numbers at once, and the
    # single-amount pass below would otherwise read only the first.
    for index, token in enumerate(merged):
        if token not in BUDGET_RANGE_CUES:
            continue
        found: list[tuple[int, int]] = []
        for j in range(index + 1, min(index + 7, len(merged))):
            if merged[j].isdigit():
                value = int(merged[j])
                if BUDGET_MIN_PLAUSIBLE <= value <= BUDGET_MAX_PLAUSIBLE:
                    found.append((j, value))
            if len(found) == 2:
                break
        if len(found) == 2:
            low, high = sorted(value for _j, value in found)
            minima.append(low)
            maxima.append(high)
            mentions.append(f"between Rs {low:,} and Rs {high:,}")
            consumed.update(j for j, _value in found)

    for index, token in enumerate(merged):
        if index in consumed or not token.isdigit():
            continue
        value = int(token)
        if not (BUDGET_MIN_PLAUSIBLE <= value <= BUDGET_MAX_PLAUSIBLE):
            continue

        currency = _currency_near(merged, index)
        kind, negated = _scan_budget_cue(merged, index)
        if kind is None and not currency:
            continue
        if not currency and value < BUDGET_MIN_UNCUED:
            continue

        if negated and kind == "max":
            kind = "min"
        elif negated and kind == "min":
            kind = "max"

        if kind == "min":
            minima.append(value)
            mentions.append(f"at least Rs {value:,}")
        elif kind == "around":
            low = int(value * (1 - BUDGET_AROUND_TOLERANCE))
            high = int(value * (1 + BUDGET_AROUND_TOLERANCE))
            minima.append(low)
            maxima.append(high)
            mentions.append(f"around Rs {value:,}")
        else:
            # 'max', 'range' with only one number found, or a bare amount.
            maxima.append(value)
            mentions.append(f"up to Rs {value:,}")

    max_lkr = min(maxima) if maxima else None
    min_lkr = max(minima) if minima else None
    # A contradictory pair ("over 900 under 400") leaves the floor off rather
    # than producing a band nothing can satisfy - the same resolution the spice
    # and price ordinals use.
    if max_lkr is not None and min_lkr is not None and min_lkr > max_lkr:
        min_lkr = None
    return max_lkr, min_lkr, mentions


def _all_lexicon_phrases() -> Iterable[str]:
    for _, bucket in PHRASES_BY_LENGTH:
        yield from bucket.keys()
