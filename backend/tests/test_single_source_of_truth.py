"""
P5 regression test — ensures client-side risk arithmetic never creeps back.
IT22629180

If this test fails, someone has re-added scoring logic to the frontend.
The district risk model must have exactly ONE implementation: district_engine.py.
"""
import os


def test_no_client_side_risk_arithmetic():
    """The frontend must not contain any of the banned scoring symbols."""
    page1 = os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "src", "SafeTravelLK_Page1.jsx"
    )
    src = open(page1, encoding="utf-8").read()
    banned = ("wilsonLower", "BAYESIAN_ALPHA", "GLOBAL_PRIOR", "computeAllScores", "scoreDistrict")
    for symbol in banned:
        assert symbol not in src, (
            f"'{symbol}' found in SafeTravelLK_Page1.jsx — district risk must "
            f"come from the API only (district_engine.py). Remove the client-side scoring."
        )
