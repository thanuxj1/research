import unittest
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from flask import Flask
from app import bp
from event_activity_engine import (
    get_destination_activities,
    match_activity_preferences,
    evaluate_activity_weather,
    evaluate_activity_crowd,
    evaluate_activity_safety,
    calculate_activity_score,
    rank_activities,
    build_activity_recommendations
)


class TestEventActivityStep5(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()

    def test_01_destination_activity_lookup(self):
        acts = get_destination_activities("Nuwara Eliya")
        self.assertGreater(len(acts), 0)
        self.assertEqual(acts[0]["name"], "Tea Estate & Factory Visit")

    def test_02_activity_metadata(self):
        acts = get_destination_activities("Kandy")
        first = acts[0]
        required = ["name", "categories", "weather_sensitivity", "rain_tolerance", "crowd_tolerance", "typical_duration_hours"]
        for key in required:
            self.assertIn(key, first)

    def test_03_preference_matching(self):
        act = {"categories": ["nature", "hiking"]}
        high_match = match_activity_preferences(act, ["hiking"])
        low_match = match_activity_preferences(act, ["beach"])
        self.assertGreater(high_match, low_match)

    def test_04_weather_suitability_outdoor_vs_indoor(self):
        outdoor = {"rain_tolerance": "low"}
        score, warns = evaluate_activity_weather(outdoor, weather_suitability_score=90, rainfall_mm=12.0)
        self.assertLess(score, 90)
        self.assertGreater(len(warns), 0)

    def test_05_crowd_suitability_evaluation(self):
        act = {"crowd_tolerance": "low"}
        score, warns = evaluate_activity_crowd(act, crowd_score=80, crowd_level="High")
        self.assertLess(score, 80)
        self.assertGreater(len(warns), 0)

    def test_06_safety_suitability_evaluation(self):
        act = {"safety_requirement": "high"}
        score, warns = evaluate_activity_safety(act, safety_score=70, safety_level="Caution")
        self.assertLess(score, 70)
        self.assertGreater(len(warns), 0)

    def test_07_activity_score_calculation(self):
        score = calculate_activity_score(90, 85, 80, 85, 80)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_08_activity_ranking(self):
        top_act, acts = rank_activities(
            "Nuwara Eliya",
            ["hiking"],
            {"score": 90, "rainfall_mm": 2.0},
            {"transport_score": 85},
            {"crowd_score": 88, "crowd_level": "Low", "safety_score": 92, "safety_level": "Very Safe"}
        )
        self.assertEqual(top_act["name"], "Horton Plains & World's End Hiking")
        self.assertEqual(acts[0]["name"], top_act["name"])

    def test_09_top_activity_selection(self):
        res = build_activity_recommendations(
            "Ella",
            ["hiking"],
            {"score": 90, "rainfall_mm": 2.0},
            {"transport_score": 85},
            {"crowd_score": 88, "crowd_level": "Low", "safety_score": 90, "safety_level": "Very Safe"}
        )
        self.assertIsNotNone(res["top_activity"])
        self.assertIn("name", res["top_activity"])

    def test_10_unsuitable_weather_warning(self):
        outdoor = {"rain_tolerance": "low"}
        _, warns = evaluate_activity_weather(outdoor, weather_suitability_score=80, rainfall_mm=15.0)
        self.assertTrue(any("rainfall" in w.lower() for w in warns))

    def test_11_high_crowd_warning(self):
        act = {"crowd_tolerance": "low"}
        _, warns = evaluate_activity_crowd(act, crowd_score=50, crowd_level="High")
        self.assertTrue(any("crowd" in w.lower() for w in warns))

    def test_12_safety_warning(self):
        act = {"safety_requirement": "high"}
        _, warns = evaluate_activity_safety(act, safety_score=50, safety_level="Caution")
        self.assertTrue(any("caution" in w.lower() for w in warns))

    def test_13_unknown_destination_handling(self):
        acts = get_destination_activities("Unknown Place")
        self.assertGreater(len(acts), 0)
        self.assertIn("Sightseeing", acts[0]["name"])

    def test_14_api_payload_integration(self):
        res = self.client.post("/recommend", json={"user_text": "hiking"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        first = data["recommendations"][0]
        self.assertIn("activity_recommendations", first)
        act_rec = first["activity_recommendations"]
        self.assertIn("top_activity", act_rec)
        self.assertIn("activities", act_rec)
        self.assertEqual(act_rec["data_source"], "Research Benchmark Estimate")

    def test_15_regression_compatibility(self):
        res = self.client.post("/recommend", json={"user_text": "nature"})
        self.assertEqual(res.status_code, 200)
        first = res.get_json()["recommendations"][0]
        required = [
            "place", "score", "crowd", "crowd_label", "weather", "desc",
            "preference_match", "recommendation_reason", "weather_suitability",
            "travel_transport", "crowd_safety"
        ]
        for f in required:
            self.assertIn(f, first)


if __name__ == "__main__":
    unittest.main()
