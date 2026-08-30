"""Guards on the polarity accuracy evaluation.

The complaint rate IS the polarity call, aggregated, so this is the measurement
that caps every accuracy claim the project makes. Three ways it could go
quietly wrong:

1. The supplementary labelling sheet gets filled by a machine and becomes an
   accuracy figure. `agreement.py` exists because that nearly happened once
   with inter-annotator agreement; the same refusal has to apply here.
2. An accuracy is quoted without its interval. At 11 pairs the interval spans
   half the scale, and the point estimate on its own reads as knowledge.
3. The human ceiling goes missing, and 0.636 reads as a failure against 100%
   rather than against the 0.90 two humans actually manage.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import config as C  # noqa: E402
from travellens import polarity_eval as PE  # noqa: E402


@pytest.fixture(scope="module")
def report():
    path = C.REPORTS / "polarity_accuracy.json"
    if not path.exists():
        pytest.skip("run python scripts/43_evaluate_polarity.py first")
    with open(str(path), encoding="utf-8") as fh:
        return json.load(fh)


def test_every_accuracy_carries_an_interval(report):
    for key, entry in report["results"].items():
        for reader in ("vs_annotator1", "vs_annotator2", "unanimous_pairs"):
            for aspect, v in entry[reader]["per_aspect"].items():
                assert v["ci95"][0] is not None, (
                    "{}/{}/{} has no interval".format(key, reader, aspect))
                assert v["ci95"][0] <= v["accuracy"] <= v["ci95"][1]


def test_the_human_ceiling_is_reported_for_every_scored_aspect(report):
    ceiling = report["human_ceiling"]["per_aspect"]
    scored = report["results"]["part_a_headline"]["vs_annotator1"]["per_aspect"]
    for aspect in scored:
        assert aspect in ceiling, (
            "{} is scored with no human ceiling beside it -- the accuracy "
            "then reads as a failure against 100%".format(aspect))
        assert 0.0 < ceiling[aspect]["human_agreement"] <= 1.0


def test_no_aspect_is_scored_without_labels(report):
    """The three unlabelled aspects must not appear with a figure."""
    supp = report.get("supplementary_sheet") or {}
    if supp.get("status") == "in use":
        pytest.skip("the supplementary sheet now carries labels")
    for key, entry in report["results"].items():
        for aspect in entry["vs_annotator1"]["per_aspect"]:
            assert aspect in PE.GOLD_ASPECTS, (
                "{} has no human labels but is scored in {}".format(aspect, key))


def test_a_machine_filled_sheet_is_refused(tmp_path, monkeypatch):
    """The failure agreement.py was written against, applied here."""
    sheet = tmp_path / PE.SUPPLEMENTARY_SHEET
    pd.DataFrame({"segment_id": ["a", "b"], "aspect": ["scenery"] * 2,
                  "verdict": ["N", "P"], "labelled_by": ["ai", "ai"]}
                 ).to_csv(sheet, index=False)
    monkeypatch.setattr(C, "REPORTS", tmp_path)
    scored = pd.DataFrame({"segment_id": [], "segment": [], "pol_final": [],
                           "pol_lexicon": []}).set_index("segment_id")
    out, note = PE.load_supplementary(scored)
    assert len(out) == 0
    assert note["status"] == "refused"


def test_an_unmarked_sheet_is_refused(tmp_path, monkeypatch):
    """No labelled_by column at all is refused, not assumed to be human."""
    sheet = tmp_path / PE.SUPPLEMENTARY_SHEET
    pd.DataFrame({"segment_id": ["a"], "aspect": ["crowd"],
                  "verdict": ["N"]}).to_csv(sheet, index=False)
    monkeypatch.setattr(C, "REPORTS", tmp_path)
    scored = pd.DataFrame({"segment_id": [], "segment": [], "pol_final": [],
                           "pol_lexicon": []}).set_index("segment_id")
    out, note = PE.load_supplementary(scored)
    assert len(out) == 0
    assert note["status"] == "refused"


def test_a_human_filled_sheet_is_picked_up(tmp_path, monkeypatch):
    """The wiring works: filling the sheet produces scored pairs."""
    sheet = tmp_path / PE.SUPPLEMENTARY_SHEET
    text = "The entrance fee was far too expensive for what you get."
    pd.DataFrame({"segment_id": ["s1"], "aspect": ["price_value"],
                  "verdict": ["N"], "labelled_by": ["human"]}
                 ).to_csv(sheet, index=False)
    monkeypatch.setattr(C, "REPORTS", tmp_path)
    scored = pd.DataFrame({"segment_id": ["s1"], "segment": [text],
                           "pol_final": ["N"], "pol_lexicon": ["N"]}
                          ).set_index("segment_id")
    out, note = PE.load_supplementary(scored)
    assert note["status"] == "in use"
    assert len(out) == 1
    assert out.iloc[0]["aspect"] == "price_value"
    assert out.iloc[0]["human1"] == "N"


def test_a_blank_sheet_is_not_an_error(report):
    """The normal state before anyone sits down with it."""
    supp = report.get("supplementary_sheet")
    assert supp is not None
    assert supp["status"] in ("no sheet yet", "sheet exists but is blank",
                              "in use")


def test_the_sheet_never_shows_the_system_verdict():
    """Showing the answer being tested would anchor the reader."""
    path = C.REPORTS / "LABEL_THESE_polarity.csv"
    if not path.exists():
        pytest.skip("no sheet generated yet")
    cols = set(pd.read_csv(path, nrows=0).columns)
    for leak in ("pred", "prediction", "pol_final", "system_verdict",
                 "aspect_polarity", "polarity"):
        assert leak not in cols, "the sheet leaks the system's answer: {}".format(leak)


def test_bootstrap_interval_brackets_the_point():
    ci = PE._bootstrap_ci([1] * 7 + [0] * 3)
    assert ci["accuracy"] == pytest.approx(0.7)
    assert ci["lo"] < 0.7 < ci["hi"]
    assert ci["lo"] >= 0.0 and ci["hi"] <= 1.0
