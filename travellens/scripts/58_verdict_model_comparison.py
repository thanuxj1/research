"""Complaint / praise / fact verdict: train, test and compare candidate models.

  python scripts/58_verdict_model_comparison.py   (after 55, and 56 for the transformers)

Task: given a sentence and a topic it mentions, is it a complaint (N), praise (P) or
a plain fact (X) about that topic?

Candidates
  V0  rule lexicon polarity (no training)
  V1  DistilBERT SST-2, zero-shot (film-review sentiment, the corpus's Method B)
  V2  RoBERTa-base sentiment, zero-shot (twitter-roberta-base-sentiment-latest)
  V3  RoBERTa zero-shot + correction rules (the DEPLOYED chain, Method E + rules)
  V4  TF-IDF + Logistic Regression          (topic-prefixed text)
  V5  TF-IDF + Linear SVM
  V6  sentence embeddings (bge-small) + Logistic Regression
  V7  stacked: the zero-shot model outputs + lexicon + topic -> Logistic Regression
  V8  fine-tuned bge-small (33M)          -- from script 56
  V9  fine-tuned RoBERTa-base sentiment (125M), topic-aware input -- from script 56

Training data: 1,173 AI-annotated (topic, sentence) pairs + 420 human-labelled pairs.
Protocol and selection rule are the same as the topic comparison (57): 5-fold
stratified CV on training pairs picks the model; the random test pairs and the
human gold pairs are scored once, afterwards.

Writes reports/model_comparison/verdict_comparison.json
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
from travellens import config as C  # noqa: E402
from travellens import model_data as M  # noqa: E402
from travellens.polarity import aspect_polarity  # noqa: E402

from scipy.sparse import csr_matrix, hstack  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import cohen_kappa_score, confusion_matrix  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402
from sklearn.svm import LinearSVC  # noqa: E402

SEED, FOLDS, BOOT = 42, 5, 2000
L = M.LABELS                     # N P X
FT_ORDER = ["N", "X", "P"]       # column order of the fine-tuned models' outputs


def metrics(pred, gold):
    pred, gold = np.asarray(pred), np.asarray(gold)
    per = {}
    for c in L:
        tp = int(((pred == c) & (gold == c)).sum()); fp = int(((pred == c) & (gold != c)).sum())
        fn = int(((pred != c) & (gold == c)).sum())
        p = tp / (tp + fp) if tp + fp else 0.0; r = tp / (tp + fn) if tp + fn else 0.0
        per[c] = {"precision": round(p, 3), "recall": round(r, 3),
                  "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0, "support": int((gold == c).sum())}
    return per


def summary(pred, gold, ci=True):
    pred, gold = np.asarray(pred), np.asarray(gold)
    per = metrics(pred, gold)
    out = {"accuracy": round(float((pred == gold).mean()), 3),
           "macro_f1": round(float(np.mean([per[c]["f1"] for c in L])), 3),
           "kappa": round(float(cohen_kappa_score(gold, pred, labels=L)), 3),
           "complaint_f1": per["N"]["f1"], "per_class": per,
           "confusion_rows_true_cols_pred": confusion_matrix(gold, pred, labels=L).tolist(), "n": int(len(gold))}
    if ci and len(gold):
        rng = np.random.default_rng(SEED)
        acc, mf = [], []
        for _ in range(BOOT):
            i = rng.integers(0, len(gold), len(gold))
            acc.append((pred[i] == gold[i]).mean())
            pc = metrics(pred[i], gold[i]); mf.append(np.mean([pc[c]["f1"] for c in L]))
        out["accuracy_ci95"] = [round(float(np.percentile(acc, q)), 3) for q in (2.5, 97.5)]
        out["macro_f1_ci95"] = [round(float(np.percentile(mf, q)), 3) for q in (2.5, 97.5)]
    return out


def mcnemar(pa, pb, gold):
    a = np.asarray(pa) == np.asarray(gold); b = np.asarray(pb) == np.asarray(gold)
    n01 = int((a & ~b).sum()); n10 = int((~a & b).sum())
    from scipy.stats import binomtest
    p = binomtest(min(n01, n10), n01 + n10, 0.5).pvalue if n01 + n10 else 1.0
    return {"only_first_right": n01, "only_second_right": n10, "p_value": round(float(p), 4)}


def fill_missing_polarity(d):
    """The corpus only stores sentiment for sentences the lexicon tagged; score the rest
    with exactly the pipeline's own functions (no cache writes)."""
    from travellens import polarity as PL
    miss = d.pol_roberta.isna()
    if not miss.any():
        return
    texts = d.loc[miss, "segment"].astype(str).tolist()
    lex = [PL.lexicon_polarity(t) for t in texts]
    sst, sst_c = PL._score_with_model(texts, PL.MODEL_NAME, None, PL.CACHE_PATH, use_cache=False, verbose=False)
    rob, rob_c = PL._score_with_model(texts, PL.ROBERTA_MODEL, PL.ROBERTA_LABELS,
                                      PL._cache_path(PL.ROBERTA_MODEL), use_cache=False, verbose=False)
    d.loc[miss, "pol_lexicon"] = [x[0] for x in lex]
    d.loc[miss, "pol_lexicon_score"] = [x[1] for x in lex]
    d.loc[miss, "pol_model"], d.loc[miss, "pol_model_conf"] = sst, sst_c
    d.loc[miss, "pol_roberta"], d.loc[miss, "pol_roberta_conf"] = rob, rob_c
    d.loc[miss, "pol_final"] = [PL.final_polarity(t, r, l[0], l[1])[0] for t, r, l in zip(texts, rob, lex)]


