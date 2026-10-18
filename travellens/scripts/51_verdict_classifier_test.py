"""Does a classifier trained on human verdict labels beat the deployed chain?

  python scripts/51_verdict_classifier_test.py

The deployed verdict (pol_final plus the correction rules) is scored against two
human readers by 43_evaluate_polarity.py. This asks whether the obvious
improvement -- training a classifier on the human-labelled sentences -- would
help. It is a TEST, not a pipeline stage: nothing here writes to the corpus.

Design, to avoid leakage
  train : the 420-row supplementary sheet (part S, one reader)
  test  : the focused gold set, Part A (representative) and Part B (contested),
          which the classifier never sees. Part A is the headline; Part B is
          reported apart, as everywhere else in this project.

Result at the time of writing (2026-10): it does NOT help. Accuracy on Part A
against reader 1 is 0.62-0.64 for the trained models against 0.656 for the
deployed chain, and Part B is worse. The deployed chain is therefore unchanged.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from travellens import config as C
from travellens import polarity_eval as pe

LABELS = list("NPX")


def build_table() -> pd.DataFrame:
    pairs = pe.load_pairs()["pairs"]
    seg = pd.read_csv(
        C.DATA_PROCESSED / "segments_scored.csv",
        usecols=["segment_id", "segment", "pol_lexicon", "pol_model", "pol_roberta", "pol_roberta_conf"])
    d = pairs.merge(seg, on="segment_id", how="left")
    return d[d.human1.isin(LABELS) & d.pred.notna()].copy()


def main() -> None:
    D = build_table()
    S, A, B = (D[D.part == p] for p in ("S", "A", "B"))
    cat_cols = ["pol_roberta", "pol_lexicon", "pol_model", "aspect"]
    cols = pd.get_dummies(D[cat_cols].astype(str)).columns

    def feats(df, vec, fit=False):
        cat = pd.get_dummies(df[cat_cols].astype(str)).astype(float).reindex(columns=cols, fill_value=0)
        text = vec.fit_transform(df.segment) if fit else vec.transform(df.segment)
        conf = csr_matrix(df[["pol_roberta_conf"]].values.astype(float))
        return hstack([text, csr_matrix(cat.values), conf]).tocsr()

    def acc(df, col, pred):
        return round(float((df[col] == pred).mean()), 3)

    a2 = A[A.human2.isin(LABELS)]
    print("train: part S n=%d | test: Part A n=%d (reader 2: n=%d), Part B n=%d" % (len(S), len(A), len(a2), len(B)))
    print("%-14s %8s %10s %8s" % ("", "A vs h1", "A vs h2", "B vs h1"))
    print("%-14s %8s %10s %8s" % ("deployed", acc(A, "human1", A.pred), acc(a2, "human2", a2.pred), acc(B, "human1", B.pred)))
    for c in (0.3, 1, 3, 10):
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
        m = LogisticRegression(C=c, max_iter=2000, class_weight="balanced").fit(feats(S, vec, True), S.human1)
        print("%-14s %8s %10s %8s" % ("trained C=%s" % c, acc(A, "human1", m.predict(feats(A, vec))),
                                      acc(a2, "human2", m.predict(feats(a2, vec))), acc(B, "human1", m.predict(feats(B, vec)))))


if __name__ == "__main__":
    main()
