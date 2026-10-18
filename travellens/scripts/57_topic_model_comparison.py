"""Topic detection: train, test and compare candidate models.

  python scripts/57_topic_model_comparison.py      (after 55, and 56 for the transformers)

Task: for each sentence, which of the seven topics does it mention (multi-label).

Candidates
  M0  rule lexicon (the deployed model; no training)
  M1  TF-IDF + Naive Bayes
  M2  TF-IDF + Logistic Regression
  M3  TF-IDF + linear SVM
  M4  sentence embeddings (bge-small) + Logistic Regression
  M5  sentence embeddings + RBF-kernel SVM
  M6  sentence embeddings + XGBoost (gradient-boosted trees)
  M7  zero-shot NLI (DistilBERT-MNLI; no training, thresholds only)
  M8  fine-tuned bge-small (33M parameters)       -- from script 56
  M9  fine-tuned RoBERTa-base (125M parameters)   -- from script 56
  +   "lexicon OR model" hybrid of every trained model

Protocol (the same for every model)
  * 5-fold cross-validation on the 1,500 training sentences gives out-of-fold scores.
  * Per-topic decision thresholds are chosen on those out-of-fold scores only.
  * THE SELECTION RULE, fixed before any test score is looked at: the final model
    is the one with the highest cross-validated macro-F1; a model within 0.01 of
    the best is preferred if it is simpler or faster.
  * Then every model is scored once on the 800 untouched random test sentences
    (AI-annotated) and on the human gold set (two readers, four topics).

Writes reports/model_comparison/topic_comparison.json
"""
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from travellens import aspects as AS  # noqa: E402
from travellens import model_data as M  # noqa: E402

from scipy.sparse import hstack  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score  # noqa: E402
from sklearn.model_selection import KFold  # noqa: E402
from sklearn.naive_bayes import MultinomialNB  # noqa: E402
from sklearn.svm import SVC, LinearSVC  # noqa: E402

SEED, FOLDS, BOOT = 42, 5, 2000
T = M.TOPICS
G = M.GOLD_TOPICS


# ---------------------------------------------------------------- metrics
def prf(pred, gold):
    pred, gold = np.asarray(pred).astype(bool), np.asarray(gold).astype(bool)
    tp = int((pred & gold).sum()); fp = int((pred & ~gold).sum()); fn = int((~pred & gold).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "tp": tp, "fp": fp, "fn": fn}


def macro_f1(P, Y):
    return float(np.mean([prf(P[:, j], Y[:, j])["f1"] for j in range(Y.shape[1])]))


def boot_ci(P, Y, seed=SEED):
    rng = np.random.default_rng(seed)
    n = len(Y)
    vals = [macro_f1(P[i], Y[i]) for i in (rng.integers(0, n, n) for _ in range(BOOT))]
    return [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)]


def report(P, Y, topics, S=None):
    per = {t: prf(P[:, j], Y[:, j]) for j, t in enumerate(topics)}
    if S is not None:
        for j, t in enumerate(topics):
            if Y[:, j].sum():
                per[t]["pr_auc"] = round(float(average_precision_score(Y[:, j], S[:, j])), 3)
    tp = sum(v["tp"] for v in per.values()); fp = sum(v["fp"] for v in per.values()); fn = sum(v["fn"] for v in per.values())
    micro = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    return {"per_topic": per,
            "macro_f1": round(macro_f1(P, Y), 3), "macro_f1_ci95": boot_ci(P, Y),
            "macro_precision": round(float(np.mean([v["precision"] for v in per.values()])), 3),
            "macro_recall": round(float(np.mean([v["recall"] for v in per.values()])), 3),
            "micro_f1": round(micro, 3),
            "label_accuracy": round(float((P == Y).mean()), 3),
            "exact_match": round(float((P == Y).all(1).mean()), 3), "n": int(len(Y))}


def best_threshold(s, y):
    cands = np.unique(np.quantile(s, np.linspace(0.5, 0.995, 120)))
    f = [prf(s >= c, y)["f1"] for c in cands]
    return float(cands[int(np.argmax(f))])


# ---------------------------------------------------------------- features
def tfidf_fit(texts):
    wv = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
    cv = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)
    wv.fit(texts); cv.fit(texts)
    return lambda xs: hstack([wv.transform(xs), cv.transform(xs)]).tocsr()


def embed(texts, cache):
    path = M.OUT / ("emb_%s.npy" % cache)
    if path.exists():
        return np.load(path)
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer("BAAI/bge-small-en-v1.5")
    E = m.encode(list(texts), batch_size=128, normalize_embeddings=True, show_progress_bar=False)
    np.save(path, E)
    return E


def zero_shot(texts, cache):
    path = M.OUT / ("zeroshot_%s.npy" % cache)
    if path.exists():
        return np.load(path)
    from transformers import pipeline
    clf = pipeline("zero-shot-classification", model="typeform/distilbert-base-uncased-mnli", device=-1)
    labels = [M.TOPIC_PHRASE[t] for t in T]
    out = clf(list(texts), candidate_labels=labels, multi_label=True,
              hypothesis_template="This review sentence is about {}.", batch_size=32)
    S = np.array([[dict(zip(o["labels"], o["scores"]))[l] for l in labels] for o in out])
    np.save(path, S)
    return S


