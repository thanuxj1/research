"""Stage 4: constraint enforcement and additive signal scoring.

Replaces the original chain of multiplicative fudge factors:

    if 'street food' in query_lower:  fused *= 0.3
    if want_dessert and not is_dessert: fused *= 0.2
    if want_beverage: fused *= (2.0 if is_drink else 0.15)
    ...

Three problems with multiplying:

1. **Signals annihilate.** Three independent mild penalties multiply to
   0.3 * 0.15 * 0.1 = 0.0045, a 200x cut. Nothing in the design intended that.
2. **Nothing is attributable.** Given a final score there is no way to recover
   which factor moved it, so the ranking cannot be explained or debugged.
3. **Order-of-magnitude sensitivity.** A `* 2.0` boost and a `* 0.15` penalty are
   not comparable quantities, so tuning one silently rescales the others.

Here, relevance is normalised to [0, 1] and every signal contributes a bounded
*additive* term. The result is monotonic in each signal, tunable per weight, and
returns its own breakdown - the API can show the user exactly why a dish ranked
where it did.

Hard constraints are handled separately, by removing documents rather than
scoring them down. An allergen exclusion is a safety requirement, not a
preference, and no amount of relevance should be able to outweigh it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from . import health
from .config import ScoringSettings
from .corpus import Dish
from .data.taxonomy import ALLERGEN_TAGS, MEAL_TIMES, SPICE_LEVELS, tag_label
from .nlu import Constraints

_ALL_MEALS = frozenset(MEAL_TIMES)


@dataclass
class Signal:
    """One additive contribution to a dish's final score."""

    name: str
    contribution: float
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "contribution": round(self.contribution, 4),
            "detail": self.detail,
        }


@dataclass
class ScoredDish:
    dish: Dish
    score: float
    relevance: float
    signals: list[Signal] = field(default_factory=list)
    warnings: list[health.Warning] = field(default_factory=list)
    health_severity: str | None = None
    rerank_score: float | None = None
    dense_score: float | None = None
    sparse_score: float | None = None
    retrievers: tuple[str, ...] = ()

    def as_dict(
        self, include_explanation: bool = False, price: object | None = None
    ) -> dict[str, object]:
        payload: dict[str, object] = self.dish.public_dict(price)
        payload["score"] = round(self.score, 4)
        payload["warnings"] = [w.as_dict() for w in self.warnings]
        payload["health_severity"] = self.health_severity
        if include_explanation:
            payload["explanation"] = {
                "relevance": round(self.relevance, 4),
                "rerank_score": None if self.rerank_score is None else round(self.rerank_score, 4),
                "dense_score": None if self.dense_score is None else round(self.dense_score, 4),
                "sparse_score": None if self.sparse_score is None else round(self.sparse_score, 4),
                "retrievers": list(self.retrievers),
                "signals": [s.as_dict() for s in self.signals],
            }
        return payload


@dataclass
class FilterReport:
    """Which hard filters ran, and what they cost."""

    applied: list[str] = field(default_factory=list)
    removed: int = 0
    relaxed: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {"applied": self.applied, "removed": self.removed, "relaxed": self.relaxed}


# ---------------------------------------------------------------------------
# Hard filters
# ---------------------------------------------------------------------------
# Decisive intents ("show me drinks", "not spicy") are enforced as filters rather
# than boosts, but only while at least this many dishes survive - so a narrow
# query degrades to ranking instead of returning an empty page.
MIN_SURVIVORS = 3


