import unittest
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from flask import Flask
from app import bp
from crowd_safety_engine import (
    classify_crowd_level,
    calculate_crowd_score,
    calculate_safety_score,
    classify_safety_level,
    build_crowd_safety_summary
)


class TestCrowdSafetyStep4(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()

    def test_01_crowd_score_calculation(self):
        score = calculate_crowd_score(90.0, is_weekend=0)
        self.assertEqual(score, 88)

    def test_02_weekend_crowd_effect(self):
        weekday_score = calculate_crowd_score(90.0, is_weekend=0)
        weekend_score = calculate_crowd_score(90.0, is_weekend=1)
        self.assertEqual(weekend_score, weekday_score - 5)

    def test_03_weekday_crowd_effect(self):
        score = calculate_crowd_score(70.0, is_weekend=0)
        self.assertEqual(score, 95)

    def test_04_crowd_classification(self):
        self.assertEqual(classify_crowd_level(90.0), "Low")
        self.assertEqual(classify_crowd_level(130.0), "Moderate")
        self.assertEqual(classify_crowd_level(180.0), "High")
        self.assertEqual(classify_crowd_level(230.0), "Very High")

    def test_05_low_crowd(self):
        c_level = classify_crowd_level(85.0)
        self.assertEqual(c_level, "Low")

    def test_06_moderate_crowd(self):
        c_level = classify_crowd_level(125.0)
        self.assertEqual(c_level, "Moderate")

    def test_07_high_crowd(self):
        c_level = classify_crowd_level(190.0)
        self.assertEqual(c_level, "High")

    def test_08_very_high_crowd(self):
        c_level = classify_crowd_level(240.0)
        self.assertEqual(c_level, "Very High")

    def test_09_safety_score_calculation(self):
        score = calculate_safety_score("Nuwara Eliya", expected_crowd=90.0, transport_suitability="good")
        self.assertGreaterEqual(score, 85)

    def test_10_safety_classification(self):
        valid = {"Very Safe", "Safe", "Moderate", "Caution"}
        for score in [95, 80, 65, 50]:
            self.assertIn(classify_safety_level(score), valid)

    def test_11_crowd_safety_combined_score(self):
        res = build_crowd_safety_summary("Galle", expected_crowd=100.0, is_weekend=0, transport_suitability="good")
        expected_overall = int(round(res["crowd_score"] * 0.55 + res["safety_score"] * 0.45))
        self.assertEqual(res["overall_score"], expected_overall)

    def test_12_warning_generation(self):
        res = build_crowd_safety_summary("Galle", expected_crowd=230.0, is_weekend=1, transport_suitability="good")
        self.assertGreater(len(res["warnings"]), 0)
        self.assertTrue(any("crowd" in w.lower() for w in res["warnings"]))

    def test_13_destination_profile_handling(self):
        res_nuwara = build_crowd_safety_summary("Nuwara Eliya", expected_crowd=90.0)
        self.assertEqual(res_nuwara["safety_level"], "Very Safe")

    def test_14_api_payload_integration(self):
        res = self.client.post("/recommend", json={"user_text": "nature"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        first = data["recommendations"][0]
        self.assertIn("crowd_safety", first)
        cs = first["crowd_safety"]
        self.assertIn("crowd_score", cs)
        self.assertIn("crowd_level", cs)
        self.assertIn("safety_score", cs)
        self.assertIn("safety_level", cs)
        self.assertIn("overall_score", cs)

    def test_15_regression_compatibility(self):
        res = self.client.post("/recommend", json={"user_text": "nature"})
        self.assertEqual(res.status_code, 200)
        first = res.get_json()["recommendations"][0]
        required = [
            "place", "score", "crowd", "crowd_label", "weather", "desc",
            "preference_match", "recommendation_reason", "weather_suitability", "travel_transport"
        ]
        for f in required:
            self.assertIn(f, first)


if __name__ == "__main__":
    unittest.main()
