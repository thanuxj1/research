"""
LostinSriLanka -- Stage 4: gold-set construction.

Builds the human annotation sheet that every later measurement is scored
against. This file does NOT label anything; it decides WHICH segments a human
should read, and writes them to a spreadsheet.

Three sampling rules, each defensible in the viva
-------------------------------------------------
1. STRATIFIED, not random.
   A random sample of this corpus is dominated by scenery. We take a quota from
   each aspect so the rare ones (safety, cleanliness, price) are measurable.

2. NEGATIVES ARE INCLUDED.
   A quota is drawn from segments the keyword baseline matched to NOTHING.
   Without these we could only measure precision (were the matches correct?)
   and never recall (what did we miss?). This is the single most common flaw in
   student evaluation sets.

3. HARD CASES ARE OVER-SAMPLED.
   A quota of contrast segments ("but", "however") -- the cases where praise and
   complaint sit together and where methods actually differ. Sampling only easy
   cases would make every method look identical.

Output
------
reports/goldset_annotator1.csv   full sheet to label
reports/goldset_annotator2.csv   overlap subset for inter-annotator agreement
reports/goldset_sampling.json    the sampling audit trail

Run with:  python scripts/04_build_goldset.py
"""
import json
from typing import Dict

import pandas as pd

from . import config as C

RANDOM_SEED = 42          # fixed so the sample is reproducible
QUOTA_PER_ASPECT = 60     # from segments the baseline matched to this aspect
QUOTA_UNMATCHED = 120     # from segments the baseline matched to nothing
QUOTA_CONTRAST = 60       # from "but / however / although" segments
OVERLAP_FOR_AGREEMENT = 150   # double-labelled subset

LABEL_KEY = {
    "N": "Negative -- the visitor is complaining about this aspect",
    "P": "Positive -- the visitor is praising this aspect",
    "X": "Neutral  -- aspect mentioned as fact only, no opinion",
    "-": "Not mentioned (leave blank; blank is read as '-')",
}


def build_goldset(seg: pd.DataFrame, reviews: pd.DataFrame) -> Dict:
    """Draw the stratified sample and write the annotation sheets."""
    usable = seg[~seg["too_short"]].copy()
    picked = {}          # segment_id -> reason it was picked
    frames = []

    def take(pool: pd.DataFrame, n: int, reason: str):
        pool = pool[~pool["segment_id"].isin(picked)]
        if len(pool) == 0:
            return
        got = pool.sample(min(n, len(pool)), random_state=RANDOM_SEED)
        for sid in got["segment_id"]:
            picked[sid] = reason
        frames.append(got)

    # -- quota 1: per aspect --------------------------------------------
    for key, aspect in C.ASPECTS.items():
        take(usable[usable["asp_" + key]], QUOTA_PER_ASPECT, "aspect:" + key)

    # -- quota 2: hard contrast cases ------------------------------------
    contrast = usable[usable["segment"].str.contains(
        r"\b(?:but|however|although|though)\b", case=False, regex=True, na=False)]
    take(contrast, QUOTA_CONTRAST, "contrast")

    # -- quota 3: matched nothing (lets us measure recall) ---------------
    take(usable[usable["n_aspects"] == 0], QUOTA_UNMATCHED, "unmatched")

    gold = pd.concat(frames, ignore_index=True)
    gold["sample_reason"] = gold["segment_id"].map(picked)

    # -- attach full review text so the annotator judges in context -------
    ctx = reviews.set_index("review_id")["text"].to_dict()
    gold["full_review"] = gold["review_id"].map(ctx)

    # -- build the sheet --------------------------------------------------
    sheet = gold[[
        "segment_id", "destination", "district", "segment", "full_review",
        "sample_reason", "is_truncated",
    ]].copy()
    # Blank columns for the human to fill: one letter per aspect.
    for key in C.ASPECTS:
        sheet[key] = ""
    sheet["checked"] = ""
    sheet["notes"] = ""

    # Shuffle so the annotator does not label all safety rows in a block --
    # labelling one aspect repeatedly drifts the criteria.
    sheet = sheet.sample(frac=1.0, random_state=RANDOM_SEED).reset_index(drop=True)
    sheet.insert(0, "row", range(1, len(sheet) + 1))

    C.REPORTS.mkdir(parents=True, exist_ok=True)
    p1 = C.REPORTS / "goldset_annotator1.csv"
    p2 = C.REPORTS / "goldset_annotator2.csv"
    sheet.to_csv(p1, index=False, encoding="utf-8-sig")   # utf-8-sig: opens cleanly in Excel
    sheet.head(OVERLAP_FOR_AGREEMENT).to_csv(p2, index=False, encoding="utf-8-sig")

    report = {
        "random_seed": RANDOM_SEED,
        "total_segments_sampled": int(len(sheet)),
        "quota_per_aspect": QUOTA_PER_ASPECT,
        "quota_unmatched": QUOTA_UNMATCHED,
        "quota_contrast": QUOTA_CONTRAST,
        "overlap_for_agreement": OVERLAP_FOR_AGREEMENT,
        "by_reason": sheet["sample_reason"].value_counts().to_dict(),
        "distinct_destinations": int(sheet["destination"].nunique()),
        "distinct_districts": int(sheet["district"].nunique()),
        "truncated_in_sample": int(sheet["is_truncated"].sum()),
        "label_key": LABEL_KEY,
        "files": {"annotator1": str(p1), "annotator2": str(p2)},
    }
    return report, sheet


def main():
    print("\nLostinSriLanka -- Stage 4: gold-set construction\n" + "=" * 60)
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_tagged.csv")
    reviews = pd.read_csv(C.CLEAN_REVIEWS_CSV)

    report, sheet = build_goldset(seg, reviews)

    with open(C.REPORTS / "goldset_sampling.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("  sampled {} segments".format(report["total_segments_sampled"]))
    print("  from {} destinations in {} districts".format(
        report["distinct_destinations"], report["distinct_districts"]))
    print()
    print("  {:<24} {:>6}".format("picked because", "rows"))
    print("  " + "-" * 32)
    for reason, n in sorted(report["by_reason"].items(), key=lambda kv: -kv[1]):
        print("  {:<24} {:>6}".format(reason, n))
    print()
    print("  annotator 1 sheet : {}".format(report["files"]["annotator1"]))
    print("  annotator 2 sheet : {}  ({} rows for agreement)".format(
        report["files"]["annotator2"], OVERLAP_FOR_AGREEMENT))


if __name__ == "__main__":
    main()