def allowed_indices(
    dishes: Sequence[Dish],
    constraints: Constraints,
    strict_allergens: Sequence[str] = (),
) -> tuple[set[int], FilterReport]:
    """Indices that satisfy every hard constraint.

    Hard:
      * allergen tags the user excluded in the query ("no seafood")
      * allergen tags implied by a health profile in strict mode
      * a stated diet, either direction, when enough dishes survive
      * a stated spice band, when enough dishes survive
      * a single decisive category intent, when enough dishes survive

    Soft (scored, not filtered): meal time, price, tag preferences, non-allergen
    exclusions, and category when the decisive-intent test does not apply.

    Diet and spice are hard because they are the attributes users state most
    firmly, and because a soft penalty provably loses to the relevance term.
    Bi-encoders represent negation poorly - "not vegetarian" embeds close to
    "vegetarian" - so for that query the retriever actively ranks vegetarian
    dishes highest, and a -0.30 penalty cannot close a +0.60 relevance gap. The
    same held for "not spicy" surfacing High-spice dishes. Enforcing these two as
    filters is what makes negation actually work end to end.

    Every hard filter except the allergen ones is guarded by `MIN_SURVIVORS`, so a
    narrow request degrades to ranking rather than to an empty page. Allergen
    filters are never relaxed: returning nothing is the correct answer when
    everything available is unsafe.
    """
    report = FilterReport()
    survivors = set(range(len(dishes)))

    hard_tags = set(strict_allergens) | (constraints.tags_exclude & ALLERGEN_TAGS)
    if hard_tags:
        survivors = {i for i in survivors if not (dishes[i].tags & hard_tags)}
        report.applied.append(
            "excludes " + ", ".join(tag_label(t) for t in sorted(hard_tags))
        )

    if constraints.diet is not None:
        wants_veg = constraints.diet == "veg"
        candidate = {i for i in survivors if dishes[i].is_veg == wants_veg}
        label = "vegetarian only" if wants_veg else "non-vegetarian only"
        if len(candidate) >= MIN_SURVIVORS:
            survivors = candidate
            report.applied.append(label)
        else:
            report.relaxed.append(f"{label} (too few matches)")

    if constraints.spice_floor is not None or constraints.spice_ceiling is not None:
        floor = 0 if constraints.spice_floor is None else constraints.spice_floor
        ceiling = (
            len(SPICE_LEVELS) - 1
            if constraints.spice_ceiling is None
            else constraints.spice_ceiling
        )
        candidate = {i for i in survivors if floor <= dishes[i].spice_rank <= ceiling}
        label = _spice_band_label(floor, ceiling)
        if len(candidate) >= MIN_SURVIVORS:
            survivors = candidate
            report.applied.append(label)
        else:
            report.relaxed.append(f"{label} (too few matches)")

    if len(constraints.categories_include) == 1 and not constraints.tags_include:
        category = next(iter(constraints.categories_include))
        candidate = {i for i in survivors if dishes[i].category == category}
        if len(candidate) >= MIN_SURVIVORS:
            survivors = candidate
            report.applied.append(f"category = {category}")
        else:
            report.relaxed.append(f"category = {category} (too few matches)")

    report.removed = len(dishes) - len(survivors)
    return survivors, report


# ---------------------------------------------------------------------------
# Additive scoring
# ---------------------------------------------------------------------------
def score_dish(
    dish: Dish,
    relevance: float,
    constraints: Constraints,
    settings: ScoringSettings,
    name_match_kind: str | None = None,
    warnings: Sequence[health.Warning] = (),
    price_book: object | None = None,
) -> tuple[float, list[Signal], str | None]:
    """Final score, its signal breakdown, and the worst health severity."""
    signals: list[Signal] = [
        Signal("relevance", settings.relevance_weight * relevance, "semantic + lexical match")
    ]

    if name_match_kind == "exact":
        signals.append(Signal("exact_name", settings.exact_name_bonus, f'query names "{dish.name}"'))
    elif name_match_kind == "fuzzy":
        signals.append(
            Signal("name_typo", settings.exact_name_bonus * 0.8, f'close spelling of "{dish.name}"')
        )
    elif name_match_kind == "partial":
        signals.append(Signal("partial_name", settings.partial_name_bonus, "query mentions this dish"))

    _score_diet(dish, constraints, settings, signals)
    _score_spice(dish, constraints, settings, signals)
    _score_price(dish, constraints, settings, signals)
    _score_budget(dish, constraints, settings, signals, price_book)
    _score_meal(dish, constraints, settings, signals)
    _score_category(dish, constraints, settings, signals)
    _score_tags(dish, constraints, settings, signals)

    severity = health.worst_severity(warnings)
    if severity == "danger":
        signals.append(
            Signal("health_danger", settings.health_danger_penalty, "conflicts with your health profile")
        )
    elif severity == "caution":
        signals.append(
            Signal("health_caution", settings.health_caution_penalty, "use caution with your health profile")
        )

    total = sum(signal.contribution for signal in signals)
    return total, signals, severity


