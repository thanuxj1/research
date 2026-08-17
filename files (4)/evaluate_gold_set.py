"""
Gold Set Evaluator — SafeTravel LK
IT22629180

Implements the script referenced but missing from
`backend/scripts/gold_set_instructions.md` Step 4.

This is the ONLY valid measure of system accuracy in the project.
`show_model_accuracy.py` cross-validates model output against labels produced
by the same keyword rules being tested, and carries its own warning saying so.

Design commitments, each of which exists to stop a specific way of overstating
a result:

  1. Corpora are evaluated and reported SEPARATELY. News records and review
     records have different base rates; a pooled figure hides that and inflates
     whichever corpus is easier.
  2. Per-class metrics are reported ONLY for classes with support >= MIN_SUPPORT.
     An F1 computed on n=1 is noise presented as a result.
  3. Every headline metric carries a bootstrap 95% CI. A point estimate from
     n<400 without an interval is not a finding.
  4. `gold_confidence == "low"` records are excluded and the excluded count is
     reported. Silently dropping ambiguous cases inflates every metric.
  5. Cohen's kappa is reported whatever its value. A low kappa means the task
     definition is unclear — that is a result about the task, not a failure to
     hide.

Usage
-----
    python evaluate_gold_set.py --gold gold_set_annotated.csv
    python evaluate_gold_set.py --gold gold.csv --second-annotator gold_b.csv
    python evaluate_gold_set.py --gold gold.csv --json results.json

Expected columns (see gold_set_instructions.md):
    id, corpus, source, is_scam_model, scam_type_model, location_name_model,
    geocode_confidence, gold_is_scam, gold_scam_type, gold_location,
    gold_victim_profile (optional), gold_confidence
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

import numpy as np
import pandas as pd

MIN_SUPPORT = 20          # per-class metrics suppressed below this
N_BOOTSTRAP = 2000
RNG = np.random.default_rng(42)


# ─────────────────────────────────────────────────────────────────────────────
# Metric helpers
# ─────────────────────────────────────────────────────────────────────────────

def _prf(y_true: np.ndarray, y_pred: np.ndarray, positive) -> tuple[float, float, float, int]:
    tp = int(np.sum((y_pred == positive) & (y_true == positive)))
    fp = int(np.sum((y_pred == positive) & (y_true != positive)))
    fn = int(np.sum((y_pred != positive) & (y_true == positive)))
    support = int(np.sum(y_true == positive))
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f, support


def _bootstrap_ci(y_true: np.ndarray, y_pred: np.ndarray, positive,
                  metric: str = "f1", n: int = N_BOOTSTRAP) -> tuple[float, float]:
    """Percentile bootstrap CI. Resamples records, not predictions."""
    if len(y_true) == 0:
        return (float("nan"), float("nan"))
    idx_map = {"precision": 0, "recall": 1, "f1": 2}[metric]
    vals = []
    n_obs = len(y_true)
    for _ in range(n):
        idx = RNG.integers(0, n_obs, n_obs)
        vals.append(_prf(y_true[idx], y_pred[idx], positive)[idx_map])
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — the correct interval for a proportion at small n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _cohen_kappa(a: pd.Series, b: pd.Series) -> float:
    a, b = a.astype(str), b.astype(str)
    labels = sorted(set(a) | set(b))
    n = len(a)
    if n == 0:
        return float("nan")
    po = float(np.mean(a.values == b.values))
    pe = sum((np.mean(a.values == l) * np.mean(b.values == l)) for l in labels)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


# ─────────────────────────────────────────────────────────────────────────────
# Reports
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_binary(df: pd.DataFrame, corpus_name: str) -> dict:
    y_true = df["gold_is_scam"].astype(int).values
    y_pred = df["is_scam_model"].astype(int).values

    p, r, f, support = _prf(y_true, y_pred, 1)
    p_ci = _bootstrap_ci(y_true, y_pred, 1, "precision")
    r_ci = _bootstrap_ci(y_true, y_pred, 1, "recall")
    f_ci = _bootstrap_ci(y_true, y_pred, 1, "f1")

    tp = int(np.sum((y_pred == 1) & (y_true == 1)))
    fp = int(np.sum((y_pred == 1) & (y_true == 0)))
    fn = int(np.sum((y_pred == 0) & (y_true == 1)))
    tn = int(np.sum((y_pred == 0) & (y_true == 0)))

    print(f"\n{'=' * 74}")
    print(f"  INCIDENT DETECTION — corpus: {corpus_name}   (n = {len(df)})")
    print(f"{'=' * 74}")
    print(f"  Positive base rate (gold) : {support}/{len(df)} = {support / len(df):.3f}")
    print(f"  Precision : {p:.3f}   95% CI [{p_ci[0]:.3f}, {p_ci[1]:.3f}]")
    print(f"  Recall    : {r:.3f}   95% CI [{r_ci[0]:.3f}, {r_ci[1]:.3f}]")
    print(f"  F1        : {f:.3f}   95% CI [{f_ci[0]:.3f}, {f_ci[1]:.3f}]")
    print(f"\n  Confusion matrix          predicted")
    print(f"                          scam   not")
    print(f"        actual  scam    {tp:>5}  {fn:>5}")
    print(f"                not     {fp:>5}  {tn:>5}")

    return {"corpus": corpus_name, "n": int(len(df)), "positives": support,
            "precision": p, "precision_ci": p_ci,
            "recall": r, "recall_ci": r_ci,
            "f1": f, "f1_ci": f_ci,
            "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}}


def evaluate_multiclass(df: pd.DataFrame, corpus_name: str,
                        gold_col: str, pred_col: str, task: str) -> dict:
    sub = df[df[gold_col].notna() & (df[gold_col].astype(str).str.strip() != "")]
    if sub.empty:
        print(f"\n  [{task}] no annotated labels present — skipped")
        return {}

    y_true = sub[gold_col].astype(str).values
    y_pred = sub[pred_col].astype(str).values
    counts = Counter(y_true)

    print(f"\n{'=' * 74}")
    print(f"  {task.upper()} — corpus: {corpus_name}   (n = {len(sub)})")
    print(f"{'=' * 74}")
    print(f"  {'class':<28}{'prec':>7}{'rec':>7}{'F1':>7}{'support':>9}")
    print("  " + "-" * 58)

    per_class, reported_f1, suppressed = {}, [], []
    for cls in sorted(counts, key=lambda c: -counts[c]):
        p, r, f, sup = _prf(y_true, y_pred, cls)
        per_class[cls] = {"precision": p, "recall": r, "f1": f, "support": sup}
        if sup >= MIN_SUPPORT:
            print(f"  {cls:<28}{p:>7.3f}{r:>7.3f}{f:>7.3f}{sup:>9}")
            reported_f1.append(f)
        else:
            suppressed.append((cls, sup))

    macro = float(np.mean(reported_f1)) if reported_f1 else float("nan")
    print("  " + "-" * 58)
    print(f"  {'MACRO-F1 (support >= ' + str(MIN_SUPPORT) + ')':<28}{'':>14}{macro:>7.3f}"
          f"{sum(counts[c] for c in counts if counts[c] >= MIN_SUPPORT):>9}")
    if suppressed:
        print(f"\n  Suppressed (support < {MIN_SUPPORT}) — reported for transparency, "
              f"NOT scored:")
        for cls, sup in sorted(suppressed, key=lambda x: -x[1]):
            print(f"    {cls:<40} n = {sup}")
        print("  State in the thesis that these classes are unmeasurable at this corpus size.")

    return {"corpus": corpus_name, "task": task, "n": int(len(sub)),
            "macro_f1_supported": macro, "per_class": per_class,
            "suppressed_classes": dict(suppressed)}


def evaluate_geocoding(df: pd.DataFrame, corpus_name: str) -> dict:
    sub = df[df["gold_location"].notna() & (df["gold_location"].astype(str).str.strip() != "")]
    if sub.empty:
        print("\n  [geocoding] no gold locations — skipped")
        return {}

    correct = (sub["gold_location"].astype(str).str.strip().str.lower()
               == sub["location_name_model"].astype(str).str.strip().str.lower())
    acc = float(correct.mean())
    lo, hi = _wilson(int(correct.sum()), len(sub))

    print(f"\n{'=' * 74}")
    print(f"  GEOCODING — corpus: {corpus_name}   (n = {len(sub)})")
    print(f"{'=' * 74}")
    print(f"  Overall district accuracy : {acc:.3f}   95% Wilson [{lo:.3f}, {hi:.3f}]")

    bands = {}
    if "geocode_confidence" in sub.columns:
        print(f"\n  {'confidence band':<24}{'accuracy':>10}{'n':>7}   95% CI")
        print("  " + "-" * 62)
        for band, grp in sub.groupby(sub["geocode_confidence"].astype(str)):
            c = (grp["gold_location"].astype(str).str.strip().str.lower()
                 == grp["location_name_model"].astype(str).str.strip().str.lower())
            b_lo, b_hi = _wilson(int(c.sum()), len(grp))
            bands[band] = {"accuracy": float(c.mean()), "n": int(len(grp)),
                           "ci": [b_lo, b_hi]}
            print(f"  {band:<24}{c.mean():>10.3f}{len(grp):>7}   [{b_lo:.3f}, {b_hi:.3f}]")
        print("\n  Decision rule: exclude any band whose upper CI bound is below 0.60")
        print("  from district scoring, and state the exclusion in the methodology.")

    # Colombo over-attribution check (AUDIT M8)
    col_pred = sub[sub["location_name_model"].astype(str).str.strip().str.lower() == "colombo"]
    colombo = {}
    if len(col_pred):
        c = (col_pred["gold_location"].astype(str).str.strip().str.lower() == "colombo")
        c_lo, c_hi = _wilson(int(c.sum()), len(col_pred))
        colombo = {"n_predicted": int(len(col_pred)), "precision": float(c.mean()),
                   "ci": [c_lo, c_hi]}
        print(f"\n  Colombo attribution precision: {c.mean():.3f} "
              f"[{c_lo:.3f}, {c_hi:.3f}]  (n = {len(col_pred)} predicted Colombo)")
        print("  Low precision here indicates dateline/byline attribution bias,")
        print("  not that Colombo is genuinely over-represented in incidents.")

    return {"corpus": corpus_name, "overall_accuracy": acc, "ci": [lo, hi],
            "by_confidence_band": bands, "colombo": colombo}


# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate against the hand-labelled gold set.")
    ap.add_argument("--gold", required=True, help="annotated gold set CSV")
    ap.add_argument("--second-annotator", help="second annotator CSV for Cohen's kappa")
    ap.add_argument("--json", help="write structured results to this path")
    args = ap.parse_args()

    df = pd.read_csv(args.gold)

    required = {"gold_is_scam", "is_scam_model"}
    missing = required - set(df.columns)
    if missing:
        print(f"ERROR: gold set is missing required columns: {sorted(missing)}")
        return 2

    df = df[df["gold_is_scam"].notna()]
    n_total = len(df)

    # Exclusion of ambiguous records — reported, never silent
    n_low = 0
    if "gold_confidence" in df.columns:
        low = df["gold_confidence"].astype(str).str.lower() == "low"
        n_low = int(low.sum())
        df = df[~low]

    print("=" * 74)
    print("  SafeTravel LK — GOLD SET EVALUATION   [IT22629180]")
    print("=" * 74)
    print(f"  Annotated records         : {n_total}")
    print(f"  Excluded (confidence=low) : {n_low}")
    print(f"  Evaluated                 : {len(df)}")
    print(f"  Per-class support floor   : {MIN_SUPPORT}")
    print(f"  Bootstrap resamples       : {N_BOOTSTRAP}")

    results: dict = {"n_annotated": n_total, "n_excluded_low_confidence": n_low,
                     "n_evaluated": int(len(df)), "min_support": MIN_SUPPORT,
                     "corpora": []}

    if "corpus" not in df.columns:
        print("\n  WARNING: no 'corpus' column. Corpora with different base rates")
        print("  must not be pooled — add a 'corpus' column before reporting.")
        df = df.assign(corpus="pooled_UNSAFE")

    for corpus_name, grp in df.groupby(df["corpus"].astype(str)):
        block = {"binary": evaluate_binary(grp, corpus_name)}
        if {"gold_scam_type", "scam_type_model"} <= set(grp.columns):
            block["scam_type"] = evaluate_multiclass(
                grp, corpus_name, "gold_scam_type", "scam_type_model", "incident type")
        if {"gold_victim_profile", "victim_profile_model"} <= set(grp.columns):
            block["victim_profile"] = evaluate_multiclass(
                grp, corpus_name, "gold_victim_profile", "victim_profile_model",
                "victim demographic")
            unknown = (grp["gold_victim_profile"].astype(str).str.lower() == "unknown").mean()
            print(f"\n  Gold 'unknown' rate: {unknown:.3f} — report this. It bounds what")
            print("  ANY profile-adaptive system can achieve on this class of source.")
            block["victim_profile"]["gold_unknown_rate"] = float(unknown)
        if {"gold_location", "location_name_model"} <= set(grp.columns):
            block["geocoding"] = evaluate_geocoding(grp, corpus_name)
        results["corpora"].append(block)

    # Inter-annotator agreement
    if args.second_annotator:
        b = pd.read_csv(args.second_annotator)
        merged = df.merge(b[["id", "gold_is_scam"]], on="id", suffixes=("_a", "_b"))
        if len(merged):
            k = _cohen_kappa(merged["gold_is_scam_a"], merged["gold_is_scam_b"])
            agree = float((merged["gold_is_scam_a"] == merged["gold_is_scam_b"]).mean())
            print(f"\n{'=' * 74}")
            print("  INTER-ANNOTATOR AGREEMENT")
            print(f"{'=' * 74}")
            print(f"  Double-annotated : {len(merged)} ({len(merged) / len(df) * 100:.1f}% of set)")
            print(f"  Raw agreement    : {agree:.3f}")
            print(f"  Cohen's kappa    : {k:.3f}")
            verdict = ("substantial — task definition is sound" if k >= 0.70 else
                       "moderate — tighten the annotation guideline and re-label"
                       if k >= 0.40 else
                       "poor — the task definition itself is ambiguous; revise before "
                       "reporting any downstream metric")
            print(f"  Interpretation   : {verdict}")
            print("  Report this value regardless of what it is.")
            results["kappa"] = {"value": k, "raw_agreement": agree, "n": int(len(merged))}
        else:
            print("\n  WARNING: no overlapping ids between annotators — kappa not computed")

    print(f"\n{'=' * 74}")
    print("  These are the numbers to report. Do not report any figure from")
    print("  show_model_accuracy.py as an accuracy result — its labels and its")
    print("  predictions share a generating process.")
    print(f"{'=' * 74}\n")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=2, default=float)
        print(f"  Structured results written to {args.json}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
