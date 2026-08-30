"""Build a blank labelling sheet for the polarity gaps.

What this is for
----------------
`reports/polarity_accuracy.json` is the project's weakest measurement and the
one that matters most: the complaint rate IS the polarity call, aggregated.
Right now it says

    roads_access  0.421  (n=19, 95% CI [0.211, 0.632])   human ceiling 0.871
    facilities    0.636  (n=33, 95% CI [0.485, 0.788])   human ceiling 0.811
    safety        0.636  (n=11, 95% CI [0.364, 0.909])   human ceiling 0.958
    cleanliness   0.852  (n=27, 95% CI [0.704, 0.963])   human ceiling 0.975

and for scenery, price_value and crowd it says nothing at all, because nobody
has labelled them. Two problems there: safety's interval spans half the scale
and is uninformative, and three of the seven aspects -- one of which,
price_value, carries a 50.6% national rate -- have no accuracy figure of any
kind.

Neither is fixable by code. An accuracy figure requires somebody to read
sentences and say what they mean, and this project already refuses machine
labels for exactly this purpose (`agreement.py`). So this module does the part
that CAN be automated: it draws the right sample, writes a sheet that is quick
to fill, and gets out of the way.

Three sampling decisions, each with a reason
--------------------------------------------
**Representative, not stratified by prediction.** It is tempting to sample
equally across predicted complaint / praise / factual so every class is
covered. That produces a sample the accuracy estimate cannot be generalised
from, because it over-weights whatever the system is rare at. Pairs are drawn
uniformly at random from the pipeline-tagged pairs for each aspect, so the
resulting accuracy applies to the corpus.

**The system's verdict is not in the sheet.** Showing it would anchor the
reader on the answer being tested. This project has already been through the
version of that mistake -- an adjudicator who had seen annotator 1's answers
produced numbers that could not be used as agreement -- and the fix is the
same: label blind.

**Gold-set segments are excluded.** Re-labelling rows that already carry a
verdict adds no information and would let the same sentence count twice.

Run with:  python scripts/47_polarity_sheet.py
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import config as C

SEED = 20260830

# How many pairs to draw per aspect. Sized from what each aspect needs rather
# than set uniformly: a proportion near 0.7 needs roughly 80 observations for a
# +/-0.10 interval, which is the coarsest interval still worth reporting.
#
#   scenery / price_value / crowd  -- nothing at all exists, so a full sample
#   roads_access                   -- 0.421 is the worst result in the project
#                                     and rests on 19 pairs
#   safety                         -- interval [0.364, 0.909] is uninformative
#   cleanliness / facilities       -- already usable; topped up only lightly
DEFAULT_TARGETS = {
    "scenery": 80,
    "price_value": 80,
    "crowd": 80,
    "roads_access": 60,
    "safety": 60,
    "facilities": 30,
    "cleanliness": 30,
}

# Roughly how long one row takes. The judgement is three-way on a sentence
# whose aspect is already named, so it is much faster than the original gold
# set, where the reader also had to decide which aspects applied.
SECONDS_PER_ROW = 12

SHEET_COLUMNS = [
    "row", "segment_id", "aspect", "aspect_label", "destination", "district",
    "segment", "full_review", "verdict", "labelled_by", "notes",
]


def _gold_segment_ids() -> set:
    ids = set()
    for name in ("goldset_focused_annotator1.csv", "goldset_focused_annotator2.csv"):
        path = C.REPORTS / name
        if path.exists():
            ids |= set(pd.read_csv(path)["segment_id"].astype(str))
    return ids


def sample(targets: Optional[Dict[str, int]] = None, seed: int = SEED) -> Dict:
    """Draw the pairs to be labelled, and the record of how they were drawn."""
    from .aggregate import long_table

    targets = dict(targets or DEFAULT_TARGETS)
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_scored.csv")
    long = long_table(seg, verbose=False)

    exclude = _gold_segment_ids()
    long = long[~long["segment_id"].astype(str).isin(exclude)]

    # A truncated segment cannot be judged fairly -- the sentence that would
    # settle it may be the part Google cut off.
    if "is_truncated" in long.columns:
        long = long[~long["is_truncated"].fillna(False).astype(bool)]

    rng = np.random.default_rng(seed)
    picked, record = [], {}
    for aspect, want in targets.items():
        pool = long[long["aspect"] == aspect]
        take = int(min(want, len(pool)))
        if take == 0:
            record[aspect] = {"available": 0, "drawn": 0}
            continue
        idx = rng.choice(len(pool), size=take, replace=False)
        rows = pool.iloc[idx]
        record[aspect] = {"available": int(len(pool)), "drawn": take,
                          "sampling": "uniform at random, seed {}".format(seed)}
        for r in rows.to_dict("records"):
            picked.append({
                "segment_id": r["segment_id"],
                "aspect": aspect,
                "aspect_label": C.ASPECTS[aspect].label,
                "destination": r.get("destination", ""),
                "district": r.get("district", ""),
                "segment": r.get("segment", ""),
                "full_review": r.get("full_review", "") or r.get("segment", ""),
                "verdict": "",
                "labelled_by": "",
                "notes": "",
            })

    # Shuffle so the sheet does not run aspect by aspect. Labelling 80
    # consecutive scenery rows invites a rhythm, and a rhythm is a bias.
    order = rng.permutation(len(picked))
    picked = [picked[i] for i in order]
    for i, row in enumerate(picked, 1):
        row["row"] = i

    df = pd.DataFrame(picked)[SHEET_COLUMNS]
    return {"sheet": df, "sampling": record, "seed": seed,
            "excluded_gold_segments": len(exclude)}


GUIDE = [
    ["HOW TO FILL THIS IN", ""],
    ["", ""],
    ["Each row is one sentence and ONE topic.", ""],
    ["Put a single letter in the 'verdict' column:", ""],
    ["   N", "the visitor is COMPLAINING about this topic"],
    ["   P", "the visitor is PRAISING this topic"],
    ["   X", "neither -- they are just stating a fact about it"],
    ["", ""],
    ["Judge only the topic named in the 'aspect_label' column.", ""],
    ["A sentence can praise the view and complain about the road;", ""],
    ["answer for the one you are asked about, not for the sentence.", ""],
    ["", ""],
    ["'full_review' is context. Judge the 'segment'.", ""],
    ["", ""],
    ["A warning to other visitors ('be careful, it is slippery')", ""],
    ["counts as N. It reports a problem with the place, even though", ""],
    ["the writer may be enjoying themselves.", ""],
    ["", ""],
    ["Leave 'verdict' blank if you genuinely cannot tell. A guess is", ""],
    ["worse than a gap: it becomes an accuracy figure either way.", ""],
    ["", ""],
    ["Put your name in 'labelled_by' -- use the word 'human'.", ""],
    ["Files without it are refused by agreement.py, on purpose.", ""],
]


def write(result: Dict, stem: str = "LABEL_THESE_polarity") -> List:
    """Write the sheet as CSV, and as XLSX when openpyxl is installed."""
    df = result["sheet"]
    written = []

    csv_path = C.REPORTS / "{}.csv".format(stem)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    written.append(csv_path)

    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print("  (openpyxl not installed -- CSV only)")
        return written

    xlsx_path = C.REPORTS / "{}.xlsx".format(stem)
    with pd.ExcelWriter(str(xlsx_path), engine="openpyxl") as xl:
        pd.DataFrame(GUIDE, columns=["", " "]).to_excel(
            xl, sheet_name="How to fill this in", index=False)
        df.to_excel(xl, sheet_name="labels", index=False)

        ws = xl.sheets["labels"]
        widths = {"A": 6, "B": 20, "C": 14, "D": 20, "E": 22, "F": 14,
                  "G": 70, "H": 70, "I": 9, "J": 12, "K": 24}
        for col, w in widths.items():
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A2"
        for row in ws.iter_rows(min_row=2, min_col=7, max_col=8):
            for cell in row:
                cell.alignment = cell.alignment.copy(wrapText=True, vertical="top")

        # A dropdown on the verdict column. Fewer typos than free text, and it
        # makes the three options visible without reading the guide sheet.
        try:
            from openpyxl.worksheet.datavalidation import DataValidation
            dv = DataValidation(type="list", formula1='"N,P,X"', allow_blank=True)
            dv.error = "Use N (complaint), P (praise) or X (just a fact)."
            ws.add_data_validation(dv)
            dv.add("I2:I{}".format(len(df) + 1))
        except Exception:
            pass
        ws.sheet_view.showGridLines = False

        guide = xl.sheets["How to fill this in"]
        guide.column_dimensions["A"].width = 62
        guide.column_dimensions["B"].width = 58
        guide.sheet_view.showGridLines = False
    written.append(xlsx_path)
    return written


def main() -> None:
    print("\nLostinSriLanka -- polarity labelling sheet\n" + "=" * 62)
    result = sample()
    df = result["sheet"]

    print("  excluded {} segments already in the gold set".format(
        result["excluded_gold_segments"]))
    print()
    print("  {:<15} {:>10} {:>8}".format("aspect", "available", "drawn"))
    print("  " + "-" * 35)
    for aspect, rec in result["sampling"].items():
        print("  {:<15} {:>10} {:>8}".format(
            aspect, rec["available"], rec["drawn"]))
    print("  {:<15} {:>10} {:>8}".format("TOTAL", "", len(df)))

    mins = int(round(len(df) * SECONDS_PER_ROW / 60.0))
    print("\n  {} rows, roughly {} minutes at {}s a row".format(
        len(df), mins, SECONDS_PER_ROW))

    written = write(result)
    record = {
        "what_this_is":
            "How the polarity labelling sheet was drawn. Kept so the resulting "
            "accuracy figures state the sample behind them.",
        "seed": result["seed"],
        "n_rows": int(len(df)),
        "excluded_gold_segments": result["excluded_gold_segments"],
        "per_aspect": result["sampling"],
        "sampling_rule":
            "Uniform at random from the (segment, aspect) pairs the deployed "
            "pipeline tags, per aspect, excluding segments already in the gold "
            "set and segments the source truncated. NOT stratified by the "
            "system's predicted verdict: stratifying there would over-weight "
            "whatever the system is rare at, and the resulting accuracy could "
            "not be generalised to the corpus.",
        "blind":
            "The system's verdict is deliberately absent from the sheet.",
        "files": [p.name for p in written],
    }
    with open(str(C.REPORTS / "polarity_sheet_sampling.json"), "w",
              encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)

    for p in written:
        print("  wrote {}".format(p))
    print("\n  Fill the 'verdict' column, put 'human' in 'labelled_by',")
    print("  then re-run:  python scripts/43_evaluate_polarity.py")


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------
# The presence sheet
# --------------------------------------------------------------------------
PRESENCE_SHEET = "LABEL_THESE_presence"

PRESENCE_GUIDE = [
    ["HOW TO FILL THIS IN", ""],
    ["", ""],
    ["One question per row, and it is NOT the same question as last time.", ""],
    ["Last time you said whether the sentence complained or praised.", ""],
    ["This time: is the sentence ABOUT that topic at all?", ""],
    ["", ""],
    ["Put one letter in the 'is_about' column:", ""],
    ["   y", "yes, this sentence really is about that topic"],
    ["   n", "no, the topic does not belong on this sentence"],
    ["", ""],
    ["Example. 'We saw a few monkeys, a deer and a few birds' was tagged", ""],
    ["Safety. It is a wildlife sighting, not a hazard, so: n.", ""],
    ["", ""],
    ["Example. 'the tuk tuk drivers try to get a commission' was tagged", ""],
    ["Roads & Access. A tuk tuk is transport, but the complaint is about", ""],
    ["money. Judge whether the topic fits the sentence: n is defensible.", ""],
    ["", ""],
    ["Your earlier verdict is deliberately NOT shown. Having answered", ""],
    ["'complaint' about a topic makes it uncomfortable to then say the", ""],
    ["topic did not apply, and that reluctance would bias the answer.", ""],
    ["", ""],
    ["Leave blank if you genuinely cannot tell.", ""],
    ["Put 'human' in 'labelled_by'.", ""],
]

PRESENCE_COLUMNS = [
    "row", "segment_id", "aspect", "aspect_label", "destination", "district",
    "segment", "full_review", "is_about", "labelled_by", "notes",
]


def build_presence(source: str = "LABEL_THESE_polarity.csv") -> pd.DataFrame:
    """The same pairs again, asking whether the tag belongs at all.

    Why this is a second sheet rather than a column on the first
    -----------------------------------------------------------
    The polarity sheet asked one question -- complaint, praise or fact -- and
    offered no way to say "this is not about that topic". That was a design
    error, and it matters most exactly where extraction is weakest: roads
    extraction precision is 0.588, so roughly two in five roads-tagged
    segments are not about roads, and all 60 roads pairs were nonetheless
    given a verdict. The polarity figures are still the right measure of the
    verdict on what the pipeline counts; they simply do not establish that the
    tag was right.

    What this yields is extraction PRECISION -- of the pairs the pipeline
    tags, how many really are about that topic. Not recall, and not F1: this
    sample contains only pairs the pipeline already tagged, so it cannot see
    what the pipeline missed. Recall needs a different sample, drawn from
    untagged segments, and is a separate exercise.

    The earlier verdict is not carried across. Having called something a
    complaint about scenery makes it awkward to then say it was not about
    scenery, and that reluctance is a bias with a direction.
    """
    path = C.REPORTS / source
    if not path.exists():
        raise SystemExit(
            "{} does not exist. Run scripts/47_polarity_sheet.py and fill it "
            "in first -- this sheet re-asks about the same pairs.".format(path))
    df = pd.read_csv(path)
    out = df.copy()
    out["is_about"] = ""
    out["labelled_by"] = ""
    out["notes"] = ""
    return out[PRESENCE_COLUMNS]


def write_presence(df: pd.DataFrame) -> List:
    written = []
    csv_path = C.REPORTS / "{}.csv".format(PRESENCE_SHEET)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    written.append(csv_path)

    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print("  (openpyxl not installed -- CSV only)")
        return written

    xlsx_path = C.REPORTS / "{}.xlsx".format(PRESENCE_SHEET)
    with pd.ExcelWriter(str(xlsx_path), engine="openpyxl") as xl:
        pd.DataFrame(PRESENCE_GUIDE, columns=["", " "]).to_excel(
            xl, sheet_name="How to fill this in", index=False)
        df.to_excel(xl, sheet_name="labels", index=False)
        ws = xl.sheets["labels"]
        widths = {"A": 6, "B": 20, "C": 14, "D": 20, "E": 22, "F": 14,
                  "G": 70, "H": 70, "I": 10, "J": 12, "K": 24}
        for col, w in widths.items():
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A2"
        for row in ws.iter_rows(min_row=2, min_col=7, max_col=8):
            for cell in row:
                cell.alignment = cell.alignment.copy(wrapText=True, vertical="top")
        try:
            from openpyxl.worksheet.datavalidation import DataValidation
            dv = DataValidation(type="list", formula1='"y,n"', allow_blank=True)
            dv.error = "Use y (the topic fits) or n (it does not)."
            ws.add_data_validation(dv)
            dv.add("I2:I{}".format(len(df) + 1))
        except Exception:
            pass
        ws.sheet_view.showGridLines = False
        guide = xl.sheets["How to fill this in"]
        guide.column_dimensions["A"].width = 62
        guide.column_dimensions["B"].width = 58
        guide.sheet_view.showGridLines = False
    written.append(xlsx_path)
    return written


def main_presence() -> None:
    print("\nLostinSriLanka -- extraction presence sheet\n" + "=" * 62)
    df = build_presence()
    print("  {} rows, the same pairs as the polarity sheet".format(len(df)))
    print("  question: is this sentence about that topic at all? y / n")
    mins = int(round(len(df) * 4 / 60.0))
    print("  roughly {} minutes -- you have already read these sentences"
          .format(mins))
    print()
    print("  {:<15} {:>6}".format("aspect", "rows"))
    print("  " + "-" * 23)
    for aspect, n in df["aspect"].value_counts().items():
        print("  {:<15} {:>6}".format(aspect, n))
    for p in write_presence(df):
        print("\n  wrote {}".format(p))
    print("\n  Fill 'is_about', put 'human' in 'labelled_by',")
    print("  then re-run:  python scripts/44_accuracy_report.py")