def _score_diet(
    dish: Dish, constraints: Constraints, settings: ScoringSettings, signals: list[Signal]
) -> None:
    if constraints.diet is None:
        return
    wants_veg = constraints.diet == "veg"
    if dish.is_veg == wants_veg:
        signals.append(
            Signal(
                "diet",
                settings.diet_match_bonus,
                "vegetarian" if wants_veg else "non-vegetarian",
            )
        )
    else:
        # Reachable only for diet == nonveg; veg is enforced as a hard filter.
        signals.append(Signal("diet", settings.soft_violation_penalty, "wrong diet type"))


def _score_spice(
    dish: Dish, constraints: Constraints, settings: ScoringSettings, signals: list[Signal]
) -> None:
    floor, ceiling = constraints.spice_floor, constraints.spice_ceiling
    if floor is None and ceiling is None:
        return
    rank = dish.spice_rank
    over = 0 if ceiling is None else max(0, rank - ceiling)
    under = 0 if floor is None else max(0, floor - rank)
    distance = max(over, under)

    if distance == 0:
        signals.append(Signal("spice", settings.spice_match_bonus, f"{dish.spicy_level} spice fits"))
        return

    # Scale the penalty by how far outside the requested band the dish sits, so
    # "Medium" for a "not spicy" query is penalised less than "High".
    factor = min(1.0, distance / 2.0)
    direction = "too spicy" if over else "not spicy enough"
    signals.append(
        Signal(
            "spice",
            -settings.spice_match_bonus * (0.5 + 0.5 * factor),
            f"{dish.spicy_level} spice is {direction}",
        )
    )


def _score_price(
    dish: Dish, constraints: Constraints, settings: ScoringSettings, signals: list[Signal]
) -> None:
    floor, ceiling = constraints.price_floor, constraints.price_ceiling
    if floor is None and ceiling is None:
        return
    rank = dish.price_rank
    over = 0 if ceiling is None else max(0, rank - ceiling)
    under = 0 if floor is None else max(0, floor - rank)
    if max(over, under) == 0:
        signals.append(Signal("price", settings.price_match_bonus, f"{dish.price_range} price fits"))
    else:
        signals.append(
            Signal("price", -settings.price_match_bonus, f"{dish.price_range} price is outside range")
        )


def _score_budget(
    dish: Dish,
    constraints: Constraints,
    settings: ScoringSettings,
    signals: list[Signal],
    price_book: object | None,
) -> None:
    """Score a stated rupee budget, e.g. "kottu under 500".

    Deliberately soft, and deliberately silent when the price is unknown. Two
    judgements worth spelling out:

    **The floor decides whether something "fits".** A dish is judged obtainable
    within budget on its *low* price, not its typical one, because "under Rs 500"
    asks whether it is possible to eat this for 500 - and at a roadside eatery it
    very often is, even when the mid-range price is higher. The full bonus is
    reserved for dishes that fit at their typical price; ones that only fit at
    the cheap end get half, which ranks them below the comfortable matches
    without hiding them.

    **A missing price scores nothing at all** - neither bonus nor penalty. There
    are 155 dishes and a price for each, but a custom table loaded via
    `FOODAI_PRICE_TABLE` may cover fewer. Penalising unpriced dishes would let an
    incomplete table quietly bury them.
    """
    if price_book is None:
        return
    ceiling = constraints.max_price_lkr
    floor = constraints.min_price_lkr
    if ceiling is None and floor is None:
        return

    price = price_book.get(dish.name)
    if price is None:
        return

    weight = settings.budget_match_bonus
    symbol = getattr(price, "symbol", "Rs")

    factors: list[tuple[float, str]] = []

    if ceiling is not None:
        if price.typical <= ceiling:
            factors.append((1.0, f"{price.display()} fits under {symbol} {ceiling:,}"))
        elif price.low <= ceiling:
            factors.append(
                (
                    0.5,
                    f"usually {symbol} {price.typical:,}, but can be found from "
                    f"{symbol} {price.low:,}",
                )
            )
        else:
            # Scaled by how far over, so Rs 50 over is not treated like Rs 3,000
            # over. Bounded at the full weight either way.
            over = (price.low - ceiling) / float(ceiling)
            factors.append(
                (
                    -(0.5 + 0.5 * min(1.0, over)),
                    f"from {symbol} {price.low:,}, over a {symbol} {ceiling:,} budget",
                )
            )

    if floor is not None:
        if price.typical >= floor:
            factors.append((1.0, f"{price.display()} is at least {symbol} {floor:,}"))
        elif price.high >= floor:
            factors.append((0.5, f"reaches {symbol} {price.high:,} at the top end"))
        else:
            under = (floor - price.high) / float(floor)
            factors.append(
                (
                    -(0.5 + 0.5 * min(1.0, under)),
                    f"tops out at {symbol} {price.high:,}, under {symbol} {floor:,}",
                )
            )

    # One signal, not two: a stated range is a single user intent, and the
    # weakest half of it should govern. Emitting two "budget" rows would also let
    # a range contribute double any other facet's weight.
    factor, detail = min(factors, key=lambda pair: pair[0])
    signals.append(Signal("budget", weight * factor, detail))


