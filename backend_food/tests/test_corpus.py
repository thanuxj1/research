"""Corpus, tagging and health-engine tests. Stdlib only.

The `test_regression_*` cases pin false positives produced by the original
substring-based rules. Several of them were safety-relevant: an allergy sufferer
being told a dish is unsafe when it is not erodes trust in every other warning.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from app import health
from app.corpus import load_corpus, parse_meal_times
from app.data.taxonomy import MEAL_TIMES

DATA_PATH = Path(__file__).resolve().parent.parent / "sri_lankan_food_dataset.csv"


class CorpusTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_corpus(DATA_PATH)

    def dish(self, name: str):
        found = self.corpus.get(name)
        self.assertIsNotNone(found, f"missing dish: {name}")
        return found


class TestLoading(CorpusTestCase):
    def test_all_rows_loaded(self) -> None:
        self.assertEqual(len(self.corpus), 155)

    def test_every_dish_has_a_curated_description(self) -> None:
        for dish in self.corpus:
            with self.subTest(dish=dish.name):
                self.assertNotEqual(dish.description, "Traditional Sri Lankan food.")

    def test_is_veg_parsed_from_uppercase_csv_booleans(self) -> None:
        self.assertTrue(self.dish("Dhal Curry").is_veg)
        self.assertFalse(self.dish("Chicken Curry").is_veg)

    def test_veg_count_matches_dataset(self) -> None:
        self.assertEqual(sum(1 for d in self.corpus if d.is_veg), 100)

    def test_dense_text_is_prose_not_keyword_soup(self) -> None:
        text = self.dish("Dhal Curry").dense_text
        self.assertIn("Dhal Curry is a vegetarian Sri Lankan", text)
        # The old builder emitted "Meal time: Any. Spice: Low." field dumps.
        self.assertNotIn("Meal time:", text)
        self.assertNotIn("Spice:", text)

    def test_sparse_tokens_boost_the_name(self) -> None:
        dish = self.dish("Chicken Kottu")
        self.assertEqual(dish.sparse_tokens.count("kottu"), 3 + dish.description.lower().count("kottu"))


class TestMealTimes(CorpusTestCase):
    def test_any_expands_to_all(self) -> None:
        self.assertEqual(parse_meal_times("Any"), frozenset(MEAL_TIMES))

    def test_compound_label(self) -> None:
        self.assertEqual(parse_meal_times("Breakfast/Dinner"), frozenset({"Breakfast", "Dinner"}))
        self.assertEqual(parse_meal_times("Lunch/Dinner"), frozenset({"Lunch", "Dinner"}))

    def test_single_label(self) -> None:
        self.assertEqual(parse_meal_times("Breakfast"), frozenset({"Breakfast"}))

    def test_unknown_falls_back_to_all(self) -> None:
        self.assertEqual(parse_meal_times(""), frozenset(MEAL_TIMES))


class TestTagging(CorpusTestCase):
    def test_regression_eggplant_is_not_egg(self) -> None:
        """`"egg" in "eggplant curry"` is True as a substring. It must not be a tag."""
        self.assertNotIn("egg", self.dish("Eggplant Curry").tags)
        self.assertNotIn("egg", self.dish("Wambatu Moju (Eggplant Pickle)").tags)

    def test_real_egg_dishes_are_tagged(self) -> None:
        for name in ("Egg Hoppers", "Egg Curry", "Omelet", "Egg Roti"):
            with self.subTest(dish=name):
                self.assertIn("egg", self.dish(name).tags)

    def test_regression_coconut_milk_is_not_dairy(self) -> None:
        for name in ("Ala Hodi (Potato White Curry)", "Kiri Hodi", "Kiribath"):
            with self.subTest(dish=name):
                self.assertNotIn("dairy", self.dish(name).tags)

    def test_regression_soya_milk_is_not_dairy(self) -> None:
        self.assertNotIn("dairy", self.dish("Soya Milk").tags)
        self.assertIn("vegan", self.dish("Soya Milk").tags)

    def test_real_dairy_dishes_are_tagged(self) -> None:
        for name in ("Milk Tea", "Butter Cake", "Curd and Treacle", "Mango Lassi"):
            with self.subTest(dish=name):
                self.assertIn("dairy", self.dish(name).tags)

    def test_regression_sweet_potato_is_not_high_sugar(self) -> None:
        self.assertNotIn("high_sugar", self.dish("Boiled Sweet Potatoes").tags)

    def test_regression_sweet_spicy_dishes_are_not_high_sugar(self) -> None:
        """"Sweet spicy stir-fried chicken" is not a confectionery."""
        for name in ("Devilled Chicken", "Devilled Pork", "Devilled Prawns"):
            with self.subTest(dish=name):
                self.assertNotIn("high_sugar", self.dish(name).tags)

    def test_real_sugary_dishes_are_tagged(self) -> None:
        for name in ("Watalappan", "Kiri Toffee (Milk Toffee)", "Seeni Sambol", "Falooda"):
            with self.subTest(dish=name):
                self.assertIn("high_sugar", self.dish(name).tags)

    def test_regression_ginger_beer_is_not_alcohol(self) -> None:
        """Sri Lankan ginger beer is a soft drink; 'beer' was a substring trap."""
        self.assertNotIn("alcohol", self.dish("Ginger Beer").tags)

    def test_regression_vegetarian_dish_never_gets_meat_tags(self) -> None:
        """Polos Curry's description mentions a "meat-like texture"."""
        polos = self.dish("Polos Curry")
        self.assertTrue(polos.is_veg)
        for tag in ("chicken", "beef", "pork", "mutton", "seafood", "fish"):
            self.assertNotIn(tag, polos.tags)

    def test_regression_spicy_dish_is_not_beginner_friendly(self) -> None:
        """Crab Curry is described as "famous among tourists" but is High spice."""
        crab = self.dish("Crab Curry")
        self.assertNotIn("beginner_friendly", crab.tags)
        self.assertIn("must_try", crab.tags)

    def test_mild_dishes_can_be_beginner_friendly(self) -> None:
        self.assertIn("beginner_friendly", self.dish("Dhal Curry").tags)

    def test_vegan_derived_not_keyword_matched(self) -> None:
        # Vegetarian but contains dairy -> not vegan.
        self.assertNotIn("vegan", self.dish("Butter Cake").tags)
        # Vegetarian, no dairy or egg -> vegan.
        self.assertIn("vegan", self.dish("Gotukola Sambol (Pennywort Salad)").tags)

    def test_nonveg_dishes_are_high_protein(self) -> None:
        self.assertIn("high_protein", self.dish("Beef Curry").tags)

    def test_seafood_family_tags(self) -> None:
        crab = self.dish("Crab Curry")
        self.assertIn("crab", crab.tags)
        self.assertIn("seafood", crab.tags)
        cuttlefish = self.dish("Cuttlefish Curry")
        self.assertIn("cuttlefish", cuttlefish.tags)
        self.assertIn("seafood", cuttlefish.tags)