# ---------------------------------------------------------------- models
def make(kind):
    if kind == "nb":
        return lambda: MultinomialNB(alpha=0.1), "proba"
    if kind == "lr":
        return lambda: LogisticRegression(C=4, max_iter=3000, class_weight="balanced"), "proba"
    if kind == "svm":
        return lambda: LinearSVC(C=0.5, class_weight="balanced"), "dec"
    if kind == "rbf":
        return lambda: SVC(C=4, kernel="rbf", class_weight="balanced"), "dec"
    if kind == "xgb":
        from xgboost import XGBClassifier
        return (lambda: XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.08, subsample=0.9,
                                      colsample_bytree=0.8, eval_metric="logloss", n_jobs=4,
                                      random_state=SEED, verbosity=0)), "proba"
    raise ValueError(kind)


def scores_of(clf, how, X):
    return clf.predict_proba(X)[:, 1] if how == "proba" else clf.decision_function(X)


def run_sklearn(kind, feats, Ytr, texts_tr, evals):
    """Returns (oof scores, {eval name: scores}, fit seconds, ms per item)."""
    factory, how = make(kind)
    oof = np.zeros(Ytr.shape)
    for tr, va in KFold(FOLDS, shuffle=True, random_state=SEED).split(texts_tr):
        Xtr, Xva = feats(tr, va)
        for j in range(Ytr.shape[1]):
            clf = factory().fit(Xtr, Ytr[tr, j])
            oof[va, j] = scores_of(clf, how, Xva)
    t0 = time.time()
    Xall, Xev = feats(np.arange(len(texts_tr)), None, evals)
    clfs = [factory().fit(Xall, Ytr[:, j]) for j in range(Ytr.shape[1])]
    fit_s = time.time() - t0
    t1 = time.time()
    out = {k: np.column_stack([scores_of(c, how, X) for c in clfs]) for k, X in Xev.items()}
    ms = 1000 * (time.time() - t1) / sum(X.shape[0] for X in Xev.values())
    return oof, out, fit_s, ms


