"""Hard-filter and additive-scoring tests. Stdlib only."""

from __future__ import annotations

import unittest
from pathlib import Path

from app import health
from app.config import ScoringSettings
from app.corpus import load_corpus
from app.nlu import Constraints, QueryAnalyzer
from app.ranking import allowed_indices, score_dish
from app.data.descriptions import FOOD_DESCRIPTIONS
from app.data.taxonomy import SPICE_ORDER

DATA_PATH = Path(__file__).resolve().parent.parent / "sri_lankan_food_dataset.csv"


class RankingTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_corpus(DATA_PATH)
        cls.dishes = cls.corpus.dishes
        cls.settings = ScoringSettings()
        cls.analyzer = QueryAnalyzer(
            dish_names=cls.corpus.names,
            extra_vocabulary=list(FOOD_DESCRIPTIONS.values()),
        )

    def dish(self, name: str):
        found = self.corpus.get(name)
        self.assertIsNotNone(found, name)
        return found

    def score(self, dish_name: str, query: str, relevance: float = 0.8, warnings=()):
        constraints = self.analyzer.analyze(query).constraints
        return score_dish(
            self.dish(dish_name),
            relevance=relevance,
            constraints=constraints,
            settings=self.settings,
            warnings=warnings,
        )


class TestHardFilters(RankingTestCase):
    def test_vegetarian_is_a_hard_filter(self) -> None:
        constraints = Constraints(diet="veg")
        survivors, report = allowed_indices(self.dishes, constraints)
        self.assertEqual(len(survivors), 100)
        self.assertTrue(all(self.dishes[i].is_veg for i in survivors))
        self.assertIn("vegetarian only", report.applied)

    def test_nonveg_is_also_a_hard_filter(self) -> None:
        """Symmetric with vegetarian.

        A soft penalty could not carry this: bi-encoders embed "not vegetarian"
        close to "vegetarian", so the retriever ranks vegetarian dishes top for
        that query and a -0.30 diet penalty cannot close the relevance gap.
        """
        survivors, report = allowed_indices(self.dishes, Constraints(diet="nonveg"))
        self.assertEqual(len(survivors), 55)
        self.assertTrue(all(not self.dishes[i].is_veg for i in survivors))
        self.assertIn("non-vegetarian only", report.applied)

    def test_allergen_exclusion_is_hard(self) -> None:
        constraints = Constraints(tags_exclude={"seafood"})
        survivors, _ = allowed_indices(self.dishes, constraints)
        self.assertTrue(all("seafood" not in self.dishes[i].tags for i in survivors))
        self.assertLess(len(survivors), len(self.dishes))

    def test_strict_health_allergens_are_hard(self) -> None:
        strict = health.allergen_tags_for(["nut_allergy", "egg_allergy"])
        survivors, report = allowed_indices(self.dishes, Constraints(), strict_allergens=strict)
        for i in survivors:
            self.assertNotIn("nuts", self.dishes[i].tags)
            self.assertNotIn("egg", self.dishes[i].tags)
        self.assertTrue(report.applied)

    def test_non_allergen_exclusion_is_soft(self) -> None:
        """"not fried" should rank down, not delete half the menu."""
        survivors, report = allowed_indices(self.dishes, Constraints(tags_exclude={"deep_fried"}))
        self.assertEqual(len(survivors), len(self.dishes))
        self.assertEqual(report.applied, [])

    def test_spice_ceiling_is_a_hard_filter(self) -> None:
        """As a soft penalty alone, a highly relevant High-spice dish still
        surfaced for "not spicy"."""
        constraints = Constraints(spice_ceiling=SPICE_ORDER["Low"])
        survivors, report = allowed_indices(self.dishes, constraints)
        self.assertEqual(len(survivors), 87)  # 56 None + 31 Low
        for i in survivors:
            self.assertLessEqual(self.dishes[i].spice_rank, SPICE_ORDER["Low"])
        self.assertIn("spice up to Low", report.applied)

    def test_spice_floor_is_a_hard_filter(self) -> None:
        constraints = Constraints(spice_floor=SPICE_ORDER["Medium"])
        survivors, report = allowed_indices(self.dishes, constraints)
        self.assertEqual(len(survivors), 68)  # 54 Medium + 14 High
        self.assertIn("spice at least Medium", report.applied)

    def test_exact_spice_band(self) -> None:
        constraints = Constraints(
            spice_floor=SPICE_ORDER["Medium"], spice_ceiling=SPICE_ORDER["Medium"]
        )
        survivors, report = allowed_indices(self.dishes, constraints)
        self.assertEqual(len(survivors), 54)
        self.assertIn("spice = Medium", report.applied)

    def test_spice_filter_relaxes_when_too_narrow(self) -> None:
        """No dish is "Very High", so that band must relax rather than empty the
        results."""
        constraints = Constraints(
            spice_floor=SPICE_ORDER["Very High"], spice_ceiling=SPICE_ORDER["Very High"]
        )
        survivors, report = allowed_indices(self.dishes, constraints)
        self.assertEqual(len(survivors), len(self.dishes))
        self.assertTrue(report.relaxed)
        self.assertEqual(report.applied, [])

    def test_spice_and_diet_filters_compose(self) -> None:
        constraints = Constraints(diet="veg", spice_ceiling=SPICE_ORDER["Low"])
        survivors, report = allowed_indices(self.dishes, constraints)
        for i in survivors:
            self.assertTrue(self.dishes[i].is_veg)
            self.assertLessEqual(self.dishes[i].spice_rank, SPICE_ORDER["Low"])
        self.assertEqual(len(report.applied), 2)

    def test_decisive_single_category_is_filtered(self) -> None:
        survivors, report = allowed_indices(
            self.dishes, Constraints(categories_include={"Drinks"})
        )
        self.assertEqual(len(survivors), 17)
        self.assertIn("category = Drinks", report.applied)

    def test_category_filter_relaxes_when_too_narrow(self) -> None:
        """A category with too few survivors must degrade to ranking, never to
        an empty result page."""
        constraints = Constraints(categories_include={"Snacks"})  # only 1 dish
        survivors, report = allowed_indices(self.dishes, constraints)
        self.assertEqual(len(survivors), len(self.dishes))
        self.assertTrue(report.relaxed)

    def test_combined_filters_intersect(self) -> None:
        constraints = Constraints(diet="veg", tags_exclude={"coconut"})
        survivors, _ = allowed_indices(self.dishes, constraints)
        for i in survivors:
            self.assertTrue(self.dishes[i].is_veg)
            self.assertNotIn("coconut", self.dishes[i].tags)

    def test_no_constraints_keeps_everything(self) -> None:
        survivors, report = allowed_indices(self.dishes, Constraints())
        self.assertEqual(len(survivors), len(self.dishes))
        self.assertEqual(report.removed, 0)