class TestFacets(CorpusTestCase):
    def test_facet_counts_match_dataset(self) -> None:
        facets = self.corpus.facets()
        self.assertEqual(facets["total"], 155)
        categories = {c["value"]: c["count"] for c in facets["categories"]}
        self.assertEqual(categories["Main Meals"], 40)
        self.assertEqual(categories["Curries"], 37)
        self.assertEqual(categories["Drinks"], 17)

    def test_facets_are_json_serializable(self) -> None:
        import json

        json.dumps(self.corpus.facets())


class TestHealthEngine(CorpusTestCase):
    def warnings_for(self, dish_name: str, conditions: list[str]):
        dish = self.dish(dish_name)
        return health.evaluate(dish.tags, dish.spicy_level, conditions)

    def test_regression_no_false_egg_warning_for_eggplant(self) -> None:
        self.assertEqual(self.warnings_for("Eggplant Curry", ["egg_allergy"]), [])

    def test_regression_no_false_lactose_warning_for_coconut_curry(self) -> None:
        self.assertEqual(
            self.warnings_for("Ala Hodi (Potato White Curry)", ["lactose_intolerance"]), []
        )

    def test_regression_no_false_diabetes_warning_for_sweet_potato(self) -> None:
        warnings = self.warnings_for("Boiled Sweet Potatoes", ["diabetes"])
        self.assertFalse([w for w in warnings if w.severity == "danger"])

    def test_seafood_allergy_flags_crab(self) -> None:
        warnings = self.warnings_for("Crab Curry", ["seafood_allergy"])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "danger")

    def test_diabetes_flags_watalappan(self) -> None:
        warnings = self.warnings_for("Watalappan", ["diabetes"])
        self.assertTrue(any(w.severity == "danger" for w in warnings))

    def test_spice_rule_fires_on_level_not_keyword(self) -> None:
        """The hypertension spice rule reads the structured `spicy_level`
        column, not the prose. Lunumiris is High in the dataset."""
        warnings = self.warnings_for("Lunumiris", ["hypertension"])
        self.assertTrue(any("spicy" in w.message.lower() for w in warnings))

    def test_structured_column_wins_over_prose(self) -> None:
        """Data-quality guard.

        The dataset and the curated prose disagree for a number of dishes:
        Chicken Curry and Crab Curry are both described as "High spice" but are
        recorded as Medium in the CSV. Ranking and health rules must key off the
        structured column, so the prose disagreement stays inert.
        """
        chicken = self.dish("Chicken Curry")
        self.assertEqual(chicken.spicy_level, "Medium")
        self.assertIn("High spice", chicken.description)
        self.assertFalse(
            any(
                "spicy" in w.message.lower()
                for w in health.evaluate(chicken.tags, chicken.spicy_level, ["hypertension"])
            )
        )

    def test_no_conditions_means_no_warnings(self) -> None:
        self.assertEqual(self.warnings_for("Crab Curry", []), [])

    def test_unknown_condition_is_ignored(self) -> None:
        self.assertEqual(self.warnings_for("Crab Curry", ["not_a_condition"]), [])

    def test_warnings_sorted_danger_first(self) -> None:
        warnings = self.warnings_for("Devilled Pork", ["high_cholesterol", "gout", "hypertension"])
        severities = [w.severity for w in warnings]
        self.assertEqual(severities, sorted(severities, key=lambda s: 0 if s == "danger" else 1))

    def test_worst_severity(self) -> None:
        self.assertEqual(
            health.worst_severity(self.warnings_for("Crab Curry", ["seafood_allergy"])), "danger"
        )
        self.assertIsNone(health.worst_severity([]))

    def test_allergen_tags_only_from_allergy_conditions(self) -> None:
        tags = health.allergen_tags_for(["seafood_allergy", "nut_allergy", "diabetes"])
        self.assertEqual(tags, {"seafood", "nuts"})

    def test_catalog_covers_every_condition(self) -> None:
        self.assertEqual(len(health.catalog()), len(health.CONDITIONS))
        self.assertEqual(
            {c["id"] for c in health.catalog()}, set(health.CONDITIONS_BY_ID)
        )

    def test_every_condition_reaches_at_least_one_dish(self) -> None:
        """A condition that can never fire is a dead rule."""
        for condition in health.CONDITIONS:
            with self.subTest(condition=condition.id):
                hits = sum(
                    1
                    for d in self.corpus
                    if health.evaluate(d.tags, d.spicy_level, [condition.id])
                )
                self.assertGreater(hits, 0, f"{condition.id} never fires")


if __name__ == "__main__":
    unittest.main(verbosity=2)