def main():
    sets = M.verdict_sets()
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_scored.csv",
                      usecols=["segment_id", "pol_lexicon", "pol_lexicon_score", "pol_model", "pol_model_conf",
                               "pol_roberta", "pol_roberta_conf", "pol_final"]).drop_duplicates("segment_id")
    for k in sets:
        sets[k] = sets[k].merge(seg, on="segment_id", how="left")
        fill_missing_polarity(sets[k])
        assert sets[k].pol_roberta.notna().all(), k
        sets[k]["text"] = [M.pair_text(t, s) for t, s in zip(sets[k].topic, sets[k].segment)]
    tr = sets["train"]
    ytr = tr.label.values
    evals = ["test_random", "gold_A", "gold_B"]

    preds, oofs, meta = {}, {}, {}

    def rule(name, f, fam):
        oofs[name] = np.array([f(r) for r in tr.to_dict("records")])
        preds[name] = {k: np.array([f(r) for r in sets[k].to_dict("records")]) for k in evals}
        meta[name] = {"family": fam, "trained": False}

    to3 = lambda v: v if v in L else "X"
    rule("V0 Rule lexicon polarity", lambda r: to3(r["pol_lexicon"]), "rules")
    rule("V1 DistilBERT SST-2 (zero-shot)", lambda r: to3(r["pol_model"]), "transformer, no training")
    rule("V2 RoBERTa sentiment (zero-shot)", lambda r: to3(r["pol_roberta"]), "transformer, no training")
    rule("V3 RoBERTa + correction rules (deployed)",
         lambda r: to3(aspect_polarity(r["segment"], r["topic"], r["pol_final"], r["pol_lexicon"])[0]),
         "transformer + rules")

    def stack_feats(d):
        cat = pd.get_dummies(d[["pol_lexicon", "pol_model", "pol_roberta", "topic"]].astype(str))
        return cat, d[["pol_roberta_conf", "pol_model_conf", "pol_lexicon_score"]].fillna(0).values.astype(float)

    cat_cols = stack_feats(pd.concat([sets[k] for k in sets]))[0].columns

    def feats(kind, fit_df, apply_dfs):
        if kind in ("tfidf_lr", "tfidf_svm"):
            wv = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True).fit(fit_df.text)
            cv = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True).fit(fit_df.text)
            return [hstack([wv.transform(d.text), cv.transform(d.text)]).tocsr() for d in apply_dfs]
        if kind == "emb_lr":
            return [EMB[d.text.map(TXT_IDX).values] for d in apply_dfs]
        if kind == "stack":
            out = []
            for d in apply_dfs:
                c, n = stack_feats(d)
                out.append(np.hstack([c.reindex(columns=cat_cols, fill_value=0).values.astype(float), n]))
            return out

    def model(kind):
        if kind == "tfidf_svm":
            return LinearSVC(C=0.5, class_weight="balanced")
        return LogisticRegression(C=4 if kind != "stack" else 1, max_iter=4000, class_weight="balanced")

    # embeddings of every pair text, once
    from sentence_transformers import SentenceTransformer
    all_txt = pd.concat([sets[k].text for k in sets]).unique().tolist()
    TXT_IDX = {t: i for i, t in enumerate(all_txt)}
    EMB = SentenceTransformer("BAAI/bge-small-en-v1.5").encode(all_txt, batch_size=128, normalize_embeddings=True,
                                                                 show_progress_bar=False)

    skf = list(StratifiedKFold(FOLDS, shuffle=True, random_state=SEED).split(tr, ytr))
    for name, kind, fam in [("V4 TF-IDF + Logistic Regression", "tfidf_lr", "classical ML"),
                            ("V5 TF-IDF + Linear SVM", "tfidf_svm", "classical ML"),
                            ("V6 Embeddings + Logistic Regression", "emb_lr", "embeddings + classical ML"),
                            ("V7 Stacked zero-shot outputs + LR", "stack", "stacked ensemble")]:
        print("training", name, flush=True)
        oof = np.empty(len(tr), dtype=object)
        for a, b in skf:
            Xa, Xb = feats(kind, tr.iloc[a], [tr.iloc[a], tr.iloc[b]])
            oof[b] = model(kind).fit(Xa, ytr[a]).predict(Xb)
        t0 = time.time()
        X = feats(kind, tr, [tr] + [sets[k] for k in evals])
        clf = model(kind).fit(X[0], ytr)
        fit_s = time.time() - t0
        t1 = time.time()
        preds[name] = {k: clf.predict(x) for k, x in zip(evals, X[1:])}
        ms = 1000 * (time.time() - t1) / sum(len(sets[k]) for k in evals)
        oofs[name] = oof
        meta[name] = {"family": fam, "trained": True, "fit_seconds": round(fit_s, 2), "ms_per_item": round(ms, 3)}

    for name, key in (("V8 Fine-tuned bge-small (33M)", "bge"), ("V9 Fine-tuned RoBERTa-base (125M)", "roberta")):
        p = M.OUT / ("ft_verdict_%s.npz" % key)
        if not p.exists():
            print("missing", p.name, "- run scripts/56 first; skipped")
            continue
        z = np.load(p)
        lg = json.loads((M.OUT / ("ft_verdict_%s.json" % key)).read_text())
        dec = lambda S: np.array(FT_ORDER)[S.argmax(1)]
        assert (np.array(FT_ORDER)[z["y"]] == ytr).all(), "fine-tuned run used different training pairs"
        oofs[name] = dec(z["oof"])
        preds[name] = {k: dec(z[k]) for k in evals}
        meta[name] = {"family": "fine-tuned transformer", "trained": True,
                      "fit_seconds": lg["final_fit_seconds"], "ms_per_item": lg["inference_ms_per_item_cpu"],
                      "training_loss_by_epoch": lg["final_fit_losses"]}

    gA = sets["gold_A"]
    agree = (gA.label_h2 != "") & (gA.label == gA.label_h2)
    has2 = gA.label_h2 != ""
    results = {}
    for name in oofs:
        r = {"meta": meta[name],
             "cv": dict(summary(oofs[name], ytr, ci=False),
                        fold_macro_f1=[summary(oofs[name][b], ytr[b], ci=False)["macro_f1"] for _, b in skf]),
             "test_random": summary(preds[name]["test_random"], sets["test_random"].label.values),
             "gold_A_reader1": summary(preds[name]["gold_A"], gA.label.values),
             "gold_A_reader2": summary(preds[name]["gold_A"][has2.values], gA.label_h2[has2].values),
             "gold_A_readers_agree": summary(preds[name]["gold_A"][agree.values], gA.label[agree].values),
             "gold_B_reader1": summary(preds[name]["gold_B"], sets["gold_B"].label.values)}
        r["cv"]["fold_sd"] = round(float(np.std(r["cv"]["fold_macro_f1"])), 3)
        results[name] = r
        print("%-44s CV mF1 %.3f acc %.3f | test acc %.3f mF1 %.3f | goldA acc %.3f (agree %.3f)" % (
            name, r["cv"]["macro_f1"], r["cv"]["accuracy"], r["test_random"]["accuracy"],
            r["test_random"]["macro_f1"], r["gold_A_reader1"]["accuracy"], r["gold_A_readers_agree"]["accuracy"]))

    ranked = sorted(results, key=lambda n: -results[n]["cv"]["macro_f1"])
    best, deployed = ranked[0], "V3 RoBERTa + correction rules (deployed)"
    sig = {}
    for k, gold in (("test_random", sets["test_random"].label.values), ("gold_A", gA.label.values)):
        sig[k] = mcnemar(preds[best][k], preds[deployed][k], gold)
    ceiling = summary(gA.label_h2[has2].values, gA.label[has2].values, ci=False)
    out = {"what_this_is": __doc__.strip().splitlines()[0],
           "selection_rule": "highest 5-fold stratified cross-validated macro-F1 on training pairs",
           "data": {k: {"pairs": int(len(v)), "labels": v.label.value_counts().to_dict(),
                        "source": v.source.value_counts().to_dict()} for k, v in sets.items()},
           "human_ceiling_gold_A": {"reader2_vs_reader1_accuracy": ceiling["accuracy"],
                                    "kappa": ceiling["kappa"], "pairs": ceiling["n"]},
           "ranking_by_cv": ranked, "best_by_cv": best,
           "best_vs_deployed_mcnemar": sig, "models": results}
    (M.OUT / "verdict_comparison.json").write_text(json.dumps(out, indent=1), encoding="utf8")
    print("best by CV:", best, "| McNemar vs deployed:", sig)


if __name__ == "__main__":
    main()
