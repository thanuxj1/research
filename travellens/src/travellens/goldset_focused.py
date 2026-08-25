"""
TravelLens LK -- the focused gold set.

A 600-row annotation sheet costs about three hours. This module builds a
~200-row sheet costing about 45 minutes that still supports a defensible
evaluation, by spending the labelling budget where it buys the most
information.

Three scope reductions, each stated openly in the thesis
-------------------------------------------------------
1. FOUR aspects, not seven. Roads, Cleanliness, Facilities and Safety are
   labelled and carry measured claims. Price, Crowding and Scenery are reported
   as exploratory and explicitly excluded from the accuracy claims. Four
   defended findings are worth more than seven undefended ones.

2. ~200 segments, not 600. Fewer labels widen the confidence interval; they do
   not invalidate the estimate. The interval is reported rather than hidden.

3. Informative sampling. Segments where the methods already agree teach almost
   nothing. Segments where they disagree are where the evaluation actually
   discriminates between them.

The split that makes (3) safe
-----------------------------
Labelling ONLY disagreements would understate accuracy: hard cases are not
representative of the corpus. So the sheet has two parts, used for different
purposes and never pooled into one headline number:

  PART A -- representative (stratified random)
            the ONLY part used for the reported accuracy / macro-F1

  PART B -- disagreement-enriched
            used for method comparison and error analysis, reported separately
            and always labelled as an enriched sample

Mixing them would inflate apparent difficulty and produce a number that
describes neither the corpus nor the hard cases. The `part` column keeps them
separable forever.

Run with:  python scripts/13_build_focused_goldset.py
"""
import json
from typing import Dict, List

import pandas as pd

from . import config as C

RANDOM_SEED = 42

# The four aspects that will carry measured claims.
FOCUS_ASPECTS = ["roads_access", "cleanliness", "facilities", "safety"]

PART_A_PER_ASPECT = 30      # 4 x 30 = 120 representative
PART_B_TOTAL = 80           # disagreement-enriched
OVERLAP_FOR_AGREEMENT = 60  # second annotator subset

# Columns holding each method's prediction, in method order.
METHOD_COLS = ["pol_lexicon", "pol_model", "pol_hybrid", "pol_roberta", "pol_final"]


def disagreement_score(row) -> int:
    """How many distinct labels the available methods produced for this segment.

    1 = every method agrees (labelling it confirms what we already know)
    3 = the methods split across all of N / P / X (maximum information)
    """
    vals = {row[c] for c in METHOD_COLS if c in row.index and pd.notna(row[c])}
    return len(vals)