def _score_meal(
    dish: Dish, constraints: Constraints, settings: ScoringSettings, signals: list[Signal]
) -> None:
    if not constraints.meal_times:
        return
    wanted = constraints.meal_times
    if dish.meal_times & wanted:
        # 101 of 155 dishes are labelled "Any", so an "Any" dish matching
        # "breakfast" is far weaker evidence than a dish labelled Breakfast.
        # Without this discount, the generic majority swamps the specific few.
        if dish.meal_times == _ALL_MEALS:
            signals.append(Signal("meal_time", settings.meal_match_bonus * 0.3, "suitable any time"))
        else:
            signals.append(
                Signal("meal_time", settings.meal_match_bonus, f"eaten at {dish.meal_time}")
            )
    else:
        signals.append(
            Signal("meal_time", -settings.meal_match_bonus, f"usually eaten at {dish.meal_time}")
        )


def _score_category(
    dish: Dish, constraints: Constraints, settings: ScoringSettings, signals: list[Signal]
) -> None:
    if dish.category in constraints.categories_exclude:
        signals.append(
            Signal("category", settings.soft_violation_penalty, f"{dish.category} was excluded")
        )
        return
    if not constraints.categories_include:
        return
    if dish.category in constraints.categories_include:
        signals.append(Signal("category", settings.category_match_bonus, f"is {dish.category}"))
    else:
        signals.append(
            Signal("category", -settings.category_match_bonus, f"is {dish.category}, not requested")
        )


def _score_tags(
    dish: Dish, constraints: Constraints, settings: ScoringSettings, signals: list[Signal]
) -> None:
    wanted = constraints.tags_include
    if wanted:
        matched = wanted & dish.tags
        if matched:
            fraction = len(matched) / len(wanted)
            signals.append(
                Signal(
                    "tags",
                    settings.tag_match_bonus * fraction,
                    "matches " + ", ".join(tag_label(t) for t in sorted(matched)),
                )
            )
        else:
            signals.append(
                Signal(
                    "tags",
                    -settings.tag_match_bonus * 0.5,
                    "missing " + ", ".join(tag_label(t) for t in sorted(wanted)),
                )
            )

    # Non-allergen exclusions are preferences, so they are penalised rather than
    # filtered. Allergen exclusions never reach here - they are hard filters.
    soft_excluded = (constraints.tags_exclude - ALLERGEN_TAGS) & dish.tags
    if soft_excluded:
        signals.append(
            Signal(
                "excluded_tags",
                settings.soft_violation_penalty,
                "contains " + ", ".join(tag_label(t) for t in sorted(soft_excluded)),
            )
        )


def spice_label(rank: int) -> str:
    return SPICE_LEVELS[max(0, min(rank, len(SPICE_LEVELS) - 1))]


def _spice_band_label(floor: int, ceiling: int) -> str:
    if floor == ceiling:
        return f"spice = {spice_label(floor)}"
    if floor <= 0:
        return f"spice up to {spice_label(ceiling)}"
    if ceiling >= len(SPICE_LEVELS) - 1:
        return f"spice at least {spice_label(floor)}"
    return f"spice {spice_label(floor)} to {spice_label(ceiling)}"
