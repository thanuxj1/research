import unittest
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from flask import Flask
from app import bp
from final_recommendation_engine import (
    classify_decision_level,
    calculate_overall_score,
    generate_why_recommended,
    identify_tradeoffs,
    generate_ai_advantages,
    build_final_recommendation
)


class TestFinalRecommendationStep7(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()

    def test_01_score_calculation(self):
        score = calculate_overall_score(95, 90, 85, 90, 95, 90)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertEqual(score, 91)

    def test_02_weight_distribution(self):
        # 0.20 + 0.15 + 0.15 + 0.20 + 0.15 + 0.15 = 1.00
        score_all_100 = calculate_overall_score(100, 100, 100, 100, 100, 100)
        self.assertEqual(score_all_100, 100)

    def test_03_ranking(self):
        res = self.client.post("/recommend", json={"user_text": "nature"})
        self.assertEqual(res.status_code, 200)
        recs = res.get_json()["recommendations"]
        for i in range(len(recs) - 1):
            self.assertGreaterEqual(recs[i]["ai_recommendation"]["overall_score"], recs[i+1]["ai_recommendation"]["overall_score"])

    def test_04_decision_levels(self):
        self.assertEqual(classify_decision_level(95), "Highly Recommended")
        self.assertEqual(classify_decision_level(85), "Recommended")
        self.assertEqual(classify_decision_level(75), "Suitable")
        self.assertEqual(classify_decision_level(65), "Consider")
        self.assertEqual(classify_decision_level(50), "Not Recommended")

    def test_05_reason_generation(self):
        reasons = generate_why_recommended("Kandy", 90, 90, 85, 90, 90, 90)
        self.assertGreater(len(reasons), 0)
        self.assertTrue(any("preference" in r.lower() for r in reasons))

    def test_06_tradeoff_generation(self):
        tradeoffs = identify_tradeoffs("Nuwara Eliya", 95, 90, 60, 90, 90, 90, travel_time_hours=3.8, travel_time_str="3h 47m")
        self.assertGreater(len(tradeoffs), 0)
        self.assertTrue(any("travel time" in t.lower() for t in tradeoffs))

    def test_07_ai_advantage_generation(self):
        advs = generate_ai_advantages()
        self.assertEqual(len(advs), 5)
        self.assertTrue(any("telemetry" in a.lower() for a in advs))

    def test_08_missing_partial_component_data(self):
        score = calculate_overall_score(None, None, None, None, None, None)
        self.assertEqual(score, 85)

    def test_09_score_normalization(self):
        score_high = calculate_overall_score(150, 150, 150, 150, 150, 150)
        score_low = calculate_overall_score(-50, -50, -50, -50, -50, -50)
        self.assertEqual(score_high, 100)
        self.assertEqual(score_low, 0)

    def test_10_api_integration(self):
        res = self.client.post("/recommend", json={"user_text": "nature"})
        self.assertEqual(res.status_code, 200)
        first = res.get_json()["recommendations"][0]
        self.assertIn("ai_recommendation", first)
        ai_rec = first["ai_recommendation"]
        self.assertIn("overall_score", ai_rec)
        self.assertIn("rank", ai_rec)
        self.assertIn("decision", ai_rec)
        self.assertIn("why_recommended", ai_rec)
        self.assertIn("tradeoffs", ai_rec)
        self.assertIn("ai_advantage", ai_rec)

    def test_11_backward_compatibility(self):
        res = self.client.post("/recommend", json={"user_text": "nature"})
        self.assertEqual(res.status_code, 200)
        first = res.get_json()["recommendations"][0]
        required = [
            "place", "score", "crowd", "crowd_label", "weather", "desc",
            "preference_match", "recommendation_reason", "weather_suitability",
            "travel_transport", "crowd_safety", "activity_recommendations", "event_timing"
        ]
        for f in required:
            self.assertIn(f, first)

    def test_12_score_equals_overall_score(self):
        res = self.client.post("/recommend", json={"user_text": "beach"})
        self.assertEqual(res.status_code, 200)
        first = res.get_json()["recommendations"][0]
        self.assertEqual(first["score"], first["ai_recommendation"]["overall_score"])

    def test_13_deterministic_score_non_override(self):
        item = {
            "place": "Galle",
            "preference_match": {"score": 90},
            "weather_suitability": {"score": 85},
            "travel_transport": {"transport_score": 88},
            "crowd_safety": {"overall_score": 90, "crowd_level": "Low"},
            "activity_recommendations": {"top_activity": {"score": 92}},
            "event_timing": {"timing_score": 90}
        }
        res = build_final_recommendation(item, 0, 15)
        self.assertIsInstance(res["overall_score"], int)

    def test_14_rank_assignment_accuracy(self):
        res = self.client.post("/recommend", json={"user_text": "cultural"})
        self.assertEqual(res.status_code, 200)
        recs = res.get_json()["recommendations"]
        for idx, rec in enumerate(recs):
            self.assertEqual(rec["ai_recommendation"]["rank"], idx + 1)

    def test_15_frontend_payload_compatibility(self):
        res = self.client.post("/recommend", json={"user_text": "hiking"})
        self.assertEqual(res.status_code, 200)
        ai_rec = res.get_json()["recommendations"][0]["ai_recommendation"]
        self.assertTrue(isinstance(ai_rec["why_recommended"], list))
        self.assertTrue(isinstance(ai_rec["tradeoffs"], list))
        self.assertTrue(isinstance(ai_rec["ai_advantage"], list))

    # ── BUG FIX SPECIFIC TEST CASES ──

    def test_16_quiet_cold_place_preference_ranking(self):
        payload = {
            "user_text": "i want to go to quiet cold place",
            "weather": {"rainfall_mm": 2, "temperature_c": 28.5},
            "crowd": {"month": 9, "day_of_week": 6, "is_weekend": 1, "lag_1": 100, "lag_2": 100, "lag_3": 100}
        }
        res = self.client.post("/recommend", json=payload)
        self.assertEqual(res.status_code, 200)
        recs = res.get_json()["recommendations"]
        rec_dict = {r["place"]: r for r in recs}

        nuwara = rec_dict["Nuwara Eliya"]
        galle = rec_dict["Galle"]
        mirissa = rec_dict["Mirissa"]
        bentota = rec_dict["Bentota"]
        ella = rec_dict["Ella"]

        # Preference scores
        self.assertGreater(nuwara["preference_match"]["score"], galle["preference_match"]["score"])
        self.assertGreater(nuwara["preference_match"]["score"], mirissa["preference_match"]["score"])
        self.assertGreater(nuwara["preference_match"]["score"], bentota["preference_match"]["score"])
        self.assertGreater(ella["preference_match"]["score"], galle["preference_match"]["score"])

        # Final overall recommendation scores
        self.assertGreater(nuwara["score"], galle["score"])
        self.assertGreater(nuwara["score"], mirissa["score"])
        self.assertGreater(nuwara["score"], bentota["score"])

        # Verify no equal fallback score of 65 across all places
        nuwara_score = nuwara["score"]
        galle_score = galle["score"]
        self.assertNotEqual(nuwara_score, galle_score)

        # Weather terminology check (must NOT be "Low")
        self.assertIn(nuwara["weather"], ["Good", "Excellent", "Moderate", "Poor"])
        self.assertNotEqual(nuwara["weather"], "Low")

    def test_17_cool_and_peaceful_destination(self):
        payload = {"user_text": "I want a cool and peaceful destination"}
        res = self.client.post("/recommend", json=payload)
        self.assertEqual(res.status_code, 200)
        recs = res.get_json()["recommendations"]
        top_place = recs[0]["place"]
        self.assertIn(top_place, ["Nuwara Eliya", "Ella"])

    def test_18_cold_low_crowd_place(self):
        payload = {"user_text": "cold low crowd place"}
        res = self.client.post("/recommend", json=payload)
        self.assertEqual(res.status_code, 200)
        recs = res.get_json()["recommendations"]
        top_place = recs[0]["place"]
        self.assertIn(top_place, ["Nuwara Eliya", "Ella"])

    def test_19_quiet_nature_place(self):
        payload = {"user_text": "quiet nature place"}
        res = self.client.post("/recommend", json=payload)
        self.assertEqual(res.status_code, 200)
        recs = res.get_json()["recommendations"]
        rec_dict = {r["place"]: r for r in recs}
        self.assertGreater(rec_dict["Ella"]["preference_match"]["score"], rec_dict["Bentota"]["preference_match"]["score"])

    def test_20_beach_with_low_crowds(self):
        payload = {"user_text": "beach with low crowds"}
        res = self.client.post("/recommend", json=payload)
        self.assertEqual(res.status_code, 200)
        recs = res.get_json()["recommendations"]
        top_place = recs[0]["place"]
        self.assertIn(top_place, ["Mirissa", "Bentota", "Trincomalee", "Hikkaduwa", "Arugam Bay", "Galle"])


if __name__ == "__main__":
    unittest.main()
