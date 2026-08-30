"""Score the pipeline against the human gold set.

  python scripts/38_evaluate_against_gold.py

The first accuracy figure in this project that is measured against labels the
pipeline had no hand in. Everything before it compared the pipeline to labels
produced by the same assistant that built it.

Two numbers, kept apart on purpose
----------------------------------
goldset_focused_sampling.json sets the rule: "Headline accuracy and macro-F1
are computed on Part A only. Part B is a deliberately enriched sample of
contested cases and is reported separately." Part B oversamples rows where the
methods disagreed, so scoring on it would understate accuracy on ordinary
text -- and quietly mixing the two would produce a figure that means nothing.

What is being scored
--------------------
Aspect EXTRACTION: for each aspect, did the pipeline tag this piece as being
about that aspect, and did the human? Polarity is reported alongside but is
not part of the headline, because the gold set records a verdict only where
the human judged the aspect present.

What the number rests on
------------------------
Two independent human passes over the same 200 segments, the second labelled
blind -- its sheet carried no answers and no sample_reason. Cohen's kappa on
aspect presence, with bootstrap 95% intervals (reports/agreement.json):

    cleanliness    0.941  [0.875, 0.986]   almost perfect
    safety         0.756  [0.621, 0.872]   substantial
    facilities     0.737  [0.619, 0.838]   substantial
    roads_access   0.718  [0.594, 0.826]   lower bound just under 0.60

This is a measured-reliable gold set, which the earlier version of this file
could not claim. Three of four aspects support a "substantial agreement" claim
on the LOWER bound, which is the bound a claim should rest on; roads_access
misses it by 0.006 and should be reported that way rather than rounded into
significance.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from travellens import config as C  # noqa: E402

ASPECTS = ["roads_access", "cleanliness", "facilities", "safety"]
REPORT = C.REPORTS / "gold_evaluation.json"


def prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def score(gold, seg, aspects):
    """Per-aspect precision/recall/F1 for aspect extraction."""
    out = {}
    for a in aspects:
        col = "asp_" + a
        ucol = "uAsp_" + a
        tp = fp = fn = tn = 0
        for r in gold.to_dict("records"):
            sid = str(r["segment_id"])
            if sid not in seg:
                continue
            row = seg[sid]
            # The union tagger is what the tree is built from where present.
            pred = bool(row.get(ucol, row.get(col, False)))
            # pandas reads an empty cell as NaN, and str(nan) is "nan"
            # -- truthy. That made every row count as a human positive,
            # so precision came out 1.000 for every aspect.
            cell = r.get(a)
            human = bool(cell is not None and not pd.isna(cell)
                         and str(cell).strip())
            if pred and human:
                tp += 1
            elif pred and not human:
                fp += 1
            elif human and not pred:
                fn += 1
            else:
                tn += 1
        p, rc, f = prf(tp, fp, fn)
        out[a] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                  "precision": p, "recall": rc, "f1": f,
                  "human_positives": tp + fn}
    fs = [v["f1"] for v in out.values() if v["human_positives"]]
    return out, round(sum(fs) / len(fs), 3) if fs else None


def main():
    print("\nLostinSriLanka -- pipeline vs the human gold set\n" + "=" * 62)

    gold = pd.read_csv(C.REPORTS / "goldset_focused_annotator1.csv")
    checked = gold["checked"].astype(str).str.strip().str.lower() == "x"
    gold = gold[checked]
    if not len(gold):
        sys.exit("the gold set has no checked rows yet")

    u = pd.read_csv(C.DATA_PROCESSED / "segments_tagged_union.csv",
                    low_memory=False)
    seg = {str(r["segment_id"]): r for r in u.to_dict("records")}
    aspects = [a for a in ASPECTS if a in gold.columns]

    part_a = gold[gold["sample_reason"].astype(str).str.startswith("representative")]
    part_b = gold[gold["sample_reason"].astype(str).str.startswith("disagreement")]

    print("  rows labelled : {}".format(len(gold)))
    print("  Part A        : {}  representative -- the headline number".format(
        len(part_a)))
    print("  Part B        : {}  contested cases -- reported separately".format(
        len(part_b)))

    results = {}
    for name, subset in (("part_a_headline", part_a),
                         ("part_b_contested", part_b),
                         ("all_rows", gold)):
        per, macro = score(subset, seg, aspects)
        results[name] = {"n_rows": len(subset), "macro_f1": macro,
                         "per_aspect": per}

    for name, title in (("part_a_headline", "PART A -- headline accuracy"),
                        ("part_b_contested", "PART B -- contested cases only")):
        r = results[name]
        print("\n  {}  (n={})".format(title, r["n_rows"]))
        print("  {:<16} {:>6} {:>7} {:>6}   {}".format(
            "aspect", "prec", "recall", "F1", "human says present"))
        print("  " + "-" * 58)
        for a in aspects:
            v = r["per_aspect"][a]
            print("  {:<16} {:>6} {:>7} {:>6}   {}".format(
                a, v["precision"], v["recall"], v["f1"], v["human_positives"]))
        print("  {:<16} {:>21}".format("macro F1", r["macro_f1"]))

    C.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(str(REPORT), "w", encoding="utf-8") as fh:
        json.dump({
            "what_this_is": (
                "The first accuracy measured against labels the pipeline had "
                "no hand in. Headline is Part A only, per the sampling rule; "
                "Part B oversamples contested rows and is reported apart."),
            "caveat": (
                "Two independent human passes, the second labelled blind. "
                "Cohen's kappa on aspect presence: cleanliness 0.941, safety "
                "0.756, facilities 0.737, roads_access 0.718; bootstrap 95% "
                "intervals in reports/agreement.json. Three of four support a "
                "substantial-agreement claim on the lower bound; roads_access "
                "misses 0.60 by 0.006. Measured against two readers who agree "
                "at that level -- not against ground truth, which does not "
                "exist for a judgement task."),
            "results": results,
        }, fh, indent=1, ensure_ascii=False)
    print("\n  wrote {}".format(REPORT))
    print("\n  Compare with README's self-labelled figures. A large drop means")
    print("  the old numbers were flattering the pipeline.")


if __name__ == "__main__":
    main()
