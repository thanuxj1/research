"""The deployed models are the selected ones, and every surface uses them identically.

* What is deployed is what the comparison selected (scripts/57-58 best_by_cv) and the
  refit reproduces the evaluated predictions (scripts/61 records the agreement).
* The dashboard (verdict_final.csv / fAsp_ columns, written by scripts/62) and the API
  (/analyse via api._analyse_final) give a corpus sentence the same topics and verdicts.
* The 420 human verdict pairs trained the verdict model, so they never enter an
  accuracy figure while it is deployed.

Skipped on a fresh clone, where models/ (gitignored) and the corpus are absent.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import config as C  # noqa: E402
from travellens import final_models as FM  # noqa: E402

SCORED = C.DATA_PROCESSED / "segments_scored.csv"
COMP = C.REPORTS / "model_comparison"
deployed = pytest.mark.skipif(not (FM.available() and FM.VERDICT_CSV.exists()),
                              reason="final models not trained/applied in this checkout")


@pytest.mark.skipif(not FM.available(), reason="final models not trained in this checkout")
def test_deployed_models_are_the_selected_ones():
    import joblib
    t = json.loads((COMP / "topic_comparison.json").read_text())
    v = json.loads((COMP / "verdict_comparison.json").read_text())
    topic = joblib.load(FM.TOPIC_PATH)
    assert t["best_by_cv"] == "H Embeddings + RBF SVM OR lexicon"
    assert topic["thresholds"] == t["models"][t["best_by_cv"]]["thresholds"]
    assert v["best_by_cv"] == "V9 Fine-tuned RoBERTa-base (125M)"
    prov = json.loads((FM.VERDICT_DIR / "provenance.json").read_text())
    assert prov["agreement_with_evaluated_run_on_test"] >= 0.97


@pytest.fixture(scope="module")
def sample():
    import pandas as pd
    v = pd.read_csv(FM.VERDICT_CSV)
    ids = v["segment_id"].drop_duplicates().sample(150, random_state=7)
    seg = pd.read_csv(SCORED, usecols=["segment_id", "segment"] + ["fAsp_" + k for k in C.ASPECTS])
    seg = seg[seg["segment_id"].isin(set(ids))].drop_duplicates("segment_id")
    return seg, v[v["segment_id"].isin(set(ids))]


@deployed
def test_api_and_dashboard_tag_the_same_topics(sample):
    seg, _ = sample
    tags = FM.tag_topics(seg["segment"].astype(str).tolist())
    same = sum(set(t) == {k for k in C.ASPECTS if row["fAsp_" + k]}
               for t, (_, row) in zip(tags, seg.iterrows()))
    # batch composition can move an embedding in the 7th decimal; a sentence on a
    # threshold may flip. More than 1% would mean two different models.
    assert same / len(seg) >= 0.99, same


@deployed
def test_api_and_dashboard_give_the_same_verdicts(sample):
    from travellens.api import _analyse_final
    seg, v = sample
    want = {(s, a): p for s, a, p in zip(v["segment_id"], v["aspect"], v["pol_fm"])}
    got = {}
    results = _analyse_final(FM, seg["segment"].astype(str).tolist())
    for sid, r in zip(seg["segment_id"], results):
        for a, p in r["aspect_polarity"].items():
            got[(sid, a)] = p
    common = set(got) & set(want)
    assert len(common) >= 0.95 * len(want)
    agree = sum(got[k] == want[k] for k in common) / len(common)
    assert agree >= 0.99, agree


@deployed
def test_training_pairs_never_score_the_deployed_model():
    from travellens.polarity_eval import load_pairs
    loaded = load_pairs()
    assert loaded["supplementary"]["status"] == "excluded"
    assert set(loaded["pairs"]["part"]) <= {"A", "B"}
