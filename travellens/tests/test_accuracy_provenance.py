"""No aspect may publish an accuracy figure without human labels behind it.

reports/accuracy_all_aspects.json used to quote precision/recall/F1 for
scenery, price_value and crowd. No label file in this repository carries those
aspects: goldset_annotator{1,2}.csv have the columns and zero entries, and the
LABEL_THESE_price_crowd* sheets are blank templates. Two of the three figures
were clearing analyse.CONFIDENCE_FLOOR, so a verdict about price or crowding
was being shown as high-confidence on the strength of a number nobody could
reproduce.

These tests hold the repair in place: the published report must agree with the
evaluations it summarises, and must not name an aspect the labels do not cover.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens import accuracy  # noqa: E402
from travellens import analyse  # noqa: E402
from travellens import config as C  # noqa: E402


@pytest.fixture(scope="module")
def published():
    path = C.REPORTS / "accuracy_all_aspects.json"
    assert path.exists(), "run python scripts/44_accuracy_report.py"
    with open(str(path), encoding="utf-8") as fh:
        return json.load(fh)


def test_every_published_aspect_has_human_labels(published):
    labelled = accuracy.human_labelled_aspects()["labelled"]
    for key in published["aspects"]:
        assert key in labelled, (
            "{} publishes an accuracy figure but no file declaring human "
            "provenance carries labels for it".format(key))
        assert labelled[key]["n_labels"] > 0


def test_unlabelled_aspects_carry_no_figures(published):
    for key, row in published["unmeasured"].items():
        assert "precision" not in row and "recall" not in row and "f1" not in row
        assert row.get("reason")
        # analyse must read the absence as an absence, not as a low score.
        assert analyse.confidence(key) == "unmeasured"
        assert analyse.MEASURED_F1.get(key) is None


def test_the_three_withdrawn_aspects_are_still_unlabelled():
    """If this fails because somebody labelled them, that is the good outcome.

    Delete the aspect from this list, re-run scripts/38_evaluate_against_gold.py
    and scripts/44_accuracy_report.py, and it rejoins the measured block on its
    own. The test exists so the rows cannot come back WITHOUT that happening.
    """
    labelled = accuracy.human_labelled_aspects()["labelled"]
    for key in ("scenery", "price_value", "crowd"):
        if key in labelled:
            pytest.skip("{} now has {} human labels -- regenerate the report"
                        .format(key, labelled[key]["n_labels"]))
    published = json.load(open(str(C.REPORTS / "accuracy_all_aspects.json"),
                               encoding="utf-8"))
    for key in ("scenery", "price_value", "crowd"):
        assert key not in published["aspects"]
        assert key in published["unmeasured"]


def test_published_figures_match_the_evaluation_they_summarise(published):
    """Gold-derived rows must match gold_evaluation.json exactly.

    Rows measured only by the presence sheet come from a different file and a
    different measurement -- precision, one reader, no recall -- so they are
    checked by tests/test_presence_sheet.py instead.
    """
    with open(str(C.REPORTS / "gold_evaluation.json"), encoding="utf-8") as fh:
        gold = json.load(fh)
    part_a = gold["results"]["part_a_headline"]["per_aspect"]
    for key, row in published["aspects"].items():
        if key not in part_a:
            assert row["f1"] is None, (
                "{} is not in the gold evaluation but publishes an F1".format(key))
            continue
        for field in ("precision", "recall", "f1", "human_positives"):
            assert row[field] == part_a[key][field], (
                "{}.{} is {} in the report and {} in gold_evaluation.json -- "
                "the report is stale, regenerate it".format(
                    key, field, row[field], part_a[key][field]))


def test_kappa_matches_the_agreement_report(published):
    """A kappa may only be published where two readers actually produced one."""
    with open(str(C.REPORTS / "agreement.json"), encoding="utf-8") as fh:
        agree = json.load(fh)
    for key, row in published["aspects"].items():
        if key not in agree["presence"]:
            assert row["cohens_kappa"] is None, (
                "{} has no second reader but publishes a kappa".format(key))
            continue
        assert row["cohens_kappa"] == agree["presence"][key]["kappa"]


def test_blank_template_cannot_donate_labels(tmp_path, monkeypatch):
    """A sheet with aspect columns and no provenance is not a label source."""
    sheet = tmp_path / "LABEL_THESE_fake.csv"
    pd.DataFrame({"segment_id": ["a", "b"],
                  "Scenery & nature": ["N", "P"]}).to_csv(sheet, index=False)
    monkeypatch.setattr(C, "REPORTS", tmp_path)
    scan = accuracy.human_labelled_aspects()
    assert "scenery" not in scan["labelled"]
    assert any(s["file"] == sheet.name for s in scan["skipped"])


def test_scored_aspect_without_labels_is_refused(tmp_path, monkeypatch):
    """The failure that produced this bug, reproduced -- and now refused."""
    (tmp_path / "gold_evaluation.json").write_text(json.dumps({
        "results": {"part_a_headline": {"n_rows": 120, "per_aspect": {
            "scenery": {"precision": 0.75, "recall": 0.655, "f1": 0.699,
                        "human_positives": 55}}}}}), encoding="utf-8")
    (tmp_path / "agreement.json").write_text(json.dumps({"presence": {}}),
                                             encoding="utf-8")
    monkeypatch.setattr(C, "REPORTS", tmp_path)
    with pytest.raises(accuracy.UnlabelledAspectRefused):
        accuracy.build()
