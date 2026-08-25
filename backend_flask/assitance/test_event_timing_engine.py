import unittest
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from flask import Flask
from app import bp
from event_timing_engine import (
    get_time_periods,
    evaluate_activity_timing,
    calculate_timing_score,
    check_activity_time_feasibility,
    generate_activity_time_window,
    build_event_timing_summary
)


class TestEventTimingStep6(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()

    def test_01_time_period_generation(self):
        periods = get_time_periods()
        required = ["early_morning", "morning", "midday", "afternoon", "evening"]
        for p in required:
            self.assertIn(p, periods)

    def test_02_best_time_matching(self):
        act = {"best_time": "early_morning"}
        exact = evaluate_activity_timing(act, "early_morning")
        adjacent = evaluate_activity_timing(act, "morning")
        self.assertEqual(exact, 100.0)
        self.assertEqual(adjacent, 75.0)

    def test_03_timing_score_calculation(self):
        score = calculate_timing_score(100.0, 90.0, 85.0, 90.0, 90.0)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_04_weather_timing_adjustment(self):
        score = calculate_timing_score(80.0, weather_timing_score=95.0)
        self.assertGreater(score, 70)

    def test_05_crowd_timing_adjustment(self):
        score_low = calculate_timing_score(80.0, crowd_timing_score=60.0)
        score_high = calculate_timing_score(80.0, crowd_timing_score=95.0)
        self.assertGreater(score_high, score_low)

    def test_06_safety_timing_adjustment(self):
        score = calculate_timing_score(80.0, safety_timing_score=90.0)
        self.assertGreaterEqual(score, 70)

    def test_07_travel_time_feasibility(self):
        feasible, reason = check_activity_time_feasibility(6.0, 3.0, arrival_hour=11.0)
        self.assertFalse(feasible)
        self.assertIn("impractical", reason)

    def test_08_activity_duration_formatting(self):
        time_str = generate_activity_time_window(6.5, 4.0)
        self.assertEqual(time_str, "06:30-10:30")

    def test_09_non_overlapping_activities(self):
        acts = [
            {"name": "Hiking", "best_time": "early_morning", "duration_hours": 4, "categories": ["hiking"]},
            {"name": "Factory Visit", "best_time": "morning", "duration_hours": 2, "categories": ["nature"]}
        ]
        res = build_event_timing_summary("Nuwara Eliya", acts, {"estimated_travel_time_hours": 1.0, "origin": "Nuwara Eliya"}, {"score": 90}, {"crowd_score": 90, "crowd_level": "Low", "safety_score": 90})
        sched = res["daily_schedule"]
        self.assertEqual(len(sched), 2)
        self.assertEqual(sched[0]["time"], "06:30-10:30")
        self.assertEqual(sched[1]["time"], "11:00-13:00")

    def test_10_daily_schedule_generation(self):
        acts = [{"name": "Fort Tour", "best_time": "afternoon", "duration_hours": 2.5, "categories": ["heritage"]}]
        res = build_event_timing_summary("Galle", acts, {"estimated_travel_time_hours": 2.0}, {"score": 85}, {"crowd_score": 85, "crowd_level": "Low", "safety_score": 85})
        self.assertIn("daily_schedule", res)
        self.assertGreater(len(res["daily_schedule"]), 0)

    def test_11_infeasible_activity_detection(self):
        feasible, reason = check_activity_time_feasibility(19.0, 4.0, arrival_hour=8.0)
        self.assertFalse(feasible)
        self.assertIn("operating hours", reason)

    def test_12_early_morning_activity(self):
        act = {"name": "Horton Plains", "best_time": "early_morning", "duration_hours": 4, "categories": ["nature"]}
        res = build_event_timing_summary("Nuwara Eliya", [act], {"estimated_travel_time_hours": 1.0, "origin": "Nuwara Eliya"}, {"score": 90}, {"crowd_score": 90, "crowd_level": "Low", "safety_score": 90})
        self.assertEqual(res["best_time_period"], "early_morning")

    def test_13_afternoon_activity(self):
        act = {"name": "Sunset Walk", "best_time": "afternoon", "duration_hours": 2, "categories": ["relaxing"]}
        res = build_event_timing_summary("Galle", [act], {"estimated_travel_time_hours": 1.0}, {"score": 85}, {"crowd_score": 85, "crowd_level": "Low", "safety_score": 85})
        self.assertIsNotNone(res["best_activity_time"])

    def test_14_api_payload_integration(self):
        res = self.client.post("/recommend", json={"user_text": "nature"})
        self.assertEqual(res.status_code, 200)
        first = res.get_json()["recommendations"][0]
        self.assertIn("event_timing", first)
        et = first["event_timing"]
        self.assertIn("best_activity_time", et)
        self.assertIn("best_time_period", et)
        self.assertIn("daily_schedule", et)
        self.assertEqual(et["data_source"], "Research Benchmark Estimate")

    def test_15_regression_compatibility(self):
        res = self.client.post("/recommend", json={"user_text": "nature"})
        self.assertEqual(res.status_code, 200)
        first = res.get_json()["recommendations"][0]
        required = [
            "place", "score", "crowd", "crowd_label", "weather", "desc",
            "preference_match", "recommendation_reason", "weather_suitability",
            "travel_transport", "crowd_safety", "activity_recommendations"
        ]
        for f in required:
            self.assertIn(f, first)


if __name__ == "__main__":
    unittest.main()
