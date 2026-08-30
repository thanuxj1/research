"""Guards on the split-half reliability study.

This study is the project's only validation of the published NUMBER rather
than of a component, so the ways it can be quietly wrong matter more than
usual. Two in particular:

1. Pooling cells across aspects inflates the correlation, because scenery sits
   near 9% and safety near 70% and both halves of any cell agree merely by
   belonging to the same aspect. The first run of the permutation null returned
   0.53 for exactly that reason. The null is the instrument that catches it, so
   the null itself is what these tests hold.

2. Measuring reliability over a different denominator than the dashboard
   publishes would answer a question nobody asked.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import config as C  # noqa: E402
from travellens import reliability as R  # noqa: E402


@pytest.fixture(scope="module")
def report():
    path = C.REPORTS / "reliability.json"
    if not path.exists():
        pytest.skip("run python scripts/46_reliability.py first")
    with open(str(path), encoding="utf-8") as fh:
        return json.load(fh)


def test_the_permutation_null_is_flat(report):
    """Shuffled verdicts must produce no reliability at all.

    If this rises, the headline figure has stopped measuring places and has
    started measuring something structural -- which is precisely what happened
    before the within-aspect centring was added.
    """
    sb = report["permutation_null"]["overall"]["spearman_brown"]
    assert sb is not None
    assert abs(sb) < 0.20, (
        "the null returns {} -- the observed reliability is partly an "
        "artefact of the method, not a property of the data".format(sb))


def test_the_null_is_flat_at_every_cell_size(report):
    for label, s in report["permutation_null"]["by_cell_size"].items():
        sb = s["spearman_brown"]
        if sb is None:
            continue
        assert abs(sb) < 0.35, "null leaks at cell size {}: {}".format(label, sb)


def test_reliability_rises_with_evidence(report):
    """More opinions per cell must mean better agreement, or something is off."""
    cum = report["observed"]["cumulative_from"]
    ordered = sorted(cum.items(), key=lambda kv: int(kv[0].split(">=")[1]))
    vals = [s["spearman_brown"] for _, s in ordered if s["spearman_brown"] is not None]
    assert vals == sorted(vals), (
        "reliability does not increase with cell size: {}".format(vals))


def test_the_gap_narrows_with_evidence(report):
    bins = report["observed"]["by_cell_size"]
    ordered = [bins[k]["mean_abs_diff_pp"] for k in bins
               if bins[k]["mean_abs_diff_pp"] is not None]
    assert ordered == sorted(ordered, reverse=True), (
        "the half-to-half gap does not narrow as cells grow: {}".format(ordered))


def test_centring_removes_each_aspect_mean():
    a = np.array([0.1, 0.3, 0.8, 0.6])
    b = np.array([0.2, 0.2, 0.7, 0.9])
    aspect = np.array(["scenery", "scenery", "safety", "safety"])
    ca, cb = R._centre_within_aspect(a, b, aspect)
    for asp in ("scenery", "safety"):
        m = aspect == asp
        assert abs(ca[m].mean()) < 1e-12
        assert abs(cb[m].mean()) < 1e-12


def test_spearman_brown_corrects_upward():
    """A half carries half the evidence, so the full measure is more reliable."""
    for r in (0.3, 0.5, 0.7):
        assert R.spearman_brown(r) > r
    assert R.spearman_brown(1.0) == pytest.approx(1.0)


def test_the_denominator_matches_the_dashboard():
    """Opinions are N+P. A factual statement is not in any published rate."""
    long = pd.DataFrame({
        "district": ["Kandy"] * 6,
        "destination": ["Test"] * 6,
        "aspect": ["cleanliness"] * 6,
        "pol": ["N", "N", "P", "X", "X", "P"],
    })
    cells = R.cells_from_long(long, "pol")
    v = cells[("Kandy", "Test", "cleanliness")]
    assert len(v) == 4, "X was counted as an opinion"
    assert int(v.sum()) == 2


def test_the_recommended_threshold_is_derived_not_asserted(report):
    """Whatever the report recommends must follow from its own numbers."""
    cum = report["observed"]["cumulative_from"]
    n, sb = R.recommend_threshold(cum, R.ACCEPTABLE)
    assert n == report["thresholds"]["acceptable_at_or_above"]
    assert cum["n>={}".format(n)]["spearman_brown"] >= R.ACCEPTABLE
    # And nothing smaller would have cleared the floor.
    smaller = [int(k.split(">=")[1]) for k in cum
               if int(k.split(">=")[1]) < n]
    for s in smaller:
        assert cum["n>={}".format(s)]["spearman_brown"] < R.ACCEPTABLE


def test_the_study_reads_the_deployed_rows():
    """It must resample the same table build_tree aggregates, not a copy of it.

    A reliability study computed on a re-implementation would report the
    reliability of the re-implementation. aggregate.long_table exists so both
    read the same rows.
    """
    src = (ROOT / "src" / "travellens" / "reliability.py").read_text(encoding="utf-8")
    assert "from .aggregate import DEFAULT_POLARITY_COL, long_table" in src
    assert "aspect_polarity" not in src, (
        "reliability.py applies the correction chain itself -- it must come "
        "from aggregate.long_table so the two cannot drift")
