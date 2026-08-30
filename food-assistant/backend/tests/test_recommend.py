"""Recommender tests.

XGBoost is not importable here, so these cover the rule-based path and the
degradation contract - which is exactly the path the original code did not have:
it swallowed any prediction failure into `score = 0.0`, silently returning an
arbitrary ordering rather than reporting that the model was unavailable.

The encoder tests pin the label encoding against `LabelEncoder`'s documented
sorted-classes behaviour, since the integer codes must match what the pickled
model was trained on.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from app.config import Settings
from app.corpus import load_corpus
from app.recommend import FEATURE_COLUMNS, OrdinalEncoder, Recommender

DATA_PATH = Path(__file__).resolve().parent.parent / "sri_lankan_food_dataset.csv"


class TestOrdinalEncoder(unittest.TestCase):
    def test_classes_are_sorted(self) -> None:
        """Mirrors sklearn LabelEncoder, which sorts its classes. The codes must
        match what the model saw at fit time."""
        encoder = OrdinalEncoder(["Medium", "High", "Low"])
        self.assertEqual(encoder.classes, ["High", "Low", "Medium"])
        self.assertEqual(encoder.encode("High"), 0)
        self.assertEqual(encoder.encode("Medium"), 2)

    def test_deduplicates(self) -> None:
        self.assertEqual(len(OrdinalEncoder(["a", "a", "b"])), 2)

    def test_unknown_value_uses_default(self) -> None:
        encoder = OrdinalEncoder(["a", "b"])
        self.assertEqual(encoder.encode("zzz"), 0)
        self.assertEqual(encoder.encode("zzz", default=7), 7)

    def test_membership(self) -> None:
        encoder = OrdinalEncoder(["a"])
        self.assertIn("a", encoder)
        self.assertNotIn("b", encoder)


class RecommenderTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_corpus(DATA_PATH)
        cls.recommender = Recommender(cls.corpus, Settings())
        # Model intentionally not loaded: exercises the rules-only path.

    def names(self, payload) -> list[str]:
        return [r["name"] for r in payload["results"]]


class TestEncoding(RecommenderTestCase):
    def test_is_veg_encoding_matches_csv_spelling(self) -> None:
        """The CSV stores TRUE/FALSE, so those are the strings the model was fit
        on - not Python booleans."""
        encoder = self.recommender.encoders["is_veg"]
        self.assertEqual(encoder.classes, ["FALSE", "TRUE"])
        self.assertEqual(encoder.encode("FALSE"), 0)
        self.assertEqual(encoder.encode("TRUE"), 1)

    def test_all_feature_columns_have_encoders(self) -> None:
        for column in FEATURE_COLUMNS:
            self.assertIn(column, self.recommender.encoders)

    def test_target_covers_every_dish(self) -> None:
        self.assertEqual(len(self.recommender.target), 155)

    def test_spice_encoding_is_alphabetical(self) -> None:
        self.assertEqual(
            self.recommender.encoders["spicy_level"].classes,
            ["High", "Low", "Medium", "None"],
        )


class TestDegradation(RecommenderTestCase):
    def test_missing_model_is_reported_not_hidden(self) -> None:
        recommender = Recommender(self.corpus, Settings(model_path=Path("/nonexistent.pkl")))
        self.assertFalse(recommender.load())
        self.assertIsNotNone(recommender.load_error)
        self.assertEqual(recommender.stats()["mode"], "rules only")

    def test_recommendations_still_returned_without_a_model(self) -> None:
        payload = self.recommender.recommend(category="Desserts", top_k=5)
        self.assertEqual(len(payload["results"]), 5)
        self.assertEqual(payload["engine"]["mode"], "rules only")

    def test_scores_are_not_all_zero(self) -> None:
        """The original returned score=0.0 for every dish when prediction failed,
        making the ranking arbitrary."""
        payload = self.recommender.recommend(category="Drinks", spicy_level="None", top_k=5)
        self.assertTrue(any(r["score"] > 0 for r in payload["results"]))


class TestPreferenceMatching(RecommenderTestCase):
    def test_category_preference_is_honoured(self) -> None:
        payload = self.recommender.recommend(category="Desserts", top_k=8)
        for result in payload["results"]:
            self.assertEqual(result["category"], "Desserts")

    def test_vegetarian_is_hard_filtered(self) -> None:
        payload = self.recommender.recommend(is_veg="True", top_k=10)
        for result in payload["results"]:
            self.assertEqual(result["is_veg"], "True")

    def test_spice_preference_ranks_first(self) -> None:
        payload = self.recommender.recommend(spicy_level="None", top_k=10)
        for result in payload["results"]:
            self.assertEqual(result["spicy_level"], "None")

    def test_any_meal_time_dish_satisfies_a_specific_request(self) -> None:
        payload = self.recommender.recommend(meal_time="Breakfast", top_k=10)
        for result in payload["results"]:
            self.assertTrue(
                "breakfast" in result["meal_time"].lower()
                or result["meal_time"].lower() == "any"
            )

    def test_combined_preferences(self) -> None:
        payload = self.recommender.recommend(
            category="Curries", is_veg="True", spicy_level="Low", top_k=5
        )
        for result in payload["results"]:
            self.assertEqual(result["category"], "Curries")
            self.assertEqual(result["is_veg"], "True")
            self.assertEqual(result["spicy_level"], "Low")

    def test_no_preferences_returns_results(self) -> None:
        payload = self.recommender.recommend(top_k=6)
        self.assertEqual(len(payload["results"]), 6)
        self.assertEqual(payload["preferences"], {})

    def test_respects_top_k(self) -> None:
        self.assertEqual(len(self.recommender.recommend(top_k=3)["results"]), 3)

    def test_explain_exposes_rule_breakdown(self) -> None:
        payload = self.recommender.recommend(category="Drinks", explain=True, top_k=3)
        explanation = payload["results"][0]["explanation"]
        self.assertIn("rule_score", explanation)
        self.assertIn("matched_preferences", explanation)
        self.assertEqual(explanation["source"], "rules only")
        self.assertIn("category", explanation["matched_preferences"])


class TestHealthIntegration(RecommenderTestCase):
    def test_warnings_are_attached(self) -> None:
        payload = self.recommender.recommend(
            category="Desserts", health_conditions=["diabetes"], top_k=8
        )
        self.assertTrue(any(r["warnings"] for r in payload["results"]))

    def test_strict_allergens_removes_dishes(self) -> None:
        payload = self.recommender.recommend(
            category="Curries",
            health_conditions=["seafood_allergy"],
            strict_allergens=True,
            top_k=20,
        )
        for result in payload["results"]:
            self.assertNotIn("seafood", result["tags"])

    def test_flagged_dishes_rank_lower(self) -> None:
        """A condition must be discriminating to reorder anything.

        `nut_allergy` splits the dessert set; `diabetes` does not, because every
        dish in the Desserts category carries `high_sugar` and so takes an
        identical penalty (see test_uniform_penalty_preserves_order).
        """
        plain = self.names(self.recommender.recommend(category="Desserts", top_k=24))
        with_allergy = self.names(
            self.recommender.recommend(
                category="Desserts", health_conditions=["nut_allergy"], top_k=24
            )
        )
        self.assertNotEqual(plain, with_allergy)
        nutty = [n for n in with_allergy if "nuts" in self.corpus.get(n).tags]
        self.assertTrue(nutty)
        # Every nut-containing dessert must sit below every nut-free one.
        first_nutty = min(with_allergy.index(n) for n in nutty)
        last_safe = max(
            with_allergy.index(n) for n in with_allergy if "nuts" not in self.corpus.get(n).tags
        )
        self.assertGreater(first_nutty, last_safe)

    def test_uniform_penalty_preserves_order(self) -> None:
        """Ordering must stay deterministic when every candidate ties.

        In rules-only mode a single stated preference gives every matching dish
        the same rule score, and a non-discriminating condition penalises them all
        equally. The result is an alphabetical tie-break rather than an arbitrary
        one. With the model loaded, its per-dish probability breaks these ties.
        """
        plain = self.names(self.recommender.recommend(category="Desserts", top_k=10))
        with_diabetes = self.names(
            self.recommender.recommend(
                category="Desserts", health_conditions=["diabetes"], top_k=10
            )
        )
        self.assertEqual(plain, with_diabetes)
        self.assertEqual(plain, sorted(plain))

    def test_response_is_json_serializable(self) -> None:
        import json

        json.dumps(
            self.recommender.recommend(
                category="Curries", health_conditions=["gout"], explain=True, top_k=5
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
