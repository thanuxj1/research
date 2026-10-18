"""Train and save the two models chosen by the comparison (scripts 57-59).

  python scripts/61_train_final_models.py

  topic    sentence embeddings (BAAI/bge-small-en-v1.5) + one RBF-kernel SVM per topic,
           OR the rule lexicon; per-topic thresholds = the ones script 57 chose on
           out-of-fold training scores.          -> models/final/topic_svm.joblib
  verdict  cardiffnlp/twitter-roberta-base-sentiment-latest fine-tuned on all 1,593
           training pairs with exactly the hyper-parameters and seed of script 56.
                                                 -> models/final/verdict_roberta/

Both are refits on the SAME training data with the SAME settings as the run that was
evaluated; the script checks that the saved models reproduce the evaluated test
predictions, so what is deployed is what was measured.
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from travellens import model_data as M  # noqa: E402

FINAL = ROOT / "models" / "final"
EMBEDDER = "BAAI/bge-small-en-v1.5"


def load56():
    spec = importlib.util.spec_from_file_location("ft56", ROOT / "scripts" / "56_finetune_transformers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def topic():
    from sentence_transformers import SentenceTransformer
    from sklearn.svm import SVC
    comp = json.loads((M.OUT / "topic_comparison.json").read_text())
    name = comp["best_by_cv"]
    assert name == "H Embeddings + RBF SVM OR lexicon", name
    th = comp["models"][name]["thresholds"]
    tr = M.load_train()
    Y = M.presence(tr).values
    emb = SentenceTransformer(EMBEDDER)
    E = emb.encode(tr.segment.tolist(), batch_size=128, normalize_embeddings=True, show_progress_bar=False)
    svms = [SVC(C=4, kernel="rbf", class_weight="balanced").fit(E, Y[:, j]) for j in range(len(M.TOPICS))]
    # determinism check against the evaluated run
    te = M.load_test()
    Ete = emb.encode(te.segment.tolist(), batch_size=128, normalize_embeddings=True, show_progress_bar=False)
    ref = np.load(M.OUT / "emb_test_random.npy")
    assert np.abs(Ete - ref).max() < 1e-4, "embedder output differs from the evaluated run"
    FINAL.mkdir(parents=True, exist_ok=True)
    joblib.dump({"topics": M.TOPICS, "embedder": EMBEDDER, "svms": svms, "thresholds": th,
                 "rule": "topic present if the rule lexicon tags it OR svm.decision_function >= threshold",
                 "selected_by": "scripts/57_topic_model_comparison.py (highest 5-fold CV macro-F1)",
                 "cv_macro_f1": comp["models"][name]["cv"]["macro_f1"],
                 "test_macro_f1": comp["models"][name]["test_random"]["macro_f1"]},
                FINAL / "topic_svm.joblib")
    print("saved", FINAL / "topic_svm.joblib")


def verdict():
    ft = load56()
    import torch
    torch.set_num_threads(max(1, torch.get_num_threads()))
    X, Y, evalsets = ft.data("verdict")
    spec = ft.MODELS["roberta"]
    t0 = time.time()
    tok, model = ft.train_one("verdict", spec, X, Y, [])
    out = FINAL / "verdict_roberta"
    model.config.id2label = {0: "N", 1: "X", 2: "P"}
    model.config.label2id = {"N": 0, "X": 1, "P": 2}
    model.save_pretrained(str(out))
    tok.save_pretrained(str(out))
    pred = ft.predict("verdict", tok, model, evalsets["test_random"]).argmax(1)
    ref = np.load(M.OUT / "ft_verdict_roberta.npz")["test_random"].argmax(1)
    agree = float((pred == ref).mean())
    (out / "provenance.json").write_text(json.dumps({
        "base": spec["name"], "task": "3-class verdict N/X/P for a (topic, sentence) pair",
        "input_format": "model_data.pair_text(topic, segment) -> '<topic phrase>: <sentence>'",
        "hyperparameters": {"epochs": ft.EPOCHS, "batch": ft.BATCH, "lr": spec["lr"], "max_len": ft.MAXLEN, "seed": ft.SEED},
        "n_train_pairs": len(X), "fit_seconds": round(time.time() - t0, 1),
        "agreement_with_evaluated_run_on_test": round(agree, 4),
        "selected_by": "scripts/58_verdict_model_comparison.py (highest 5-fold CV macro-F1)"}, indent=1))
    print("saved", out, "| agreement with evaluated test predictions: %.4f" % agree)
    assert agree >= 0.97, "refit diverged from the evaluated model"


if __name__ == "__main__":
    which = sys.argv[1:] or ["topic", "verdict"]
    if "topic" in which:
        topic()
    if "verdict" in which:
        verdict()
