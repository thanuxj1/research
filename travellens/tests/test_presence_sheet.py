"""Guards on the extraction-presence sheet and the precision it yields.

The polarity sheet asked "complaint, praise or fact?" and offered no way to say
"this is not about that topic at all". That was a design error: roads
extraction precision is 0.588, so roughly two in five roads-tagged segments are
not about roads, and all 60 roads pairs were given a verdict regardless. The
presence sheet re-asks the missing question.

What it can produce is PRECISION and nothing else -- the sample holds only
pairs the pipeline already tagged, so it cannot see a mention the pipeline
missed. These tests exist mostly to stop an F1 being manufactured from it.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import accuracy as A  # noqa: E402
from travellens import config as C  # noqa: E402
from travellens import polarity_sheet as PS  # noqa: E402


def test_the_sheet_asks_presence_not_polarity():
    path = C.REPORTS / "LABEL_THESE_presence.csv"
    if not path.exists():
        pytest.skip("run python scripts/48_presence_sheet.py first")
    cols = set(pd.read_csv(path, nrows=0).columns)
    assert "is_about" in cols
    # The earlier verdict must not travel with it: having called something a
    # complaint about scenery makes it awkward to then say it was not about
    # scenery, and that reluctance has a direction.
    assert "verdict" not in cols
    for leak in ("pred", "prediction", "pol_final", "aspect_polarity"):
        assert leak not in cols


def test_the_sheet_covers_the_same_pairs_as_the_polarity_sheet():
    pres = C.REPORTS / "LABEL_THESE_presence.csv"
    pol = C.REPORTS / "LABEL_THESE_polarity.csv"
    if not (pres.exists() and pol.exists()):
        pytest.skip("sheets not generated")
    a = pd.read_csv(pres)
    b = pd.read_csv(pol)
    assert len(a) == len(b)
    assert (a["segment_id"].astype(str).tolist()
            == b["segment_id"].astype(str).tolist())
    assert a["aspect"].tolist() == b["aspect"].tolist()


def test_presence_precision_never_reports_recall_or_f1(tmp_path, monkeypatch):
    sheet = tmp_path / A.PRESENCE_SHEET
    pd.DataFrame({
        "segment_id": ["a", "b", "c", "d"],
        "aspect": ["scenery"] * 4,
        "is_about": ["y", "y", "n", "y"],
        "labelled_by": ["human"] * 4,
    }).to_csv(sheet, index=False)
    monkeypatch.setattr(C, "REPORTS", tmp_path)
    out = A.presence_precision()
    assert out["status"] == "in use"
    rec = out["per_aspect"]["scenery"]
    assert rec["precision"] == pytest.approx(0.75)
    assert rec["n_pairs_judged"] == 4
    assert "recall" not in rec and "f1" not in rec, (
        "the presence sheet cannot see what the pipeline missed, so any "
        "recall or F1 here would be invented")
    assert rec["ci95"][0] <= rec["precision"] <= rec["ci95"][1]


def test_a_machine_filled_presence_sheet_is_refused(tmp_path, monkeypatch):
    sheet = tmp_path / A.PRESENCE_SHEET
    pd.DataFrame({"segment_id": ["a"], "aspect": ["crowd"],
                  "is_about": ["y"], "labelled_by": ["ai"]}
                 ).to_csv(sheet, index=False)
    monkeypatch.setattr(C, "REPORTS", tmp_path)
    assert A.presence_precision()["status"] == "refused"


def test_an_unmarked_presence_sheet_is_refused(tmp_path, monkeypatch):
    sheet = tmp_path / A.PRESENCE_SHEET
    pd.DataFrame({"segment_id": ["a"], "aspect": ["crowd"],
                  "is_about": ["y"]}).to_csv(sheet, index=False)
    monkeypatch.setattr(C, "REPORTS", tmp_path)
    assert A.presence_precision()["status"] == "refused"


def test_a_presence_only_aspect_ships_no_f1():
    """An aspect measured only by the presence sheet must not gain an F1.

    Downstream -- analyse.confidence, the portal's build -- keys on f1. A
    precision figure from one reader promoted into that field would be read as
    the two-reader F1 the gold set produces.
    """
    report = C.REPORTS / "accuracy_all_aspects.json"
    if not report.exists():
        pytest.skip("run python scripts/44_accuracy_report.py first")
    with open(str(report), encoding="utf-8") as fh:
        rep = json.load(fh)
    for key, row in rep["aspects"].items():
        if row.get("human_readers") == 1 and row.get("cohens_kappa") is None:
            assert row["f1"] is None
            assert row["recall"] is None
            assert row["precision"] is not None


def test_the_report_states_the_sheet_state():
    report = C.REPORTS / "accuracy_all_aspects.json"
    if not report.exists():
        pytest.skip("run python scripts/44_accuracy_report.py first")
    with open(str(report), encoding="utf-8") as fh:
        rep = json.load(fh)
    assert rep["presence_sheet"]["status"] in (
        "no sheet yet", "sheet exists but is blank", "refused", "in use")


def test_building_the_presence_sheet_needs_the_polarity_sheet(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "REPORTS", tmp_path)
    with pytest.raises(SystemExit):
        PS.build_presence()
