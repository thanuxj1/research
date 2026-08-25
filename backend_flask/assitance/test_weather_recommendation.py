import unittest
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from flask import Flask
from app import bp
from weather_recommendation_engine import calculate_weather_suitability


class TestWeatherRecommendationStep2(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()

    def test_01_very_low_rainfall(self):
        res = calculate_weather_suitability("Galle", 25.0, 0.5)
        self.assertGreaterEqual(res["score"], 85)
        self.assertIn(res["suitability"], ["excellent", "good"])
        self.assertTrue(any("low rainfall" in r.lower() for r in res["reasons"]))

    def test_02_moderate_rainfall(self):
        res = calculate_weather_suitability("Galle", 25.0, 7.0)
        self.assertLess(res["score"], 95)
        self.assertIn(res["suitability"], ["good", "moderate"])

    def test_03_heavy_rainfall(self):
        res = calculate_weather_suitability("Galle", 25.0, 15.0)
        self.assertLess(res["score"], 70)
        self.assertTrue(any("rain" in r.lower() for r in res["reasons"]))

    def test_04_extreme_rainfall(self):
        res = calculate_weather_suitability("Galle", 25.0, 25.0)
        self.assertEqual(res["suitability"], "poor")
        self.assertTrue(any("heavy rainfall" in r.lower() for r in res["reasons"]))

    def test_05_comfortable_temperature(self):
        res = calculate_weather_suitability("Kandy", 22.0, 1.0)
        self.assertGreaterEqual(res["score"], 80)
        self.assertTrue(any("comfortable temperature" in r.lower() for r in res["reasons"]))

    def test_06_high_temperature(self):
        res = calculate_weather_suitability("Jaffna", 35.0, 1.0)
        self.assertLess(res["score"], 85)
        self.assertTrue(any("high temperature" in r.lower() for r in res["reasons"]))

    def test_07_low_temperature(self):
        res = calculate_weather_suitability("Bentota", 15.0, 1.0)
        self.assertIsInstance(res["reasons"], list)

    def test_08_mountain_destination_cool_weather(self):
        res = calculate_weather_suitability("Nuwara Eliya", 15.0, 1.0)
        self.assertGreaterEqual(res["score"], 85)
        self.assertTrue(any("cool temperature" in r.lower() for r in res["reasons"]))

    def test_09_beach_destination_heavy_rainfall(self):
        res = calculate_weather_suitability("Mirissa", 28.0, 22.0)
        self.assertEqual(res["suitability"], "poor")
        self.assertTrue(any("beach" in r.lower() and "rain" in r.lower() for r in res["reasons"]))

    def test_10_nature_destination_good_weather(self):
        res = calculate_weather_suitability("Ella", 21.0, 1.5)
        self.assertGreaterEqual(res["score"], 85)
        self.assertTrue(any("outdoor" in r.lower() or "comfortable" in r.lower() for r in res["reasons"]))

    def test_11_weather_score_range(self):
        for temp in [10, 18, 25, 32, 40]:
            for rain in [0, 2, 8, 15, 30]:
                res = calculate_weather_suitability("Ella", temp, rain)
                self.assertGreaterEqual(res["score"], 0)
                self.assertLessEqual(res["score"], 100)

    def test_12_suitability_labels_validity(self):
        valid_labels = {"excellent", "good", "moderate", "poor"}
        for place in ["Galle", "Nuwara Eliya", "Jaffna"]:
            res = calculate_weather_suitability(place, 25.0, 2.0)
            self.assertIn(res["suitability"], valid_labels)

    def test_13_reasons_generated(self):
        res = calculate_weather_suitability("Yala", 28.0, 2.0)
        self.assertIsInstance(res["reasons"], list)
        self.assertGreater(len(res["reasons"]), 0)

    def test_14_existing_fields_intact(self):
        res = self.client.post("/recommend", json={"user_text": "nature"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        recs = data["recommendations"]
        first = recs[0]
        required_fields = ["place", "score", "crowd", "crowd_label", "weather", "desc", "preference_match", "recommendation_reason", "weather_suitability"]
        for f in required_fields:
            self.assertIn(f, first)

    def test_15_full_api_integration(self):
        payload = {
            "user_text": "I want cool weather and nature",
            "weather": {"temperature_c": 21.0, "rainfall_mm": 1.5}
        }
        res = self.client.post("/recommend", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        recs = data["recommendations"]
        self.assertGreater(len(recs), 0)
        first = recs[0]
        ws = first["weather_suitability"]
        self.assertIn("score", ws)
        self.assertIn("condition", ws)
        self.assertIn("suitability", ws)
        self.assertIn("reasons", ws)


if __name__ == "__main__":
    unittest.main()