def main():
    M.OUT.mkdir(parents=True, exist_ok=True)
    tr, te, gold = M.load_train(), M.load_test(), M.load_gold()
    Ytr, Yte = M.presence(tr).values, M.presence(te).values
    texts = {"train": tr.segment.tolist(), "test_random": te.segment.tolist(), "gold": gold.segment.tolist()}
    gA, gB = (gold.part == "A").values, (gold.part == "B").values
    gold_y = {"gold_A_reader1": (gA, M.presence(gold, G, "_h1").values),
              "gold_A_reader2": (gA, M.presence(gold, G, "_h2").values),
              "gold_B_reader1": (gB, M.presence(gold, G, "_h1").values)}
    gidx = [T.index(t) for t in G]

    # lexicon (deployed) -- binary
    lex = {k: np.array([[t in set(AS.tag_segment(s)) for t in T] for s in v]).astype(float)
           for k, v in texts.items()}

    E = {k: embed(v, k) for k, v in texts.items()}

    def tfidf_feats(tr_idx, va_idx, evals=None):
        f = tfidf_fit([texts["train"][i] for i in tr_idx])
        if evals is None:
            return f([texts["train"][i] for i in tr_idx]), f([texts["train"][i] for i in va_idx])
        return f([texts["train"][i] for i in tr_idx]), {k: f(v) for k, v in evals.items()}

    def emb_feats(tr_idx, va_idx, evals=None):
        if evals is None:
            return E["train"][tr_idx], E["train"][va_idx]
        return E["train"][tr_idx], {k: E[k] for k in evals}

    ev_text = {"test_random": texts["test_random"], "gold": texts["gold"]}
    ev_emb = {"test_random": None, "gold": None}
    runs = {}   # name -> dict(oof, scores, meta)
    runs["M0 Rule lexicon (deployed)"] = {"oof": lex["train"], "scores": {"test_random": lex["test_random"], "gold": lex["gold"]},
                                          "binary": True, "meta": {"family": "rules", "trained": False,
                                                                   "fit_seconds": 0, "ms_per_item": None}}
    for name, kind, feats, ev, fam in [
            ("M1 TF-IDF + Naive Bayes", "nb", tfidf_feats, ev_text, "classical ML"),
            ("M2 TF-IDF + Logistic Regression", "lr", tfidf_feats, ev_text, "classical ML"),
            ("M3 TF-IDF + Linear SVM", "svm", tfidf_feats, ev_text, "classical ML"),
            ("M4 Embeddings + Logistic Regression", "lr", emb_feats, ev_emb, "embeddings + classical ML"),
            ("M5 Embeddings + RBF SVM", "rbf", emb_feats, ev_emb, "embeddings + classical ML"),
            ("M6 Embeddings + XGBoost", "xgb", emb_feats, ev_emb, "embeddings + gradient boosting")]:
        print("training", name, flush=True)
        oof, sc, fit_s, ms = run_sklearn(kind, feats, Ytr, texts["train"], ev)
        runs[name] = {"oof": oof, "scores": sc, "meta": {"family": fam, "trained": True,
                                                        "fit_seconds": round(fit_s, 2), "ms_per_item": round(ms, 3)}}
    print("zero-shot NLI", flush=True)
    Z = {k: zero_shot(v, k) for k, v in texts.items()}
    runs["M7 Zero-shot NLI (DistilBERT-MNLI)"] = {"oof": Z["train"], "scores": {"test_random": Z["test_random"], "gold": Z["gold"]},
                                                  "meta": {"family": "transformer, no training", "trained": False}}
    for name, key in (("M8 Fine-tuned bge-small (33M)", "bge"), ("M9 Fine-tuned RoBERTa-base (125M)", "roberta")):
        p = M.OUT / ("ft_topic_%s.npz" % key)
        if not p.exists():
            print("missing", p.name, "- run scripts/56 first; skipped")
            continue
        z = np.load(p)
        lg = json.loads((M.OUT / ("ft_topic_%s.json" % key)).read_text())
        runs[name] = {"oof": z["oof"], "scores": {"test_random": z["test_random"], "gold": z["gold"]},
                      "meta": {"family": "fine-tuned transformer", "trained": True,
                               "fit_seconds": lg["final_fit_seconds"], "ms_per_item": lg["inference_ms_per_item_cpu"],
                               "training_loss_by_epoch": lg["final_fit_losses"]}}

    # hybrids: lexicon OR model
    for name in [n for n in list(runs) if runs[n]["meta"].get("trained") and not runs[n].get("binary")]:
        r = runs[name]
        runs["H " + name.split(" ", 1)[1] + " OR lexicon"] = {
            "hybrid_of": name, "oof": r["oof"], "scores": r["scores"],
            "meta": dict(r["meta"], family="hybrid: lexicon OR " + r["meta"]["family"])}

    results = {}
    for name, r in runs.items():
        hyb = "hybrid_of" in r
        if r.get("binary"):
            th = [0.5] * len(T)
        else:
            th = []
            for j in range(len(T)):
                s = r["oof"][:, j].copy()
                if hyb:   # lexicon hits count as maximal score
                    s = np.where(lex["train"][:, j] > 0, np.inf, s)
                    finite = s[np.isfinite(s)]
                    cands = np.unique(np.quantile(finite, np.linspace(0.5, 0.995, 120)))
                    f = [prf(s >= c, Ytr[:, j])["f1"] for c in cands]
                    th.append(float(cands[int(np.argmax(f))]))
                else:
                    th.append(best_threshold(s, Ytr[:, j]))
        th = np.array(th)

        def decide(S, L):
            P = (S >= th).astype(int)
            return np.maximum(P, L.astype(int)) if hyb else P

        Poof = decide(r["oof"], lex["train"])
        Pte = decide(r["scores"]["test_random"], lex["test_random"])
        Pg = decide(r["scores"]["gold"], lex["gold"])
        soft = None if r.get("binary") or hyb else r["scores"]["test_random"]
        res = {"meta": r["meta"], "thresholds": [round(float(x), 4) for x in th],
               "cv": {"macro_f1": round(macro_f1(Poof, Ytr), 3),
                      "per_topic_f1": {t: prf(Poof[:, j], Ytr[:, j])["f1"] for j, t in enumerate(T)},
                      "fold_macro_f1": [round(macro_f1(Poof[va], Ytr[va]), 3)
                                        for _, va in KFold(FOLDS, shuffle=True, random_state=SEED).split(Ytr)]},
               "test_random": report(Pte, Yte, T, soft)}
        for gname, (mask, Yg) in gold_y.items():
            res[gname] = report(Pg[mask][:, gidx], Yg[mask], G)
        res["cv"]["fold_sd"] = round(float(np.std(res["cv"]["fold_macro_f1"])), 3)
        results[name] = res
        print("%-46s CV %.3f  test %.3f  goldA %.3f" % (name, res["cv"]["macro_f1"], res["test_random"]["macro_f1"],
                                                       res["gold_A_reader1"]["macro_f1"]), flush=True)

    # selection rule (CV only), then McNemar against the deployed lexicon on the test set
    ranked = sorted(results, key=lambda n: -results[n]["cv"]["macro_f1"])
    best = ranked[0]
    out = {"what_this_is": __doc__.strip().splitlines()[0],
           "selection_rule": "highest 5-fold cross-validated macro-F1 on the training set; within 0.01, prefer simpler/faster",
           "data": {"train_sentences": len(tr), "test_random_sentences": len(te),
                    "gold_A_sentences": int(gA.sum()), "gold_B_sentences": int(gB.sum()),
                    "train_labels": "AI-annotated (Claude), calibrated against the human gold set",
                    "test_random_labels": "AI-annotated (Claude), random sample, never trained or tuned on",
                    "gold_labels": "human, two independent readers, four topics"},
           "ranking_by_cv": ranked, "best_by_cv": best, "models": results}
    (M.OUT / "topic_comparison.json").write_text(json.dumps(out, indent=1), encoding="utf8")
    print("best by CV:", best)


if __name__ == "__main__":
    main()
