"""The reliability figure must come from two humans, or not exist.

Background
----------
This project has already produced an AI second pass over the gold set. It is
documented honestly in reports/automated_second_pass.json, which states that
kappa computed from it "would be a claim about two language models agreeing,
presented as a claim about human reliability".

Despite that, the filled CSV was later read back and very nearly reported as
inter-annotator agreement -- the labels look identical in shape to human ones,
and nothing in the data says otherwise. A warning in a JSON file did not
prevent it, so the rule now lives in code that raises.

These tests exist so the guard cannot be quietly removed or weakened.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import agreement as AG  # noqa: E402


def _labels(provenance, n=40):
    """A minimal labels file, optionally declaring provenance."""
    df = pd.DataFrame({
        "segment_id": [f"s{i}" for i in range(n)],
        "roads_access": ["N" if i % 3 == 0 else None for i in range(n)],
        "cleanliness": ["P" if i % 4 == 0 else None for i in range(n)],
        "facilities": [None] * n,
        "safety": ["N" if i % 5 == 0 else None for i in range(n)],
    })
    if provenance is not None:
        df[AG.PROVENANCE_COL] = provenance
    return df


def test_an_undeclared_file_is_refused(tmp_path):
    """Silence is not consent. An unmarked file is the exact failure mode."""
    p = tmp_path / "goldset_focused_annotator2.csv"
    _labels(None).to_csv(p, index=False)
    with pytest.raises(AG.MachineLabelsRefused, match="carries no"):
        AG.load_labels(p)


@pytest.mark.parametrize("who", ["ai", "AI", "machine", "assistant", "llm",
                                 "model", "automated", "  Ai  "])
def test_machine_provenance_is_refused(tmp_path, who):
    p = tmp_path / "goldset_focused_annotator2.csv"
    _labels(who).to_csv(p, index=False)
    with pytest.raises(AG.MachineLabelsRefused):
        AG.load_labels(p)


def test_an_unrecognised_provenance_is_refused(tmp_path):
    """Fail closed: a value nobody anticipated is not assumed to be human."""
    p = tmp_path / "goldset_focused_annotator2.csv"
    _labels("intern-ish?").to_csv(p, index=False)
    with pytest.raises(AG.MachineLabelsRefused):
        AG.load_labels(p)


def test_human_provenance_is_accepted(tmp_path):
    p = tmp_path / "goldset_focused_annotator2.csv"
    _labels("human").to_csv(p, index=False)
    df = AG.load_labels(p)
    assert len(df) == 40


def test_kappa_is_reported_with_an_interval():
    """A point estimate alone cannot support a claim, so it never travels alone."""
    a = [0, 1] * 40
    b = [0, 1] * 40
    out = AG.bootstrap_ci(a, b)
    assert out["kappa"] == 1.0
    assert out["lo"] is not None and out["hi"] is not None


def test_claims_rest_on_the_lower_bound_not_the_point():
    """A high point estimate on few rows must not read as 'substantial'."""
    a = [0] * 8 + [1] * 2
    b = [0] * 8 + [1] * 2
    a1 = pd.DataFrame({"segment_id": [f"s{i}" for i in range(10)],
                       "safety": [None if x == 0 else "N" for x in a],
                       "roads_access": [None] * 10,
                       "cleanliness": [None] * 10, "facilities": [None] * 10})
    a2 = a1.copy()
    res = AG.agreement(a1, a2)
    r = res["presence"]["safety"]
    # perfect agreement on 10 rows: point estimate 1.0, interval still wide
    assert r["kappa"] == 1.0
    assert r["lo"] is not None


def test_interpretation_bands_are_applied_to_the_bound():
    assert AG.interpret(0.55) == "moderate"
    assert AG.interpret(0.65) == "substantial"
    assert AG.interpret(0.85) == "almost perfect"
    assert AG.interpret(None) == "undefined"


def test_the_machine_pass_on_disk_is_not_named_like_an_annotator():
    """The AI-labelled CSV must not sit at the path the pipeline reads.

    It was named goldset_focused_annotator2.csv, which is indistinguishable
    from a human pass to anything that opens it.
    """
    reports = ROOT / "reports"
    stray = reports / "goldset_focused_annotator2.csv"
    if stray.exists():
        df = pd.read_csv(stray)
        labelled = df[[c for c in AG.FOCUS_ASPECTS if c in df.columns]].notna().any(axis=1)
        if labelled.any():
            assert AG.PROVENANCE_COL in df.columns, (
                "a populated annotator2 file must declare who labelled it")
