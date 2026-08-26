"""Price lookup, band derivation, staleness and venue-tier scaling.

Stdlib only, like `nlu.py` / `ranking.py` / `health.py`, so the price tests run
without the ML stack installed.

Three deliberate choices:

**The CSV column stays authoritative.** `price_range` in
`sri_lankan_food_dataset.csv` is a feature column of the pickled XGBoost model
(`recommend.FEATURE_COLUMNS`) and an ordinal in `nlu.Constraints`. Numeric prices
are additive - display, plus budget queries - and never rewrite the band. Where
the two disagree, `band_mismatches()` reports it instead of one silently
overwriting the other. That is the same treatment the README gives the
spice-versus-prose disagreement.

**Staleness is a first-class field, not a caveat in the docs.** A price table has
a shelf life, and Sri Lankan food prices moved sharply after 2022. Past
`stale_days` every price carries `stale: true` and the client badges it. A price
that is quietly two years old is worse than no price, because the user cannot
tell the difference.

**A price is a range scaled by venue class, not a point.** `for_tier()` exists
because "how much is kottu" has no single answer; the honest answer is a band
plus where you are standing.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .data.prices import (
    CONFIDENCE_LEVELS,
    CURRENCY,
    CURRENCY_SYMBOL,
    DEFAULT_TIER,
    DISH_PRICES,
    KNOWN_BAND_MISMATCHES,
    PRICE_AS_OF,
    VENUE_TIER_MULTIPLIERS,
)

# Upper bound of each band, in baseline rupees, applied to `typical`. Chosen to
# reproduce the CSV's Low/Medium/High split; see tests/test_pricing.py.
BAND_LOW_MAX = 500
BAND_MEDIUM_MAX = 1200

BANDS = ("Low", "Medium", "High")


def derive_band(typical: float) -> str:
    """Low/Medium/High from a baseline `typical` price."""
    if typical <= BAND_LOW_MAX:
        return "Low"
    if typical <= BAND_MEDIUM_MAX:
        return "Medium"
    return "High"


def round_price(value: float) -> int:
    """Round to a step a menu would actually use.

    Inflation adjustment produces figures like 517.4, and showing "Rs 517" for a
    cup of tea implies a precision the estimate does not have.
    """
    if value < 100:
        step = 5
    elif value < 500:
        step = 10
    elif value < 2000:
        step = 50
    else:
        step = 100
    return max(step, int(round(value / step)) * step)


def format_amount(value: int, symbol: str = CURRENCY_SYMBOL) -> str:
    """`1400` -> `"Rs 1,400"`."""
    return f"{symbol} {value:,}"


@dataclass(frozen=True)
class Price:
    """A dish's price estimate, already inflation-adjusted."""

    dish: str
    low: int
    typical: int
    high: int
    unit: str
    confidence: str
    currency: str
    symbol: str
    as_of: str
    stale: bool
    age_days: int
    band: str
    # The authoritative band from the CSV, when the caller supplied a Dish.
    dataset_band: str | None = None
    inflation: float = 1.0

    @property
    def band_agrees(self) -> bool:
        """False only where the numbers and the dataset column disagree."""
        return self.dataset_band is None or self.band == self.dataset_band

    def for_tier(self, tier: str = DEFAULT_TIER) -> tuple[int, int]:
        """Estimated (low, high) at one class of venue.

        The band is kept - a single venue still has a spread across portion
        sizes - but narrowed around the tier-scaled typical price.
        """
        multiplier = VENUE_TIER_MULTIPLIERS.get(tier, 1.0)
        centre = self.typical * multiplier
        return round_price(centre * 0.82), round_price(centre * 1.35)

    def display(self) -> str:
        """`"Rs 650 - 1,400"`, or a single figure when the range collapses."""
        low, high = format_amount(self.low, self.symbol), f"{self.high:,}"
        return low if self.low == self.high else f"{low} - {high}"

    def as_dict(self) -> dict[str, object]:
        return {
            "low": self.low,
            "typical": self.typical,
            "high": self.high,
            "unit": self.unit,
            "currency": self.currency,
            "display": self.display(),
            "band": self.band,
            "dataset_band": self.dataset_band,
            "band_agrees": self.band_agrees,
            "confidence": self.confidence,
            "as_of": self.as_of,
            "age_days": self.age_days,
            "stale": self.stale,
            "estimated": True,
            "inflation_applied": round(self.inflation, 4),
        }