def build(seg: pd.DataFrame, reviews: pd.DataFrame) -> Dict:
    usable = seg[(~seg["too_short"]) & (seg["n_aspects"] > 0)].copy()
    available = [c for c in METHOD_COLS if c in usable.columns]
    usable["n_distinct_labels"] = usable.apply(disagreement_score, axis=1)

    picked: Dict[str, str] = {}
    frames: List[pd.DataFrame] = []

    def take(pool: pd.DataFrame, n: int, reason: str, part: str):
        pool = pool[~pool["segment_id"].isin(picked)]
        if pool.empty or n <= 0:
            return
        got = pool.sample(min(n, len(pool)), random_state=RANDOM_SEED).copy()
        got["sample_reason"] = reason
        got["part"] = part
        for sid in got["segment_id"]:
            picked[sid] = reason
        frames.append(got)

    # -- PART A: representative, stratified by aspect ----------------------
    for aspect in FOCUS_ASPECTS:
        take(usable[usable["asp_" + aspect]], PART_A_PER_ASPECT,
             "representative:" + aspect, "A_representative")

    # -- PART B: disagreement-enriched, spread across the four aspects -----
    per_aspect = max(1, PART_B_TOTAL // len(FOCUS_ASPECTS))
    for aspect in FOCUS_ASPECTS:
        pool = usable[(usable["asp_" + aspect]) & (usable["n_distinct_labels"] >= 2)]
        pool = pool.sort_values("n_distinct_labels", ascending=False)
        # Take from the most-contested first, but sample within that band so
        # the selection is not deterministic on one quirk of the data.
        top = pool.head(max(per_aspect * 4, per_aspect))
        take(top, per_aspect, "disagreement:" + aspect, "B_disagreement")

    gold = pd.concat(frames, ignore_index=True)

    ctx = reviews.set_index("review_id")["text"].to_dict()
    gold["full_review"] = gold["review_id"].map(ctx)

    sheet = gold[[
        "segment_id", "part", "destination", "district", "segment",
        "full_review", "sample_reason", "n_distinct_labels", "is_truncated",
    ]].copy()
    for aspect in FOCUS_ASPECTS:
        sheet[aspect] = ""
    sheet["checked"] = ""
    sheet["notes"] = ""

    sheet = sheet.sample(frac=1.0, random_state=RANDOM_SEED).reset_index(drop=True)
    sheet.insert(0, "row", range(1, len(sheet) + 1))

    C.REPORTS.mkdir(parents=True, exist_ok=True)
    p1 = C.REPORTS / "goldset_focused_annotator1.csv"
    p2 = C.REPORTS / "goldset_focused_annotator2.csv"
    sheet.to_csv(p1, index=False, encoding="utf-8-sig")
    sheet.head(OVERLAP_FOR_AGREEMENT).to_csv(p2, index=False, encoding="utf-8-sig")

    report = {
        "random_seed": RANDOM_SEED,
        "focus_aspects": FOCUS_ASPECTS,
        "excluded_aspects": [a for a in C.ASPECTS if a not in FOCUS_ASPECTS],
        "methods_compared": available,
        "total_rows": int(len(sheet)),
        "part_A_representative": int((sheet["part"] == "A_representative").sum()),
        "part_B_disagreement": int((sheet["part"] == "B_disagreement").sum()),
        "overlap_for_agreement": OVERLAP_FOR_AGREEMENT,
        "estimated_minutes": int(len(sheet) * 4 * 3.5 / 60),
        "distinct_destinations": int(sheet["destination"].nunique()),
        "distinct_districts": int(sheet["district"].nunique()),
        "usage_rule": (
            "Headline accuracy and macro-F1 are computed on Part A only. Part B "
            "is a deliberately enriched sample of contested cases and is reported "
            "separately for method comparison and error analysis. The two parts "
            "must never be pooled into a single accuracy figure."
        ),
        "files": {"annotator1": str(p1), "annotator2": str(p2)},
    }
    with open(C.REPORTS / "goldset_focused_sampling.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return report, sheet


def main():
    print("\nTravelLens LK -- focused gold set\n" + "=" * 60)
    seg_path = C.DATA_PROCESSED / "segments_scored.csv"
    if not seg_path.exists():
        raise SystemExit("run scripts/10_refresh.py first -- need method predictions")

    seg = pd.read_csv(seg_path)
    reviews = pd.read_csv(C.CLEAN_REVIEWS_CSV)
    report, sheet = build(seg, reviews)

    print("  aspects labelled   : {}".format(", ".join(report["focus_aspects"])))
    print("  aspects excluded   : {}  (reported as exploratory)".format(
        ", ".join(report["excluded_aspects"])))
    print("  methods compared   : {}".format(len(report["methods_compared"])))
    print()
    print("  Part A representative : {:>3} rows  <- headline accuracy comes from here".format(
        report["part_A_representative"]))
    print("  Part B disagreement   : {:>3} rows  <- method comparison, reported separately".format(
        report["part_B_disagreement"]))
    print("  TOTAL                 : {:>3} rows".format(report["total_rows"]))
    print()
    print("  covers {} destinations in {} districts".format(
        report["distinct_destinations"], report["distinct_districts"]))
    print("  estimated time     : ~{} minutes".format(report["estimated_minutes"]))
    print()
    print("  annotator 1 : {}".format(report["files"]["annotator1"]))
    print("  annotator 2 : {}  ({} rows for agreement)".format(
        report["files"]["annotator2"], OVERLAP_FOR_AGREEMENT))


if __name__ == "__main__":
    main()
