"""
Guard tests: the external-validity statistic, and the claim attached to it.

A hand-rolled correlation is only worth reporting if it is right, so this
checks it against cases with known answers -- perfect agreement, perfect
disagreement, ties, and too-small samples. scipy would have been easier and
would also have been a new dependency for one function.

The second half guards the CLAIM. Correlating against Google star ratings is
corroboration of the aggregate, not accuracy of any label, and the difference
is the whole reason open problem #1 still stands.

Run:  python -m pytest tests/test_external_validity.py -q
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from travellens import external_validity as EV  # noqa: E402


def test_perfect_agreement_and_disagreement():
    n = EV.MIN_PLACES + 3
    rising = list(range(n))
    falling = list(range(n))[::-1]
    assert EV._spearman(rising, rising) == 1.0
    assert EV._spearman(rising, falling) == -1.0


def test_a_known_value():
    """Textbook case: one adjacent swap in an otherwise perfect ranking.

    rho = 1 - 6*sum(d^2)/(n(n^2-1)); a single adjacent swap gives sum(d^2)=2,
    so with n=12 that is 1 - 12/1716 = 0.993.
    """
    n = 12
    a = list(range(n))
    b = list(range(n))
    b[4], b[5] = b[5], b[4]
    assert EV._spearman(a, b) == 0.993


def test_ties_use_average_ranks():
    """Ties must not be broken by input order, or the answer depends on how
    the rows happened to be sorted."""
    a = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6]
    b = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6]
    assert EV._spearman(a, b) == 1.0
    assert EV._ranks([5, 5, 1]) == [2.5, 2.5, 1.0]


def test_too_few_places_returns_nothing():
    """A correlation over a handful of places is noise wearing a number."""
    assert EV._spearman([1, 2, 3], [3, 2, 1]) is None
    assert EV._spearman(list(range(EV.MIN_PLACES - 1)),
                        list(range(EV.MIN_PLACES - 1))) is None


def test_a_flat_variable_has_no_correlation():
    """Every place rated 4.5 tells you nothing; it must not divide by zero."""
    n = EV.MIN_PLACES + 2
    assert EV._spearman(list(range(n)), [4.5] * n) is None


def test_unrated_places_are_excluded_not_zeroed():
    """A place with no public rating must drop out, not enter as a 0.

    Treating 'no rating' as zero stars would manufacture a correlation out of
    missing data.
    """
    cache = pd.DataFrame([
        {"destination": "Rated", "place_id": "a", "rating": 4.5,
         "user_rating_count": 100, "status": "OK", "fetched_on": "", "key": ""},
        {"destination": "Unrated", "place_id": "b", "rating": "",
         "user_rating_count": "", "status": "OK", "fetched_on": "", "key": ""},
        {"destination": "Failed", "place_id": "c", "rating": "",
         "user_rating_count": "", "status": "ERROR_Timeout", "fetched_on": "",
         "key": ""},
    ])
    sc = pd.DataFrame([
        {"destination": "Rated", "aspect": "safety", "complaint_rate": 0.5,
         "n_negative": 5, "n_opinions": 10},
        {"destination": "Unrated", "aspect": "safety", "complaint_rate": 0.9,
         "n_negative": 9, "n_opinions": 10},
        {"destination": "Failed", "aspect": "safety", "complaint_rate": 0.1,
         "n_negative": 1, "n_opinions": 10},
    ])
    out = EV.correlate(cache, sc)
    assert out["n_destinations_rated"] == 1
    assert out["aspects"]["safety"]["n"] == 1
    assert out["aspects"]["safety"]["spearman_rate_vs_stars"] is None


def test_the_report_does_not_claim_accuracy():
    """The wording is the safeguard: this is corroboration, never validation
    of a label. If that framing is lost the statistic starts being cited as
    something it is not."""
    import json
    path = EV.save({"n_destinations_rated": 0, "aspects": {}},
                   path=ROOT / "reports" / "_test_external_validity.json")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    text = payload["what_this_is"].lower()
    assert "not accuracy" in text or "corroboration, not accuracy" in text
    assert "open problem #1" in payload["what_this_is"]
    assert payload["expected_direction"].startswith("negative")
    Path(path).unlink()
