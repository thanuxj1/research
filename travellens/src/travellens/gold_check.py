"""
LostinSriLanka -- gold-set validator and agreement scorer.

Two jobs:
  1. Catch labelling mistakes early (typos, impossible letters, missed rows).
  2. Measure inter-annotator agreement (Cohen's kappa) once both people have
     labelled the 150-row overlap.

Run it whenever you like while labelling -- it works on partly-filled sheets.

Run with:  python scripts/05_check_goldset.py
"""
from typing import Optional

import pandas as pd

from . import config as C

VALID_LABELS = {"N", "P", "X"}
ASPECT_COLS = list(C.ASPECTS.keys())


def aspect_cols(df: pd.DataFrame) -> list:
    """The aspect columns this sheet actually has.

    The focused set covers four aspects, the full set all seven. Assuming
    seven crashed on the focused set, and reporting a kappa of 1.0 for a
    column that exists in neither sheet was worse than crashing -- it looked
    like perfect agreement about nothing.
    """
    return [c for c in ASPECT_COLS if c in df.columns]


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Uppercase, strip, and treat blank / '-' as 'not mentioned' (None)."""
    df = df.copy()
    for col in aspect_cols(df):
        s = df[col].astype(str).str.strip().str.upper()
        df[col] = s.where(s.isin(VALID_LABELS), None)
    return df


def validate(path) -> dict:
    """Report progress and any invalid cells in one annotator's sheet."""
    raw = pd.read_csv(path)
    df = _normalise(raw)
    cols = aspect_cols(raw)

    problems = []
    for col in cols:
        bad = raw[col].astype(str).str.strip().str.upper()
        mask = (~bad.isin(VALID_LABELS)) & (~bad.isin(["", "NAN", "-"]))
        for row, value in zip(raw.loc[mask, "row"], raw.loc[mask, col]):
            problems.append("row {}: column '{}' has '{}' -- expected N, P, X or blank"
                            .format(row, col, value))

    checked = raw["checked"].astype(str).str.strip().str.lower().isin(["x", "yes", "1", "true"])
    labelled_any = df[cols].notna().any(axis=1)
    # A row marked checked with no labels is fine (nothing applied); a row with
    # labels but not marked checked is probably unfinished.
    unmarked = int((labelled_any & ~checked).sum())

    counts = {c: df[c].value_counts().to_dict() for c in cols}
    return {
        "file": str(path),
        "rows": int(len(df)),
        "rows_checked": int(checked.sum()),
        "pct_complete": round(100 * checked.mean(), 1),
        "rows_with_labels_but_unchecked": unmarked,
        "invalid_cells": problems,
        "aspects": cols,
        "label_counts": counts,
        "frame": df,
    }


def cohens_kappa(a: pd.Series, b: pd.Series) -> Optional[float]:
    """Cohen's kappa for two label series over the same rows.

    Blank (not mentioned) is treated as its own category '-', because agreeing
    that an aspect is absent is genuine agreement.
    """
    a = a.fillna("-")
    b = b.fillna("-")
    n = len(a)
    if n == 0:
        return None
    categories = sorted(set(a) | set(b))
    observed = float((a == b).sum()) / n
    expected = sum((a == c).mean() * (b == c).mean() for c in categories)
    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)


def interpret(k: Optional[float]) -> str:
    if k is None:
        return "n/a"
    if k < 0.20:
        return "poor -- guidelines are not working"
    if k < 0.40:
        return "fair -- revise guidelines"
    if k < 0.60:
        return "moderate -- borderline, tighten unclear rules"
    if k < 0.80:
        return "substantial -- acceptable to report"
    return "almost perfect"