class TestAdditiveScoring(RankingTestCase):
    def test_relevance_is_the_base(self) -> None:
        total, signals, _ = score_dish(
            self.dish("Dhal Curry"), 0.75, Constraints(), self.settings
        )
        self.assertEqual(len(signals), 1)
        self.assertAlmostEqual(total, 0.75)

    def test_regression_signals_do_not_annihilate(self) -> None:
        """The old pipeline multiplied penalties: 0.3 * 0.15 * 0.1 = 0.0045, a
        200x cut from three mild signals. Additive scoring stays bounded."""
        constraints = Constraints(
            categories_include={"Desserts"},
            tags_include={"street_food"},
            meal_times={"Breakfast"},
            spice_ceiling=SPICE_ORDER["Low"],
        )
        dish = self.dish("Devilled Pork")  # violates all four
        total, signals, _ = score_dish(dish, 0.8, constraints, self.settings)
        self.assertGreaterEqual(len(signals), 5)
        # Heavily penalised, but still on a comparable scale - not annihilated.
        self.assertGreater(total, -1.5)
        self.assertLess(total, 0.4)

    def test_every_signal_is_attributable(self) -> None:
        """Each contribution must be recoverable, which the old multiplicative
        chain made impossible."""
        total, signals, _ = score_dish(
            self.dish("Dhal Curry"),
            0.7,
            Constraints(diet="veg", spice_ceiling=SPICE_ORDER["Low"], meal_times={"Lunch"}),
            self.settings,
        )
        self.assertAlmostEqual(total, sum(s.contribution for s in signals))
        names = {s.name for s in signals}
        self.assertIn("relevance", names)
        self.assertIn("diet", names)
        self.assertIn("spice", names)

    def test_spice_penalty_scales_with_distance(self) -> None:
        """"not spicy": Medium should be penalised less than High."""
        constraints = Constraints(spice_ceiling=SPICE_ORDER["Low"])
        medium, _, _ = score_dish(self.dish("Chicken Curry"), 0.8, constraints, self.settings)
        high, _, _ = score_dish(self.dish("Devilled Pork"), 0.8, constraints, self.settings)
        self.assertGreater(medium, high)

    def test_spice_within_band_is_rewarded(self) -> None:
        constraints = Constraints(spice_ceiling=SPICE_ORDER["Low"])
        total, signals, _ = score_dish(self.dish("Dhal Curry"), 0.8, constraints, self.settings)
        spice = next(s for s in signals if s.name == "spice")
        self.assertGreater(spice.contribution, 0)

    def test_generic_meal_time_is_discounted(self) -> None:
        """A dish labelled "Any" is weaker evidence for "breakfast" than a dish
        labelled Breakfast - 101 of 155 dishes are "Any"."""
        constraints = Constraints(meal_times={"Breakfast"})
        specific, _, _ = score_dish(self.dish("Kola Kenda"), 0.8, constraints, self.settings)
        generic, _, _ = score_dish(self.dish("Dhal Curry"), 0.8, constraints, self.settings)
        self.assertGreater(specific, generic)

    def test_exact_name_match_dominates(self) -> None:
        low_relevance_exact, _, _ = score_dish(
            self.dish("Watalappan"), 0.30, Constraints(), self.settings, name_match_kind="exact"
        )
        high_relevance_no_name, _, _ = score_dish(
            self.dish("Kokis"), 0.70, Constraints(), self.settings
        )
        self.assertGreater(low_relevance_exact, high_relevance_no_name)

    def test_partial_name_is_weaker_than_exact(self) -> None:
        exact, _, _ = score_dish(
            self.dish("Watalappan"), 0.5, Constraints(), self.settings, name_match_kind="exact"
        )
        partial, _, _ = score_dish(
            self.dish("Watalappan"), 0.5, Constraints(), self.settings, name_match_kind="partial"
        )
        self.assertGreater(exact, partial)

    def test_tag_bonus_scales_with_coverage(self) -> None:
        one_of_two = Constraints(tags_include={"seafood", "street_food"})
        both = Constraints(tags_include={"seafood"})
        partial, _, _ = score_dish(self.dish("Crab Curry"), 0.8, one_of_two, self.settings)
        full, _, _ = score_dish(self.dish("Crab Curry"), 0.8, both, self.settings)
        self.assertGreater(full, partial)

    def test_soft_excluded_tag_penalised_not_removed(self) -> None:
        constraints = Constraints(tags_exclude={"deep_fried"})
        total, signals, _ = score_dish(self.dish("Fish Cutlet"), 0.8, constraints, self.settings)
        self.assertIn("excluded_tags", {s.name for s in signals})
        self.assertLess(total, 0.8)

    def test_category_mismatch_is_penalised(self) -> None:
        constraints = Constraints(categories_include={"Drinks"})
        drink, _, _ = score_dish(self.dish("Ceylon Tea"), 0.8, constraints, self.settings)
        food, _, _ = score_dish(self.dish("Chicken Kottu"), 0.8, constraints, self.settings)
        self.assertGreater(drink, food)


