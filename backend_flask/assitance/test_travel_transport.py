import unittest
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from flask import Flask
from app import bp
from travel_transport_engine import (
    calculate_distance,
    estimate_travel_time,
    get_transport_options,
    calculate_transport_score,
    evaluate_transport_suitability,
    build_travel_transport_summary
)


class TestTravelTransportStep3(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()

    def test_01_colombo_to_kandy_distance(self):
        dist, is_est = calculate_distance("Colombo", "Kandy")
        self.assertEqual(dist, 115)
        self.assertFalse(is_est)

    def test_02_colombo_to_ella_distance(self):
        dist, is_est = calculate_distance("Colombo", "Ella")
        self.assertEqual(dist, 205)
        self.assertFalse(is_est)

    def test_03_car_travel_time(self):
        hours, formatted = estimate_travel_time(115, "car")
        self.assertEqual(hours, 2.56)
        self.assertEqual(formatted, "2h 34m")

    def test_04_bus_travel_time(self):
        hours, formatted = estimate_travel_time(115, "bus")
        self.assertEqual(hours, 3.29)
        self.assertEqual(formatted, "3h 17m")

    def test_05_train_travel_time(self):
        hours, formatted = estimate_travel_time(115, "train")
        self.assertEqual(hours, 2.88)
        self.assertEqual(formatted, "2h 53m")

    def test_06_multiple_transport_options(self):
        options = get_transport_options("Colombo", "Kandy", 115)
        self.assertEqual(len(options), 3)
        modes = [o["mode"] for o in options]
        self.assertIn("car", modes)
        self.assertIn("bus", modes)
        self.assertIn("train", modes)

    def test_07_transport_availability(self):
        summary = build_travel_transport_summary("Colombo", "Kandy", "car")
        self.assertEqual(summary["availability"], "high")
        self.assertEqual(summary["selected_transport_mode"], "car")

    def test_08_transport_score_bounds(self):
        for dist in [20, 65, 115, 205, 395]:
            score = calculate_transport_score(dist, dist / 45, "car", get_transport_options("Colombo", "Kandy", dist))
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)

    def test_09_suitability_classification(self):
        valid_suitabilities = {"excellent", "good", "moderate", "difficult"}
        for score in [95, 80, 60, 30]:
            suit = evaluate_transport_suitability(score)
            self.assertIn(suit, valid_suitabilities)

    def test_10_long_distance_warning(self):
        summary = build_travel_transport_summary("Colombo", "Jaffna", "car")
        self.assertGreater(len(summary["warnings"]), 0)
        self.assertTrue(any("far" in w.lower() or "long" in w.lower() for w in summary["warnings"]))

    def test_11_short_distance_destination(self):
        summary = build_travel_transport_summary("Colombo", "Bentota", "car")
        self.assertTrue(any("short travel time" in r.lower() for r in summary["reasons"]))

    def test_12_unknown_destination_fallback(self):
        dist, is_est = calculate_distance("Colombo", "UnknownLocationXYZ")
        self.assertEqual(dist, 150)
        self.assertTrue(is_est)

    def test_13_api_response_integration(self):
        payload = {"user_text": "nature", "origin": "Colombo", "transport_mode": "car"}
        res = self.client.post("/recommend", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        first = data["recommendations"][0]
        self.assertIn("travel_transport", first)
        tt = first["travel_transport"]
        self.assertEqual(tt["origin"], "Colombo")
        self.assertIn("distance_km", tt)
        self.assertIn("estimated_travel_time", tt)
        self.assertIn("transport_options", tt)

    def test_14_existing_step1_fields_intact(self):
        res = self.client.post("/recommend", json={"user_text": "nature"})
        self.assertEqual(res.status_code, 200)
        first = res.get_json()["recommendations"][0]
        required = ["place", "score", "crowd", "crowd_label", "weather", "desc", "preference_match", "recommendation_reason"]
        for f in required:
            self.assertIn(f, first)

    def test_15_existing_step2_weather_fields_intact(self):
        res = self.client.post("/recommend", json={"user_text": "nature"})
        self.assertEqual(res.status_code, 200)
        first = res.get_json()["recommendations"][0]
        self.assertIn("weather_suitability", first)
        ws = first["weather_suitability"]
        self.assertIn("score", ws)
        self.assertIn("suitability", ws)
        self.assertIn("temperature_c", ws)
        self.assertIn("rainfall_mm", ws)


if __name__ == "__main__":
    unittest.main()