class PriceBook:
    """Read-only price index over the dish table."""

    def __init__(
        self,
        table: Mapping[str, tuple[int, int, int, str, str]] | None = None,
        as_of: str = PRICE_AS_OF,
        currency: str = CURRENCY,
        symbol: str = CURRENCY_SYMBOL,
        inflation: float = 1.0,
        stale_days: int = 365,
        today: date | None = None,
    ) -> None:
        source = DISH_PRICES if table is None else table
        self.as_of = as_of
        self.currency = currency
        self.symbol = symbol
        self.inflation = inflation if inflation > 0 else 1.0
        self.stale_days = stale_days
        self._today = today or date.today()
        self._age_days = self._compute_age()
        self._stale = self.stale_days > 0 and self._age_days > self.stale_days
        # Keyed case-insensitively, matching Corpus.get().
        self._by_name: dict[str, Price] = {}
        for name, entry in source.items():
            price = self._build(name, entry)
            if price is not None:
                self._by_name[name.strip().lower()] = price

    # -- construction ------------------------------------------------------
    def _compute_age(self) -> int:
        try:
            baseline = date.fromisoformat(self.as_of)
        except ValueError:
            return 0
        return max(0, (self._today - baseline).days)

    def _build(
        self, name: str, entry: Sequence[object]
    ) -> Price | None:
        if len(entry) < 4:
            return None
        try:
            low = round_price(float(entry[0]) * self.inflation)
            typical = round_price(float(entry[1]) * self.inflation)
            high = round_price(float(entry[2]) * self.inflation)
        except (TypeError, ValueError):
            return None
        unit = str(entry[3])
        confidence = str(entry[4]) if len(entry) > 4 else "medium"
        if confidence not in CONFIDENCE_LEVELS:
            confidence = "medium"

        # Rounding can invert a tight range; keep the ordering an invariant so
        # `display()` can never print "Rs 200 - 190".
        low, typical, high = sorted((low, typical, high))

        return Price(
            dish=name,
            low=low,
            typical=typical,
            high=high,
            unit=unit,
            confidence=confidence,
            currency=self.currency,
            symbol=self.symbol,
            as_of=self.as_of,
            stale=self._stale,
            age_days=self._age_days,
            # Derived from the *baseline* typical, so a uniform inflation
            # multiplier cannot reshuffle dishes between bands.
            band=derive_band(float(entry[1])),
            inflation=self.inflation,
        )

    # -- lookup ------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._by_name)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.strip().lower() in self._by_name

    def get(self, name: str) -> Price | None:
        return self._by_name.get(name.strip().lower())

    def for_dish(self, dish: object) -> Price | None:
        """Price for a `corpus.Dish`, annotated with the dataset's own band.

        Typed loosely on purpose: importing `Dish` here would make `pricing`
        depend on `corpus`, and only `.name` / `.price_range` are needed.
        """
        name = getattr(dish, "name", None)
        if not isinstance(name, str):
            return None
        price = self.get(name)
        if price is None:
            return None
        dataset_band = getattr(dish, "price_range", None)
        if not isinstance(dataset_band, str) or dataset_band not in BANDS:
            return price
        return replace(price, dataset_band=dataset_band)

    def missing(self, names: Iterable[str]) -> list[str]:
        """Dish names with no price entry - a coverage check for the tests."""
        return [name for name in names if name not in self]

    def band_mismatches(self, dishes: Iterable[object]) -> list[dict[str, object]]:
        """Dishes whose numeric band contradicts the dataset column.

        Surfaced rather than reconciled. `KNOWN_BAND_MISMATCHES` documents the
        expected set and the test suite pins it, so new drift is a test failure
        rather than a quiet inconsistency.
        """
        out: list[dict[str, object]] = []
        for dish in dishes:
            price = self.for_dish(dish)
            if price is not None and not price.band_agrees:
                out.append(
                    {
                        "name": price.dish,
                        "dataset_band": price.dataset_band,
                        "derived_band": price.band,
                        "typical": price.typical,
                        "documented": price.dish in KNOWN_BAND_MISMATCHES,
                    }
                )
        return out

    # -- budget queries ----------------------------------------------------
    def fits_budget(self, name: str, max_lkr: int) -> bool | None:
        """Is the dish obtainable at or under `max_lkr`?

        Tested against `low`, not `typical`: "under Rs 500" asks whether it is
        *possible* to eat this for 500, and at a local eatery it often is even
        when the mid-range price is higher. Returns None when the dish has no
        price, so callers can distinguish "does not fit" from "unknown".
        """
        price = self.get(name)
        if price is None:
            return None
        return price.low <= max_lkr

    def budget_distance(self, name: str, max_lkr: int) -> float | None:
        """How far over budget, as a fraction of the budget. 0.0 when it fits.

        Used by `ranking._score_budget` to scale the penalty, so a dish Rs 50
        over is not treated like one Rs 3,000 over.
        """
        price = self.get(name)
        if price is None or max_lkr <= 0:
            return None
        if price.low <= max_lkr:
            return 0.0
        return (price.low - max_lkr) / float(max_lkr)

    # -- ops ---------------------------------------------------------------
    @property
    def age_days(self) -> int:
        """Days since `as_of`. Exposed so callers need not touch `_age_days`."""
        return self._age_days

    @property
    def stale(self) -> bool:
        """True once the table is older than `stale_days`.

        A read-only property rather than a plain attribute: staleness is derived
        from `as_of` and today's date, and a settable flag would let a caller
        mark a two-year-old table fresh.
        """
        return self._stale

    def stats(self) -> dict[str, object]:
        return {
            "entries": len(self._by_name),
            "currency": self.currency,
            "as_of": self.as_of,
            "age_days": self._age_days,
            "stale": self._stale,
            "stale_after_days": self.stale_days,
            "inflation": round(self.inflation, 4),
            "bands": {
                "low_max": BAND_LOW_MAX,
                "medium_max": BAND_MEDIUM_MAX,
            },
            "venue_tiers": dict(VENUE_TIER_MULTIPLIERS),
            "source": "curated offline estimates",
            "estimated": True,
        }


def load_price_table(path: Path) -> dict[str, tuple[int, int, int, str, str]]:
    """Load a price table from CSV, for replacing the bundled estimates.

    Columns: `name,low,typical,high,unit,confidence`. `unit` and `confidence`
    are optional. Rows that cannot be parsed are skipped rather than aborting
    the load, so one bad line does not take the API down at boot.
    """
    table: dict[str, tuple[int, int, int, str, str]] = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            try:
                low = int(float(row["low"]))
                typical = int(float(row["typical"]))
                high = int(float(row["high"]))
            except (KeyError, TypeError, ValueError):
                continue
            unit = (row.get("unit") or "portion").strip() or "portion"
            confidence = (row.get("confidence") or "medium").strip().lower()
            if confidence not in CONFIDENCE_LEVELS:
                confidence = "medium"
            table[name] = (low, typical, high, unit, confidence)
    return table
