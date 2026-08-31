"""Price model tests. Stdlib only, no ML dependencies required:

    python -m unittest discover tests -v

Two of these are load-bearing rather than routine.

`test_derived_bands_agree_with_the_dataset` is what licenses the whole numeric
price layer to exist alongside the dataset's `price_range` column. That column is
a feature of the pickled XGBoost model and an ordinal in the NLU layer, so the
rupee figures must not contradict it; where they do, the disagreement is pinned
here by name instead of being silently reconciled in either direction.

`test_unit_is_never_empty` guards a wrong-by-1000 class of bug: Rs 40 for Plain
Hoppers is *per hopper* and Rs 700 for Rice and Curry is *per plate*. A price
rendered without its unit is not imprecise, it is false.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.corpus import load_corpus
from app.data.prices import (
    CONFIDENCE_LEVELS,
    DISH_PRICES,
    KNOWN_BAND_MISMATCHES,
    PRICE_AS_OF,
    VENUE_TIER_MULTIPLIERS,
)
from app.pricing import (
    BAND_LOW_MAX,
    BAND_MEDIUM_MAX,
    BANDS,
    PriceBook,
    derive_band,
    format_amount,
    load_price_table,
    round_price,
)

DATA_PATH = Path(__file__).resolve().parent.parent / "sri_lankan_food_dataset.csv"

# Fixed so staleness assertions do not start failing on their own one day.
FRESH_DAY = date(2025, 6, 1)  # 31 days after PRICE_AS_OF
STALE_DAY = date(2027, 1, 1)


class PricingTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.book = PriceBook(today=FRESH_DAY)


class TestBands(unittest.TestCase):
    def test_thresholds_are_inclusive_upper_bounds(self) -> None:
        self.assertEqual(derive_band(BAND_LOW_MAX), "Low")
        self.assertEqual(derive_band(BAND_LOW_MAX + 1), "Medium")
        self.assertEqual(derive_band(BAND_MEDIUM_MAX), "Medium")
        self.assertEqual(derive_band(BAND_MEDIUM_MAX + 1), "High")

    def test_band_names_match_the_dataset_vocabulary(self) -> None:
        # The derived band is compared against the CSV column directly, so the
        # two vocabularies have to be identical, not merely similar.
        self.assertEqual(BANDS, ("Low", "Medium", "High"))
        for value in (1, 500, 501, 1200, 99_000):
            with self.subTest(value=value):
                self.assertIn(derive_band(value), BANDS)


class TestRounding(unittest.TestCase):
    def test_steps_follow_the_magnitude(self) -> None:
        cases = [(37, 35), (99, 100), (517.4, 500), (1234, 1250), (2549, 2500)]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(round_price(value), expected)

    def test_never_rounds_down_to_nothing(self) -> None:
        """A price of Rs 0 would read as "free", which is a different claim."""
        for value in (0, 0.4, 2):
            with self.subTest(value=value):
                self.assertGreater(round_price(value), 0)

    def test_format_amount_uses_thousands_separators(self) -> None:
        self.assertEqual(format_amount(1400), "Rs 1,400")
        self.assertEqual(format_amount(90), "Rs 90")
        self.assertEqual(format_amount(1400, "LKR"), "LKR 1,400")


class TestTable(PricingTestCase):
    def test_every_dish_in_the_corpus_has_a_price(self) -> None:
        """Partial coverage would show a price on some cards and not others,
        which reads as "this one is free" rather than "we do not know"."""
        corpus = load_corpus(DATA_PATH)
        self.assertEqual(self.book.missing(d.name for d in corpus), [])

    def test_no_prices_for_dishes_that_do_not_exist(self) -> None:
        # A stale entry here is how a renamed dish quietly loses its price.
        corpus = load_corpus(DATA_PATH)
        self.assertEqual([name for name in DISH_PRICES if corpus.get(name) is None], [])

    def test_unit_is_never_empty(self) -> None:
        for name, entry in DISH_PRICES.items():
            with self.subTest(dish=name):
                self.assertTrue(str(entry[3]).strip())

    def test_confidence_is_a_known_level(self) -> None:
        for name, entry in DISH_PRICES.items():
            with self.subTest(dish=name):
                self.assertIn(entry[4], CONFIDENCE_LEVELS)

    def test_low_typical_high_are_ordered_in_the_source(self) -> None:
        for name, entry in DISH_PRICES.items():
            with self.subTest(dish=name):
                self.assertLessEqual(entry[0], entry[1])
                self.assertLessEqual(entry[1], entry[2])

    def test_ordering_survives_rounding(self) -> None:
        """Rounding can invert a tight range, and `display()` would then print
        "Rs 200 - 190"."""
        for price in (self.book.get(name) for name in DISH_PRICES):
            with self.subTest(dish=price.dish):
                self.assertLessEqual(price.low, price.typical)
                self.assertLessEqual(price.typical, price.high)


class TestBandCrossCheck(PricingTestCase):
    def test_derived_bands_agree_with_the_dataset(self) -> None:
        """The numeric table must not contradict the CSV's `price_range`.

        Pinned exactly rather than by count: a new disagreement is a decision
        someone has to make (fix the number, or document why the column is
        wrong), not something to be absorbed by a loosened assertion.
        """
        corpus = load_corpus(DATA_PATH)
        mismatches = self.book.band_mismatches(list(corpus))
        self.assertEqual({m["name"] for m in mismatches}, set(KNOWN_BAND_MISMATCHES))
        for mismatch in mismatches:
            with self.subTest(dish=mismatch["name"]):
                self.assertTrue(mismatch["documented"])
                self.assertNotEqual(mismatch["dataset_band"], mismatch["derived_band"])

    def test_band_agrees_is_true_when_no_dataset_band_is_known(self) -> None:
        # `get()` has no Dish to read the column from, so it must not claim a
        # disagreement it cannot see.
        price = self.book.get("Chicken Kottu")
        self.assertIsNone(price.dataset_band)
        self.assertTrue(price.band_agrees)

    def test_for_dish_attaches_the_dataset_band(self) -> None:
        corpus = load_corpus(DATA_PATH)
        price = self.book.for_dish(corpus.get("Chicken Kottu"))
        self.assertEqual(price.dataset_band, "Medium")
        self.assertEqual(price.band, "Medium")
        self.assertTrue(price.band_agrees)

    def test_for_dish_ignores_a_junk_band(self) -> None:
        """A band outside the vocabulary is dropped rather than reported as a
        mismatch: the disagreement would be with the loader, not the price."""

        class Fake:
            name = "Chicken Kottu"
            price_range = "Moderate"

        price = self.book.for_dish(Fake())
        self.assertIsNone(price.dataset_band)

    def test_for_dish_tolerates_objects_it_cannot_read(self) -> None:
        self.assertIsNone(self.book.for_dish(object()))
        self.assertIsNone(self.book.for_dish(None))


class TestLookup(PricingTestCase):
    def test_lookup_is_case_and_whitespace_insensitive(self) -> None:
        # Matches Corpus.get(), so a name that resolves to a dish also resolves
        # to its price.
        for query in ("Chicken Kottu", "chicken kottu", "  CHICKEN KOTTU  "):
            with self.subTest(query=query):
                self.assertIsNotNone(self.book.get(query))

    def test_unknown_dish_is_none_not_zero(self) -> None:
        self.assertIsNone(self.book.get("Spaghetti Carbonara"))
        self.assertNotIn("Spaghetti Carbonara", self.book)

    def test_len_matches_the_source_table(self) -> None:
        self.assertEqual(len(self.book), len(DISH_PRICES))


class TestDisplay(PricingTestCase):
    def test_range_is_rendered_with_one_symbol(self) -> None:
        self.assertEqual(self.book.get("Chicken Kottu").display(), "Rs 650 - 2,000")

    def test_collapsed_range_renders_as_a_single_figure(self) -> None:
        book = PriceBook(
            table={"Flat": (100, 100, 100, "portion", "high")}, today=FRESH_DAY
        )
        self.assertEqual(book.get("Flat").display(), "Rs 100")

    def test_as_dict_carries_the_caveats_not_just_the_numbers(self) -> None:
        payload = self.book.get("Chicken Kottu").as_dict()
        for key in (
            "low", "typical", "high", "unit", "currency", "display", "band",
            "dataset_band", "band_agrees", "confidence", "as_of", "age_days",
            "stale", "estimated", "inflation_applied",
        ):
            with self.subTest(key=key):
                self.assertIn(key, payload)
        # The client renders the "est." marker from this flag rather than
        # assuming every price is an estimate, so it must always be present.
        self.assertIs(payload["estimated"], True)


class TestVenueTiers(PricingTestCase):
    def test_tiers_are_ordered_by_multiplier(self) -> None:
        price = self.book.get("Rice and Curry")
        ordered = sorted(VENUE_TIER_MULTIPLIERS, key=VENUE_TIER_MULTIPLIERS.get)
        lows = [price.for_tier(tier)[0] for tier in ordered]
        self.assertEqual(lows, sorted(lows))

    def test_every_tier_keeps_low_below_high(self) -> None:
        for name in ("Ceylon Tea", "Rice and Curry", "Crab Curry"):
            price = self.book.get(name)
            for tier in VENUE_TIER_MULTIPLIERS:
                with self.subTest(dish=name, tier=tier):
                    low, high = price.for_tier(tier)
                    self.assertLess(low, high)

    def test_unknown_tier_falls_back_to_the_baseline(self) -> None:
        price = self.book.get("Rice and Curry")
        self.assertEqual(price.for_tier("gastropub"), price.for_tier("casual"))

    def test_street_is_cheaper_than_hotel_by_a_wide_margin(self) -> None:
        """The point of the tier scale: one number for "how much is kottu" would
        be wrong at both ends."""
        price = self.book.get("Chicken Kottu")
        self.assertLess(price.for_tier("street")[1], price.for_tier("hotel")[0])


class TestStaleness(PricingTestCase):
    def test_fresh_table_is_not_stale(self) -> None:
        self.assertFalse(self.book.stale)
        self.assertEqual(self.book.age_days, 31)
        self.assertFalse(self.book.get("Chicken Kottu").stale)

    def test_old_table_marks_every_price_stale(self) -> None:
        book = PriceBook(today=STALE_DAY)
        self.assertTrue(book.stale)
        self.assertTrue(all(book.get(name).stale for name in DISH_PRICES))

    def test_staleness_can_be_switched_off_but_not_faked(self) -> None:
        book = PriceBook(today=STALE_DAY, stale_days=0)
        self.assertFalse(book.stale)
        # Read-only on purpose: a settable flag would let a caller mark a
        # two-year-old table fresh, which is the exact failure this guards.
        with self.assertRaises(AttributeError):
            book.stale = False  # type: ignore[misc]

    def test_age_is_never_negative(self) -> None:
        book = PriceBook(as_of=PRICE_AS_OF, today=date(2024, 1, 1))
        self.assertEqual(book.age_days, 0)

    def test_unparseable_as_of_does_not_crash_the_boot(self) -> None:
        book = PriceBook(as_of="soon", today=FRESH_DAY)
        self.assertEqual(book.age_days, 0)
        self.assertFalse(book.stale)


class TestInflation(PricingTestCase):
    def test_multiplier_scales_the_figures(self) -> None:
        book = PriceBook(inflation=3.0, today=FRESH_DAY)
        self.assertEqual(book.get("Ceylon Tea").typical, 300)
        self.assertEqual(self.book.get("Ceylon Tea").typical, 100)

    def test_bands_are_derived_from_baseline_figures(self) -> None:
        """A uniform re-basing must not reshuffle dishes between Low/Medium/High:
        the band feeds the model's feature column, and inflation is not a
        statement about relative cost."""
        book = PriceBook(inflation=3.0, today=FRESH_DAY)
        for name in DISH_PRICES:
            with self.subTest(dish=name):
                self.assertEqual(book.get(name).band, self.book.get(name).band)

    def test_nonsense_multiplier_is_ignored(self) -> None:
        for value in (0.0, -2.0):
            with self.subTest(inflation=value):
                book = PriceBook(inflation=value, today=FRESH_DAY)
                self.assertEqual(book.inflation, 1.0)


class TestBudget(PricingTestCase):
    def test_fits_budget_is_tested_against_the_low_price(self) -> None:
        """"Under Rs 500" asks whether it is *possible* to eat this for 500, and
        at a local eatery it often is even when the typical price is higher."""
        price = self.book.get("Vegetable Kottu")
        self.assertEqual((price.low, price.typical), (450, 700))
        self.assertTrue(self.book.fits_budget("Vegetable Kottu", 500))
        self.assertFalse(self.book.fits_budget("Vegetable Kottu", 400))

    def test_unknown_dish_is_unknown_not_unaffordable(self) -> None:
        self.assertIsNone(self.book.fits_budget("Spaghetti Carbonara", 500))
        self.assertIsNone(self.book.budget_distance("Spaghetti Carbonara", 500))

    def test_distance_is_zero_when_it_fits(self) -> None:
        self.assertEqual(self.book.budget_distance("Vegetable Kottu", 500), 0.0)

    def test_distance_is_a_fraction_of_the_budget(self) -> None:
        # Rs 450 low against a Rs 300 budget: half as much again.
        self.assertAlmostEqual(self.book.budget_distance("Vegetable Kottu", 300), 0.5)

    def test_distance_scales_with_how_far_over_it_is(self) -> None:
        """The ranking penalty is scaled by this, so a dish Rs 50 over must not
        be treated like one Rs 3,000 over."""
        near = self.book.budget_distance("Vegetable Kottu", 400)
        far = self.book.budget_distance("Crab Curry", 400)
        self.assertLess(near, far)

    def test_nonpositive_budget_is_not_a_budget(self) -> None:
        for ceiling in (0, -100):
            with self.subTest(ceiling=ceiling):
                self.assertIsNone(self.book.budget_distance("Vegetable Kottu", ceiling))


class TestStats(PricingTestCase):
    def test_stats_reports_provenance(self) -> None:
        stats = self.book.stats()
        self.assertEqual(stats["entries"], len(DISH_PRICES))
        self.assertEqual(stats["currency"], "LKR")
        self.assertEqual(stats["as_of"], PRICE_AS_OF)
        self.assertIs(stats["estimated"], True)
        self.assertEqual(stats["bands"], {"low_max": BAND_LOW_MAX, "medium_max": BAND_MEDIUM_MAX})
        self.assertEqual(stats["venue_tiers"], dict(VENUE_TIER_MULTIPLIERS))

    def test_stats_venue_tiers_is_a_copy(self) -> None:
        # Handed to a JSON response; mutating it must not edit the constant.
        self.book.stats()["venue_tiers"]["street"] = 99.0
        self.assertNotEqual(VENUE_TIER_MULTIPLIERS["street"], 99.0)


class TestCsvOverride(unittest.TestCase):
    """`FOODAI_PRICE_TABLE` is the documented way to replace the estimates."""

    def _write(self, text: str) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        handle.write(text)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink)
        return path

    def test_loads_a_well_formed_table(self) -> None:
        path = self._write(
            "name,low,typical,high,unit,confidence\n"
            "Chicken Kottu,900,1300,2600,plate,high\n"
        )
        table = load_price_table(path)
        self.assertEqual(table["Chicken Kottu"], (900, 1300, 2600, "plate", "high"))

    def test_unit_and_confidence_are_optional(self) -> None:
        path = self._write("name,low,typical,high\nTea,50,100,400\n")
        self.assertEqual(load_price_table(path)["Tea"], (50, 100, 400, "portion", "medium"))

    def test_unknown_confidence_falls_back_to_medium(self) -> None:
        path = self._write("name,low,typical,high,unit,confidence\nTea,50,100,400,cup,certain\n")
        self.assertEqual(load_price_table(path)["Tea"][4], "medium")

    def test_bad_rows_are_skipped_not_fatal(self) -> None:
        """One malformed line must not take the API down at boot."""
        path = self._write(
            "name,low,typical,high\n"
            ",1,2,3\n"              # no name
            "Tea,cheap,100,400\n"   # unparseable
            "Tea,50,100,400\n"      # good
        )
        table = load_price_table(path)
        self.assertEqual(list(table), ["Tea"])

    def test_a_loaded_table_drives_the_book(self) -> None:
        path = self._write("name,low,typical,high,unit\nTea,50,100,400,cup\n")
        book = PriceBook(table=load_price_table(path), today=FRESH_DAY)
        self.assertEqual(len(book), 1)
        self.assertEqual(book.get("tea").unit, "cup")
        self.assertIsNone(book.get("Chicken Kottu"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
