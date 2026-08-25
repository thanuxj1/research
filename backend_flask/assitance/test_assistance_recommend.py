import unittest
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from flask import Flask
from app import bp, parse_user_preferences


class TestAssistanceRecommendStep1(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()

    def _post_recommend(self, payload):
        res = self.client.post("/recommend", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("recommendations", data)
        self.assertIsInstance(data["recommendations"], list)
        return data["recommendations"]

    def test_01_empty_preference(self):
        # 1. Empty preference handling
        recs = self._post_recommend({"user_text": ""})
        self.assertGreater(len(recs), 0)
        first = recs[0]
        self.assertIn("preference_match", first)
        self.assertIn("recommendation_reason", first)

    def test_02_nature_preference(self):
        # 2. Nature preference extraction
        extracted = parse_user_preferences("I want quiet nature and green scenery")
        self.assertIn("nature", extracted)
        recs = self._post_recommend({"user_text": "I want nature"})
        self.assertGreater(len(recs), 0)
        # Check that top nature destinations match
        top_recs = recs[:5]
        matched_any = any("nature" in r["preference_match"]["matched"] for r in top_recs)
        self.assertTrue(matched_any)

    def test_03_beach_preference(self):
        # 3. Beach preference extraction
        extracted = parse_user_preferences("I want golden beaches and ocean views")
        self.assertIn("beach", extracted)

    def test_04_low_crowd_preference(self):
        # 4. Low crowd preference extraction
        extracted = parse_user_preferences("I want peaceful places with low crowd")
        self.assertIn("low_crowd", extracted)
        recs = self._post_recommend({"user_text": "I want low crowd places"})
        first = recs[0]
        reasons = first["recommendation_reason"]
        self.assertTrue(any("crowd" in r.lower() for r in reasons))

    def test_05_multiple_preferences(self):
        # 5. Multiple preferences extraction
        extracted = parse_user_preferences("I want cool weather and mountains with photography")
        self.assertIn("cool_weather", extracted)
        self.assertIn("mountains", extracted)
        self.assertIn("photography", extracted)

    def test_06_planned_date_processing(self):
        # 6. Planned date / crowd telemetry input
        payload = {
            "user_text": "nature",
            "crowd": {"month": 12, "day_of_week": 6, "is_weekend": 1, "lag_1": 100, "lag_2": 100, "lag_3": 100}
        }
        recs = self._post_recommend(payload)
        self.assertGreater(len(recs), 0)

    def test_07_recommendation_ranking(self):
        # 7. Recommendation ranking (descending score order)
        recs = self._post_recommend({"user_text": "nature"})
        scores = [r["score"] for r in recs]
        sorted_scores = sorted(scores, reverse=True)
        self.assertEqual(scores, sorted_scores)

    def test_08_preference_match_score(self):
        # 8. Preference-match score structure
        recs = self._post_recommend({"user_text": "nature and cool weather"})
        first = recs[0]
        pm = first["preference_match"]
        self.assertIn("matched", pm)
        self.assertIn("score", pm)
        self.assertIsInstance(pm["score"], int)
        self.assertGreaterEqual(pm["score"], 0)
        self.assertLessEqual(pm["score"], 100)

    def test_09_recommendation_reasons(self):
        # 9. Recommendation reasons list
        recs = self._post_recommend({"user_text": "cool weather and mountains"})
        first = recs[0]
        reasons = first["recommendation_reason"]
        self.assertIsInstance(reasons, list)
        self.assertGreater(len(reasons), 0)
        self.assertIsInstance(reasons[0], str)

    def test_10_api_backward_compatibility(self):
        # 10. Existing API compatibility (place, score, crowd, crowd_label, weather, desc)
        recs = self._post_recommend({"user_text": "nature"})
        first = recs[0]
        required_keys = ["place", "score", "crowd", "crowd_label", "weather", "desc", "preference_match", "recommendation_reason"]
        for key in required_keys:
            self.assertIn(key, first)


if __name__ == "__main__":
    unittest.main()