def agreement(path1, path2) -> dict:
    """Compare the overlapping rows of two annotators."""
    d1 = _normalise(pd.read_csv(path1)).set_index("segment_id")
    d2 = _normalise(pd.read_csv(path2)).set_index("segment_id")
    shared = d1.index.intersection(d2.index)

    # Only aspects BOTH sheets carry. Iterating all seven against the focused
    # set produced a kappa of 1.0 for columns neither file had -- perfect
    # agreement about nothing, which would have inflated the mean.
    out = {"overlap_rows": int(len(shared)), "per_aspect": {}}
    for col in [c for c in aspect_cols(d1) if c in aspect_cols(d2)]:
        k = cohens_kappa(d1.loc[shared, col], d2.loc[shared, col])
        out["per_aspect"][col] = {
            "kappa": None if k is None else round(k, 3),
            "verdict": interpret(k),
            "exact_agreement_pct": round(
                100 * float((d1.loc[shared, col].fillna("-") ==
                             d2.loc[shared, col].fillna("-")).mean()), 1),
        }
    ks = [v["kappa"] for v in out["per_aspect"].values() if v["kappa"] is not None]
    out["mean_kappa"] = round(sum(ks) / len(ks), 3) if ks else None
    out["overall_verdict"] = interpret(out["mean_kappa"])
    return out


def main(argv=None):
    """Checks the FOCUSED 200-row set by default.

    It used to check only the 600-row set. The README names the focused set as
    the outstanding task and scripts/35_annotate.py fills that one in, so
    somebody could label 200 rows and then find this script reading a
    different file and reporting nothing. --full restores the old target.
    """
    import argparse
    ap = argparse.ArgumentParser(description="Gold-set progress and agreement.")
    ap.add_argument("--full", action="store_true",
                    help="check the 600-row seven-aspect set instead")
    args = ap.parse_args(argv)

    stem = "goldset_annotator" if args.full else "goldset_focused_annotator"
    print("\nLostinSriLanka -- gold-set check\n" + "=" * 60)
    p1 = C.REPORTS / "{}1.csv".format(stem)
    p2 = C.REPORTS / "{}2.csv".format(stem)

    v = validate(p1)
    print("  {}".format(v["file"]))
    print("  progress : {} / {} rows checked ({}%)".format(
        v["rows_checked"], v["rows"], v["pct_complete"]))
    if v["rows_with_labels_but_unchecked"]:
        print("  warning  : {} rows have labels but no 'x' in checked".format(
            v["rows_with_labels_but_unchecked"]))
    if v["invalid_cells"]:
        print("  INVALID CELLS ({}):".format(len(v["invalid_cells"])))
        for p in v["invalid_cells"][:20]:
            print("    - {}".format(p))
    else:
        print("  no invalid cells")

    print("\n  label counts so far")
    print("  {:<16} {:>4} {:>4} {:>4}".format("aspect", "N", "P", "X"))
    print("  " + "-" * 32)
    for col, counts in v["label_counts"].items():
        print("  {:<16} {:>4} {:>4} {:>4}".format(
            col, counts.get("N", 0), counts.get("P", 0), counts.get("X", 0)))

    # A second reader who was SHOWN the first annotator's labels agrees with
    # them by construction. Reporting kappa from that would overstate the
    # reliability of the task, which is the one thing kappa exists to measure.
    adj = C.REPORTS / "goldset_adjudication.json"
    if adj.exists():
        import json
        with open(str(adj), encoding="utf-8") as fh:
            rec = json.load(fh)
        if rec.get("second_reader_saw_annotator_1_labels"):
            print("\n  NOTE: a second reader reviewed annotator 1's labels and")
            print("  changed {} row(s) -- see goldset_adjudication.json.".format(
                rec.get("rows_changed", 0)))
            print("  That is ADJUDICATION, not agreement. No kappa is computed")
            print("  from it: a reviewer starting from someone else's answers")
            print("  agrees with them by construction. An independent blind")
            print("  pass over the same 200 rows is still outstanding.")

    v2 = validate(p2)
    if v2["rows_checked"] > 0 and v["rows_checked"] > 0:
        print("\n  inter-annotator agreement")
        a = agreement(p1, p2)
        print("  overlap rows: {}".format(a["overlap_rows"]))
        print("  {:<16} {:>7}  {}".format("aspect", "kappa", "verdict"))
        print("  " + "-" * 52)
        for col, info in a["per_aspect"].items():
            print("  {:<16} {:>7}  {}".format(col, info["kappa"], info["verdict"]))
        print("\n  MEAN KAPPA: {}  ({})".format(a["mean_kappa"], a["overall_verdict"]))
    else:
        print("\n  agreement not computed yet -- annotator 2 sheet is still empty")


if __name__ == "__main__":
    main()