class TestHealthPenalties(RankingTestCase):
    def test_danger_outranked_by_safe_alternative(self) -> None:
        dish = self.dish("Crab Curry")
        warnings = health.evaluate(dish.tags, dish.spicy_level, ["seafood_allergy"])
        flagged, signals, severity = score_dish(
            dish, 0.9, Constraints(), self.settings, warnings=warnings
        )
        safe, _, _ = score_dish(self.dish("Dhal Curry"), 0.6, Constraints(), self.settings)
        self.assertEqual(severity, "danger")
        self.assertIn("health_danger", {s.name for s in signals})
        self.assertGreater(safe, flagged)

    def test_caution_penalty_is_milder_than_danger(self) -> None:
        dish = self.dish("Chicken Curry")
        caution = health.evaluate(dish.tags, dish.spicy_level, ["kidney_disease"])
        self.assertTrue(caution)
        cautioned, _, severity = score_dish(
            dish, 0.8, Constraints(), self.settings, warnings=caution
        )
        self.assertEqual(severity, "caution")
        self.assertGreater(cautioned, 0.8 + self.settings.health_danger_penalty)

    def test_no_warnings_no_penalty(self) -> None:
        total, signals, severity = score_dish(
            self.dish("Dhal Curry"), 0.8, Constraints(), self.settings, warnings=[]
        )
        self.assertIsNone(severity)
        self.assertNotIn("health_danger", {s.name for s in signals})


class TestEndToEndConstraints(RankingTestCase):
    """Query string -> constraints -> filter + score, the real path."""

    def rank(self, query: str, relevance: float = 0.8) -> list[str]:
        analyzed = self.analyzer.analyze(query)
        survivors, _ = allowed_indices(self.dishes, analyzed.constraints)
        scored = []
        for i in survivors:
            total, _, _ = score_dish(
                self.dishes[i], relevance, analyzed.constraints, self.settings
            )
            scored.append((total, self.dishes[i].name))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [name for _, name in scored]

    def test_no_seafood_removes_all_seafood(self) -> None:
        results = self.rank("curry without seafood")
        for name in results:
            self.assertNotIn("seafood", self.corpus.get(name).tags)

    def test_vegetarian_query_returns_only_vegetarian(self) -> None:
        for name in self.rank("vegetarian breakfast"):
            self.assertTrue(self.corpus.get(name).is_veg)

    def test_not_vegetarian_returns_only_non_vegetarian(self) -> None:
        results = self.rank("not vegetarian dinner")
        self.assertTrue(results)
        for name in results:
            self.assertFalse(self.corpus.get(name).is_veg)

    def test_mild_query_puts_mild_dishes_first(self) -> None:
        top = self.rank("not spicy food")[:15]
        for name in top:
            self.assertLessEqual(self.corpus.get(name).spice_rank, SPICE_ORDER["Low"])

    def test_drinks_query_returns_only_drinks(self) -> None:
        results = self.rank("something cold to drink")
        self.assertTrue(results)
        for name in results:
            self.assertEqual(self.corpus.get(name).category, "Drinks")

    def test_cheap_query_prefers_low_price(self) -> None:
        top = self.rank("cheap street food")[:10]
        self.assertTrue(all(self.corpus.get(n).price_range == "Low" for n in top))


if __name__ == "__main__":
    unittest.main(verbosity=2)
