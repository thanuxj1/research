"""Query-understanding tests.

Stdlib only, no ML dependencies required:

    python -m unittest discover backend/tests -v

Each test named `test_regression_*` pins a concrete bug that existed in the
original substring-matching implementation.
"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

from app.data.descriptions import FOOD_DESCRIPTIONS
from app.data.taxonomy import SPICE_ORDER
from app.nlu import QueryAnalyzer

DATA_PATH = Path(__file__).resolve().parent.parent / "sri_lankan_food_dataset.csv"


def _load_names() -> list[str]:
    with DATA_PATH.open(newline="", encoding="utf-8") as fh:
        return [row["name"] for row in csv.DictReader(fh)]


class NluTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        names = _load_names()
        cls.analyzer = QueryAnalyzer(
            dish_names=names,
            extra_vocabulary=list(FOOD_DESCRIPTIONS.values()),
        )

    def analyze(self, query: str):
        return self.analyzer.analyze(query)


class TestSpice(NluTestCase):
    def test_not_spicy_caps_spice(self) -> None:
        c = self.analyze("not spicy food").constraints
        self.assertEqual(c.spice_ceiling, SPICE_ORDER["Low"])
        self.assertIsNone(c.spice_floor)

    def test_mild_caps_spice(self) -> None:
        self.assertEqual(self.analyze("mild curry").constraints.spice_ceiling, SPICE_ORDER["Low"])

    def test_spicy_sets_floor(self) -> None:
        c = self.analyze("very spicy curry").constraints
        self.assertIsNotNone(c.spice_floor)
        self.assertGreaterEqual(c.spice_floor, SPICE_ORDER["Medium"])
        self.assertIsNone(c.spice_ceiling)

    def test_medium_spice_targets_medium(self) -> None:
        c = self.analyze("medium spice chicken").constraints
        self.assertEqual(c.spice_floor, SPICE_ORDER["Medium"])
        self.assertEqual(c.spice_ceiling, SPICE_ORDER["Medium"])

    def test_no_spice_at_all(self) -> None:
        self.assertEqual(self.analyze("zero spice dessert").constraints.spice_ceiling, 0)

    def test_aversion_beats_desire(self) -> None:
        # Contradictory: floor must be dropped, ceiling kept (safety-first).
        c = self.analyze("spicy but not spicy").constraints
        self.assertEqual(c.spice_ceiling, SPICE_ORDER["Low"])
        self.assertIsNone(c.spice_floor)


class TestDiet(NluTestCase):
    def test_vegetarian(self) -> None:
        self.assertEqual(self.analyze("vegetarian lunch").constraints.diet, "veg")

    def test_regression_not_vegetarian_is_not_vegetarian(self) -> None:
        """Original code: `'vegetarian' in query` -> filtered TO vegetarian."""
        self.assertEqual(self.analyze("not vegetarian").constraints.diet, "nonveg")

    def test_regression_no_meat_means_vegetarian(self) -> None:
        self.assertEqual(self.analyze("no meat please").constraints.diet, "veg")

    def test_vegan_adds_tag(self) -> None:
        c = self.analyze("vegan options").constraints
        self.assertEqual(c.diet, "veg")
        self.assertIn("vegan", c.tags_include)

    def test_contradiction_leaves_diet_open(self) -> None:
        self.assertIsNone(self.analyze("vegetarian and non vegetarian").constraints.diet)

    def test_meat_words_do_not_force_diet(self) -> None:
        c = self.analyze("vegetarian alternative to chicken").constraints
        self.assertEqual(c.diet, "veg")
        self.assertIn("chicken", c.tags_include)


class TestNegation(NluTestCase):
    def test_regression_dont_want_seafood_excludes_seafood(self) -> None:
        """Original code returned ONLY seafood for this query."""
        c = self.analyze("I don't want seafood").constraints
        self.assertIn("seafood", c.tags_exclude)
        self.assertNotIn("seafood", c.tags_include)

    def test_without_coconut(self) -> None:
        self.assertIn("coconut", self.analyze("curry without coconut").constraints.tags_exclude)

    def test_suffix_free(self) -> None:
        self.assertIn("gluten", self.analyze("gluten free breakfast").constraints.tags_exclude)

    def test_suffix_allergy(self) -> None:
        self.assertIn("nuts", self.analyze("nut allergy snacks").constraints.tags_exclude)

    def test_allergic_to(self) -> None:
        self.assertIn("dairy", self.analyze("I am allergic to dairy").constraints.tags_exclude)

    def test_scope_breaker_stops_negation(self) -> None:
        c = self.analyze("not spicy but seafood").constraints
        self.assertEqual(c.spice_ceiling, SPICE_ORDER["Low"])
        self.assertIn("seafood", c.tags_include)
        self.assertNotIn("seafood", c.tags_exclude)

    def test_negation_does_not_leak_to_later_phrases(self) -> None:
        c = self.analyze("no eggs and then some nice warm coconut dessert").constraints
        self.assertIn("egg", c.tags_exclude)
        self.assertNotIn("coconut", c.tags_exclude)

    def test_regression_negation_scope_stops_at_first_phrase(self) -> None:
        """A fixed 4-token window over-captured: "not vegetarian dinner" reached
        past "vegetarian" and negated "dinner" too, silently discarding the
        meal-time the user asked for."""
        c = self.analyze("not vegetarian dinner").constraints
        self.assertEqual(c.diet, "nonveg")
        self.assertEqual(c.meal_times, {"Dinner"})

    def test_conjunction_propagates_negation(self) -> None:
        c = self.analyze("no eggs or dairy").constraints
        self.assertIn("egg", c.tags_exclude)
        self.assertIn("dairy", c.tags_exclude)

    def test_conjunction_after_positive_stays_positive(self) -> None:
        c = self.analyze("seafood and coconut").constraints
        self.assertIn("seafood", c.tags_include)
        self.assertIn("coconut", c.tags_include)
        self.assertEqual(c.tags_exclude, set())

    def test_filler_between_cue_and_phrase(self) -> None:
        for query in ("without any coconut", "no more of that coconut"):
            with self.subTest(query=query):
                self.assertIn("coconut", self.analyze(query).constraints.tags_exclude)

    def test_regression_free_does_not_negate_the_next_phrase(self) -> None:
        """"free" is a suffix cue. Treating it as a prefix cue too meant
        "gluten free breakfast" excluded breakfast."""
        c = self.analyze("gluten free breakfast").constraints
        self.assertIn("gluten", c.tags_exclude)
        self.assertEqual(c.meal_times, {"Breakfast"})

    def test_regression_allergy_does_not_negate_the_next_phrase(self) -> None:
        c = self.analyze("nut allergy tea time snacks").constraints
        self.assertIn("nuts", c.tags_exclude)
        self.assertIn("tea_time", c.tags_include)

    def test_regression_anything_is_not_a_bare_cue(self) -> None:
        """"anything" only negates as part of "anything but"."""
        c = self.analyze("anything mild").constraints
        self.assertEqual(c.spice_ceiling, SPICE_ORDER["Low"])

    def test_exclusion_beats_inclusion(self) -> None:
        c = self.analyze("seafood but not seafood").constraints
        self.assertIn("seafood", c.tags_exclude)
        self.assertNotIn("seafood", c.tags_include)

    def test_anything_but(self) -> None:
        self.assertIn("seafood", self.analyze("anything but seafood").constraints.tags_exclude)

    def test_regression_contractions_survive_normalization(self) -> None:
        """Contractions must expand before punctuation is stripped, or the
        negation cue is destroyed and the query inverts."""
        cases = [
            ("I don't like spicy food", "spice_ceiling", SPICE_ORDER["Low"]),
            ("I doesn't want spicy", "spice_ceiling", SPICE_ORDER["Low"]),
            ("I can't eat gluten", "tags_exclude", "gluten"),
            ("I couldn't eat seafood", "tags_exclude", "seafood"),
            ("I won't eat pork", "tags_exclude", "pork"),
        ]
        for query, attr, expected in cases:
            with self.subTest(query=query):
                value = getattr(self.analyze(query).constraints, attr)
                if isinstance(value, set):
                    self.assertIn(expected, value)
                else:
                    self.assertEqual(value, expected)

    def test_curly_apostrophe(self) -> None:
        # Mobile keyboards emit U+2019, not U+0027.
        c = self.analyze("I don\u2019t want seafood").constraints
        self.assertIn("seafood", c.tags_exclude)

    def test_negated_terms_dropped_from_sparse_bag(self) -> None:
        """BM25 must not retrieve the very thing the user excluded."""
        bag = self.analyze("rice without seafood").sparse_tokens
        self.assertIn("rice", bag)
        for term in ("seafood", "fish", "prawn", "crab", "cuttlefish"):
            self.assertNotIn(term, bag)


class TestWordBoundaries(NluTestCase):
    def test_regression_instead_does_not_mean_tea(self) -> None:
        """Original code: `'tea' in query` matched "ins*tea*d"."""
        c = self.analyze("what should I eat instead").constraints
        self.assertNotIn("Drinks", c.categories_include)

    def test_regression_steamed_does_not_mean_tea(self) -> None:
        c = self.analyze("steamed breakfast").constraints
        self.assertNotIn("Drinks", c.categories_include)

    def test_regression_tea_time_is_snacks_not_drinks(self) -> None:
        """Longest-match: "tea time" must win over the bare "tea" -> Drinks alias."""
        c = self.analyze("tea time snacks").constraints
        self.assertIn("tea_time", c.tags_include)
        self.assertNotIn("Drinks", c.categories_include)

    def test_bare_tea_is_a_drink(self) -> None:
        self.assertIn("Drinks", self.analyze("ceylon tea").constraints.categories_include)

    def test_regression_sweet_potato_is_not_a_dessert(self) -> None:
        """"sweet potato" must not be coerced into the Desserts category."""
        c = self.analyze("boiled sweet potatoes").constraints
        self.assertNotIn("Desserts", c.categories_include)


class TestFacets(NluTestCase):
    def test_price_cheap(self) -> None:
        self.assertEqual(self.analyze("cheap street food").constraints.price_ceiling, 0)

    def test_price_expensive(self) -> None:
        self.assertEqual(self.analyze("premium dinner").constraints.price_floor, 2)

    def test_meal_time(self) -> None:
        self.assertEqual(self.analyze("breakfast ideas").constraints.meal_times, {"Breakfast"})

    def test_multiple_meal_times(self) -> None:
        self.assertEqual(
            self.analyze("breakfast or dinner").constraints.meal_times,
            {"Breakfast", "Dinner"},
        )

    def test_category_drinks(self) -> None:
        self.assertIn("Drinks", self.analyze("cold drink").constraints.categories_include)

    def test_tourist_implies_mild_and_beginner(self) -> None:
        c = self.analyze("food for tourists").constraints
        self.assertEqual(c.spice_ceiling, SPICE_ORDER["Low"])
        self.assertIn("beginner_friendly", c.tags_include)

    def test_compound_query(self) -> None:
        c = self.analyze("cheap mild vegetarian breakfast without coconut").constraints
        self.assertEqual(c.diet, "veg")
        self.assertEqual(c.price_ceiling, 0)
        self.assertEqual(c.spice_ceiling, SPICE_ORDER["Low"])
        self.assertEqual(c.meal_times, {"Breakfast"})
        self.assertIn("coconut", c.tags_exclude)

    def test_sauces_and_sides_reachable_via_and(self) -> None:
        self.assertIn(
            "Sauces & Sides",
            self.analyze("sambol side dishes").constraints.categories_include,
        )


class TestBudget(NluTestCase):
    """Numeric budgets in LKR.

    A misread amount is worse than an unread one: it silently reshapes the whole
    result page, and the user has no way to tell that "under 1,000" was taken as
    Rs 1. The `test_regression_*` cases here are all of that kind.
    """

    def budget(self, query: str) -> tuple[int | None, int | None]:
        c = self.analyze(query).constraints
        return c.max_price_lkr, c.min_price_lkr

    def test_ceiling_phrasings(self) -> None:
        for query in (
            "kottu under 500",
            "kottu under Rs 500",
            "less than 500 rupees",
            "up to 500 rupees",
            "max 500 lkr",
            "within 500 rupees",
            "500 rupees or less",
            "cheaper than 500 rupees",
        ):
            with self.subTest(query=query):
                self.assertEqual(self.budget(query), (500, None))

    def test_floor_phrasings(self) -> None:
        for query in (
            "over 1000 rupees",
            "above 1000 rupees",
            "at least 1000 rupees",
            "minimum 1000 rupees",
        ):
            with self.subTest(query=query):
                self.assertEqual(self.budget(query), (None, 1000))

    def test_bare_amount_with_a_currency_word_is_a_ceiling(self) -> None:
        """Users state what they are willing to spend far more often than what
        they insist on spending."""
        self.assertEqual(self.budget("kottu for 500 rupees"), (500, None))

    def test_glued_units_are_read(self) -> None:
        # Typed without a space more often than not.
        self.assertEqual(self.budget("something for 500lkr"), (500, None))
        self.assertEqual(self.budget("rs500 rice and curry"), (500, None))

    def test_around_is_a_band_on_both_sides(self) -> None:
        self.assertEqual(self.budget("around 700 rupees"), (875, 525))

    def test_explicit_range(self) -> None:
        for query in ("between 300 and 800 rupees", "from 300 to 800 rupees"):
            with self.subTest(query=query):
                self.assertEqual(self.budget(query), (800, 300))

    def test_negation_flips_the_comparator(self) -> None:
        """"more" is a *minimum* cue, so read literally "no more than 500" sets a
        Rs 500 floor and returns exactly the dishes the user was avoiding."""
        self.assertEqual(self.budget("no more than 500 rupees"), (500, None))
        self.assertEqual(self.budget("not less than 500 rupees"), (None, 500))

    def test_most_restrictive_bound_wins(self) -> None:
        self.assertEqual(self.budget("under 800 rupees, ideally under 500"), (500, None))

    def test_contradictory_pair_drops_the_floor(self) -> None:
        # A band nothing can satisfy would empty the page; the ceiling is the
        # half of the request that can still be honoured.
        self.assertEqual(self.budget("over 900 rupees under 400 rupees"), (400, None))

    def test_quantities_are_not_budgets(self) -> None:
        for query in ("i want 2 hoppers", "less than 3 chillies", "top 5 spicy dishes"):
            with self.subTest(query=query):
                self.assertEqual(self.budget(query), (None, None))

    def test_bare_number_alone_is_not_a_budget(self) -> None:
        self.assertEqual(self.budget("500"), (None, None))
        self.assertEqual(self.budget("kottu 500"), (None, None))

    def test_implausible_amounts_are_ignored(self) -> None:
        """Above the plausible ceiling an amount is a year or a phone number, not
        a dish price."""
        self.assertEqual(self.budget("under 500000 rupees"), (None, None))
        self.assertEqual(self.budget("under 5 rupees"), (None, None))

    def test_lkr_budget_is_separate_from_the_ordinal_price_facet(self) -> None:
        """`price_ceiling` is an ordinal over the dataset's Low/Medium/High
        column, which is an XGBoost feature; rupee amounts must not be written
        into it."""
        cheap = self.analyze("cheap kottu").constraints
        self.assertEqual(cheap.price_ceiling, 0)
        self.assertIsNone(cheap.max_price_lkr)

        numeric = self.analyze("kottu under 500 rupees").constraints
        self.assertEqual(numeric.max_price_lkr, 500)
        self.assertIsNone(numeric.price_ceiling)

    def test_amount_is_echoed_in_words(self) -> None:
        # Shown in the UI, so a misread budget is at least visible.
        self.assertEqual(self.analyze("kottu under 1500 rupees").budget_mentions, ["up to Rs 1,500"])
        self.assertEqual(self.analyze("around 700 rupees").budget_mentions, ["around Rs 700"])
        self.assertEqual(
            self.analyze("between 300 and 800 rupees").budget_mentions,
            ["between Rs 300 and Rs 800"],
        )

    def test_budget_phrasing_does_not_cost_the_name_match(self) -> None:
        """Budget words are stripped before dish-name matching. Left in, the
        extra tokens dilute the query enough to lose the name match, and with it
        a bonus worth more than any other ranking signal."""
        for query in (
            "chicken kottu under 600 rupees",
            "chicken kottu budget 600",
            "chicken kottu 300-800 rupees",
        ):
            with self.subTest(query=query):
                matches = self.analyze(query).name_matches
                self.assertEqual(matches[0].name, "Chicken Kottu")
                self.assertEqual(matches[0].kind, "exact")

    def test_regression_thousands_separator(self) -> None:
        """"under 1,000 rupees" tokenised to ["1", "000"] and read as Rs 1."""
        self.assertEqual(self.budget("under 1,000 rupees"), (1000, None))
        # Lakh-style grouping is written this way here too.
        self.assertEqual(self.budget("under 1,00,000 rupees"), (100_000, None))

    def test_regression_adjacent_numbers_are_not_one_amount(self) -> None:
        """Repairing the separator above by rejoining adjacent 3-digit groups made
        "top 10 500" a Rs 10,500 budget. The separator is now handled on the raw
        text, where the comma is still visible to distinguish the two."""
        self.assertEqual(self.budget("top 10 500 rupees"), (500, None))
        self.assertEqual(self.budget("2 dishes 300 rupees"), (300, None))

    def test_regression_hyphenated_range(self) -> None:
        """The same rejoining turned "300-800 rupees" into Rs 300,800, which then
        exceeded the plausible maximum and was dropped, losing the budget
        entirely rather than misreading it."""
        for query in ("300-800 rupees", "kottu 300 - 800 rupees", "kottu 300–800 rupees"):
            with self.subTest(query=query):
                self.assertEqual(self.budget(query), (800, 300))

    def test_regression_implied_ceiling_words(self) -> None:
        """"budget 1500" parsed to nothing: "budget" was filler rather than a cue,
        and an amount with no comparator and no currency word is discarded."""
        self.assertEqual(self.budget("budget 1500"), (1500, None))
        self.assertEqual(self.budget("spend 800 on lunch"), (800, None))
        self.assertEqual(self.budget("i can afford 900"), (900, None))

    def test_implied_cue_yields_to_an_explicit_comparator(self) -> None:
        # The nearer cue governs, so an implied ceiling never overrides a stated
        # floor.
        self.assertEqual(self.budget("budget of at least 2000 rupees"), (None, 2000))
        self.assertEqual(self.budget("spend up to 2000 rupees"), (2000, None))


class TestNameMatching(NluTestCase):
    def test_exact_name(self) -> None:
        result = self.analyze("Watalappan")
        self.assertEqual(result.name_matches[0].name, "Watalappan")
        self.assertEqual(result.name_matches[0].kind, "exact")
        self.assertTrue(result.is_lookup)

    def test_typo_is_corrected(self) -> None:
        result = self.analyze("watalapan")
        self.assertIn("watalappan", result.corrected)
        self.assertTrue(any(m.name == "Watalappan" for m in result.name_matches))

    def test_partial_name_in_sentence(self) -> None:
        result = self.analyze("is chicken kottu spicy")
        self.assertTrue(any(m.name == "Chicken Kottu" for m in result.name_matches))

    def test_browse_query_is_not_a_lookup(self) -> None:
        self.assertFalse(self.analyze("something mild for a hot afternoon").is_lookup)

    def test_no_spurious_correction_of_common_words(self) -> None:
        # Ordinary English must survive the spell corrector untouched.
        for query in ("what should I eat instead", "something light and healthy"):
            with self.subTest(query=query):
                self.assertEqual(self.analyze(query).corrections, [])


class TestSerialization(NluTestCase):
    def test_as_dict_is_json_friendly(self) -> None:
        import json

        payload = self.analyze("mild vegetarian breakfast, no coconut").as_dict()
        json.dumps(payload)  # must not raise
        self.assertIn("constraints", payload)
        self.assertIn("matched_phrases", payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
