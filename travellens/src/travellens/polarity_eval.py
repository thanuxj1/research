"""Per-aspect POLARITY accuracy against the human gold set.

Why this exists separately from gold_check / 38
-----------------------------------------------
`38_evaluate_against_gold.py` scores aspect EXTRACTION: did the pipeline find
the same aspects a human found? That is the number the project has usually
quoted. It says nothing about whether a correctly-found aspect got the right
verdict -- and the verdict is what every complaint rate on the dashboard is
made of. This scores the verdict.

What is scored
--------------
Conditional accuracy: only (segment, aspect) pairs where the human judged the
aspect PRESENT and recorded a verdict, and where the pipeline also found the
aspect. A missed aspect is an extraction failure and is 38's business; mixing
the two produces a number that answers neither question. The prediction is
built exactly as `aggregate.py` builds it -- `pol_final` from the corpus, then
`polarity.aspect_polarity()` -- so this measures the deployed system rather
than a reconstruction of it.

Three things this reports that a single accuracy figure cannot
--------------------------------------------------------------
**Intervals.** Part A carries 11 to 33 pairs per aspect. A point estimate on
33 rows moves several points when one row changes, and quoting it bare invites
a reader to treat 0.636 as if it were known to three digits. Every figure here
carries a percentile bootstrap interval, and claims should rest on the lower
bound -- the same rule `agreement.py` applies to kappa.

**Both readers.** Two people labelled these 200 segments independently, and
both recorded verdicts, not just presence. The project has only ever scored
against annotator 1. Scoring against annotator 2 as well is a second,
independent measurement of the same system that costs no new labelling, and
an accuracy that survives both readers is a different claim from one that
holds against a single reader.

**The ceiling.** Two humans reading the same sentence do not always agree
either: on these pairs they agree 83% to 98% of the time depending on the
aspect. A system cannot meaningfully be asked to exceed the rate at which the
people defining the task agree with each other, so the honest question is not
"is accuracy 0.64" but "how far is 0.64 from the ceiling for that aspect". A
figure reported without its ceiling reads as a failure against 100%, which is
not the standard anyone could meet.

Reported separately, `unanimous_pairs` scores only the pairs where BOTH readers
gave the same verdict -- the unambiguous cases. Accuracy there is the fairest
single number for the system, because a pair the humans themselves split on has
no defensible right answer to be scored against.

Part A / Part B
---------------
Reported apart, per `goldset_focused_sampling.json`. Part A is the
representative sample and is the headline; Part B oversamples contested rows,
so it means something different.

Run with:  python scripts/43_evaluate_polarity.py
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from . import config as C
from .aspects import tag_segment
from .polarity import aspect_polarity

# The four the focused gold set covers. The supplementary sheet
# (scripts/47_polarity_sheet.py) can carry all seven, so anything reading a
# frame derives its aspects from the frame rather than from this list.
GOLD_ASPECTS = ["roads_access", "cleanliness", "facilities", "safety"]
ASPECTS = GOLD_ASPECTS
LABELS = {"N": "complaint", "P": "praise", "X": "neutral"}

SUPPLEMENTARY_SHEET = "LABEL_THESE_polarity.csv"


def _aspects_in(df: pd.DataFrame) -> List[str]:
    """Aspects present in this frame, in the canonical config order."""
    have = set(df["aspect"]) if len(df) else set()
    return [a for a in C.ASPECTS if a in have]


BOOTSTRAP = 5000
SEED = 20260830


def _bootstrap_ci(correct: Sequence[int], n_boot: int = BOOTSTRAP,
                  seed: int = SEED) -> Dict:
    """Percentile interval for a proportion.

    Resampled rather than taken from a normal approximation: a proportion is
    bounded at 0 and 1, and with 11 pairs a symmetric interval runs off the
    end of the scale.
    """
    arr = np.asarray(correct, dtype=float)
    n = len(arr)
    if n == 0:
        return {"accuracy": None, "lo": None, "hi": None, "n": 0}
    point = float(arr.mean())
    if n < 2:
        return {"accuracy": round(point, 3), "lo": None, "hi": None, "n": n}
    rng = np.random.default_rng(seed)
    draws = arr[rng.integers(0, n, (n_boot, n))].mean(axis=1)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"accuracy": round(point, 3), "lo": round(float(lo), 3),
            "hi": round(float(hi), 3), "n": n}


def _verdict(cell) -> Optional[str]:
    if cell is None or (isinstance(cell, float) and np.isnan(cell)):
        return None
    v = str(cell).strip().upper()[:1]
    return v if v in LABELS else None


def load_pairs() -> Dict:
    """Every (segment, aspect) both the pipeline and a human have a verdict for.

    Returns one row per pair with the pipeline's verdict, annotator 1's and --
    where that reader also judged the aspect present -- annotator 2's.
    """
    a1 = pd.read_csv(C.REPORTS / "goldset_focused_annotator1.csv")
    a1 = a1[a1["checked"].astype(str).str.strip().str.lower() == "x"]
    if not len(a1):
        raise SystemExit("the gold set has no checked rows yet")

    a2_path = C.REPORTS / "goldset_focused_annotator2.csv"
    a2 = pd.read_csv(a2_path) if a2_path.exists() else None
    a2_by_id = ({str(r["segment_id"]): r for r in a2.to_dict("records")}
                if a2 is not None else {})

    scored = pd.read_csv(
        C.DATA_PROCESSED / "segments_scored.csv",
        usecols=["segment_id", "segment", "pol_final", "pol_lexicon"],
    ).drop_duplicates("segment_id").set_index("segment_id")

    rows, missed = [], 0
    for r in a1.to_dict("records"):
        sid = str(r["segment_id"])
        if sid not in scored.index:
            continue
        s = scored.loc[sid]
        if pd.isna(s["pol_final"]):
            continue
        text = str(s["segment"])
        found = tag_segment(text)
        # `part` is the column the sampler writes; sample_reason is the older
        # way of recovering it and is kept as a fallback so an earlier gold
        # file still evaluates.
        part = str(r.get("part") or "").strip().upper()
        if part not in ("A", "B"):
            part = ("A" if str(r.get("sample_reason", "")).startswith("representative")
                    else "B")
        other = a2_by_id.get(sid)

        for a in ASPECTS:
            human1 = _verdict(r.get(a))
            if human1 is None:
                continue                       # reader 1: aspect not present
            if a not in found:
                missed += 1                    # extraction miss, 38's business
                continue
            pred, _, _ = aspect_polarity(text, a, s["pol_final"], s["pol_lexicon"])
            rows.append({
                "segment_id": sid, "part": part, "aspect": a,
                "human1": human1,
                "human2": _verdict(other.get(a)) if other is not None else None,
                "pred": pred,
            })
    supp, supp_note = load_supplementary(scored)
    pairs = pd.DataFrame(rows)
    if len(supp):
        pairs = pd.concat([pairs, supp], ignore_index=True)
    return {"pairs": pairs, "extraction_misses": missed,
            "supplementary": supp_note}


def load_supplementary(scored: pd.DataFrame):
    """Pairs from the sheet scripts/47_polarity_sheet.py writes, once filled.

    Refused unless it declares human provenance, by the same check
    agreement.py applies -- an unmarked labels file is exactly how a machine
    pass becomes an accuracy figure. An unfilled sheet is not an error: it is
    the normal state until somebody sits down with it, so this returns an
    empty frame and says so.
    """
    from .agreement import MachineLabelsRefused, _provenance

    path = C.REPORTS / SUPPLEMENTARY_SHEET
    empty = pd.DataFrame(columns=["segment_id", "part", "aspect", "human1",
                                  "human2", "pred"])
    if not path.exists():
        return empty, {"status": "no sheet yet",
                       "how_to_make_one": "python scripts/47_polarity_sheet.py"}

    df = pd.read_csv(path)
    filled = df[df["verdict"].notna() & (df["verdict"].astype(str).str.strip() != "")]
    if not len(filled):
        return empty, {"status": "sheet exists but is blank",
                       "rows_waiting": int(len(df)),
                       "next": "fill the verdict column, then re-run this script"}
    try:
        _provenance(filled, path)
    except MachineLabelsRefused as exc:
        return empty, {"status": "refused",
                       "reason": str(exc).splitlines()[0].strip()}

    rows = []
    for r in filled.to_dict("records"):
        sid = str(r["segment_id"])
        aspect = str(r["aspect"])
        human = _verdict(r.get("verdict"))
        if human is None or sid not in scored.index or aspect not in C.ASPECTS:
            continue
        srow = scored.loc[sid]
        if pd.isna(srow["pol_final"]):
            continue
        text = str(srow["segment"])
        if aspect not in tag_segment(text):
            continue                     # no longer tagged: not a polarity call
        pred, _, _ = aspect_polarity(text, aspect, srow["pol_final"],
                                     srow["pol_lexicon"])
        rows.append({"segment_id": sid, "part": "S", "aspect": aspect,
                     "human1": human, "human2": None, "pred": pred})
    out = pd.DataFrame(rows) if rows else empty
    out = _attach_presence(out)
    return out, {"status": "in use", "rows_scored": int(len(out)),
                 "aspects": sorted(set(out["aspect"])) if len(out) else []}


def _attach_presence(pairs: pd.DataFrame) -> pd.DataFrame:
    """Mark each pair with whether a human says the tag belongs at all.

    The two sheets cover the same 420 pairs and ask different questions --
    "is this about that topic?" and "complaint, praise or fact?" -- so joining
    them yields the figure neither can produce alone: polarity accuracy on the
    pairs that are genuinely about the topic.

    That matters because the two errors compound. A verdict scored on a
    wrongly-tagged sentence is being marked against a question the reader was
    forced to answer, and the published complaint rate carries both mistakes at
    once. Separating them says which one to fix.
    """
    from .accuracy import PRESENCE_SHEET

    pairs = pairs.copy()
    pairs["is_about"] = None
    path = C.REPORTS / PRESENCE_SHEET
    if not path.exists() or not len(pairs):
        return pairs
    try:
        pres = pd.read_csv(path)
    except (OSError, ValueError):
        return pairs
    if "is_about" not in pres.columns:
        return pairs
    # Same provenance rule as everywhere else: an unmarked or machine sheet
    # contributes nothing.
    from .agreement import MachineLabelsRefused, _provenance
    marked = pres[pres["is_about"].notna()
                  & (pres["is_about"].astype(str).str.strip() != "")]
    if not len(marked):
        return pairs
    try:
        _provenance(marked, path)
    except MachineLabelsRefused:
        return pairs

    lookup = {}
    for r in marked.to_dict("records"):
        v = str(r["is_about"]).strip().lower()[:1]
        if v in ("y", "n"):
            lookup[(str(r["segment_id"]), str(r["aspect"]))] = (v == "y")
    pairs["is_about"] = [
        lookup.get((str(sid), str(asp)))
        for sid, asp in zip(pairs["segment_id"], pairs["aspect"])]
    return pairs


def _aspects_in_report(entry: Dict) -> List[str]:
    have = set(entry["vs_annotator1"]["per_aspect"])
    return [a for a in C.ASPECTS if a in have]


def _score(df: pd.DataFrame, human_col: str) -> Dict:
    """Per-aspect accuracy with intervals, plus the confusion counts."""
    out = {}
    d0 = df[df[human_col].notna()]
    for a in _aspects_in(d0):
        d = d0[d0["aspect"] == a]
        if not len(d):
            continue
        correct = (d[human_col] == d["pred"]).astype(int).tolist()
        ci = _bootstrap_ci(correct)
        confusion = {}
        for h, p in zip(d[human_col], d["pred"]):
            k = "{}->{}".format(h, p)
            confusion[k] = confusion.get(k, 0) + 1
        out[a] = {
            "n": ci["n"], "accuracy": ci["accuracy"],
            "ci95": [ci["lo"], ci["hi"]],
            "confusion_human_to_system": dict(sorted(
                confusion.items(), key=lambda kv: -kv[1])),
        }
    accs = [v["accuracy"] for v in out.values() if v["accuracy"] is not None]
    macro = round(sum(accs) / len(accs), 3) if accs else None

    # Interval on the pooled figure too. The macro average of four small
    # aspects has an interval of its own, and omitting it makes the headline
    # look firmer than any of the numbers behind it.
    pooled = _bootstrap_ci((d0[human_col] == d0["pred"]).astype(int).tolist())
    return {"per_aspect": out, "macro_accuracy": macro,
            "pooled_accuracy": pooled["accuracy"],
            "pooled_ci95": [pooled["lo"], pooled["hi"]],
            "n_pairs": int(len(d0))}


def human_ceiling(df: pd.DataFrame) -> Dict:
    """How often the two readers agree, on the pairs both judged present.

    This is the standard the system should be read against. Reporting accuracy
    against an implicit 100% asks the pipeline to beat the people who defined
    the task.
    """
    out = {}
    both = df[df["human1"].notna() & df["human2"].notna()]
    for a in _aspects_in(both):
        d = both[both["aspect"] == a]
        if not len(d):
            continue
        ci = _bootstrap_ci((d["human1"] == d["human2"]).astype(int).tolist())
        out[a] = {"n_pairs_both_judged_present": ci["n"],
                  "human_agreement": ci["accuracy"],
                  "ci95": [ci["lo"], ci["hi"]]}
    vals = [v["human_agreement"] for v in out.values()]
    return {"per_aspect": out,
            "macro": round(sum(vals) / len(vals), 3) if vals else None}


def _gap_to_ceiling(scored: Dict, ceiling: Dict) -> Dict:
    """System accuracy as a share of what two humans manage on the same pairs."""
    out = {}
    for a, v in scored["per_aspect"].items():
        c = ceiling["per_aspect"].get(a)
        if not c or not c["human_agreement"]:
            continue
        out[a] = {
            "system": v["accuracy"],
            "human_ceiling": c["human_agreement"],
            "gap": round(c["human_agreement"] - v["accuracy"], 3),
            "share_of_ceiling": round(v["accuracy"] / c["human_agreement"], 3),
        }
    return out


def build() -> Dict:
    loaded = load_pairs()
    df = loaded["pairs"]
    ceiling = human_ceiling(df)

    results = {}
    for key, subset in (
        ("part_a_headline", df[df["part"] == "A"]),
        ("part_b_contested", df[df["part"] == "B"]),
        # The supplementary sheet is a fresh uniform sample drawn per aspect,
        # so it is reported on its own rather than pooled into Part A -- mixing
        # two sampling frames produces a figure neither of them supports.
        ("supplementary_sample", df[df["part"] == "S"]),
        # The cleanest conditional figure in the project: pairs a human says
        # really are about the topic, so the verdict is the only thing being
        # scored. Everything else mixes an extraction error into a polarity
        # number.
        ("supplementary_correctly_tagged",
         df[(df["part"] == "S") & (df.get("is_about") == True)]),  # noqa: E712
        ("all_rows", df),
    ):
        if not len(subset):
            continue
        unanimous = subset[subset["human1"].notna()
                           & (subset["human1"] == subset["human2"])]
        entry = {
            "n_pairs": int(len(subset)),
            "vs_annotator1": _score(subset, "human1"),
            "vs_annotator2": _score(subset, "human2"),
            "unanimous_pairs": _score(unanimous, "human1"),
        }
        entry["gap_to_human_ceiling"] = _gap_to_ceiling(
            entry["vs_annotator1"], ceiling)
        results[key] = entry

    return {
        "what_this_is":
            "Conditional polarity accuracy of the deployed pipeline "
            "(pol_final + polarity.aspect_polarity) against human labels, "
            "computed from the corpus and the gold file so it reproduces. "
            "Scored only where a human recorded a verdict AND the extractor "
            "found the aspect.",
        "why_it_is_not_the_same_as_gold_evaluation_json":
            "38_evaluate_against_gold.py scores whether the right ASPECT was "
            "found. This scores whether a correctly-found aspect got the right "
            "VERDICT, which is what the complaint rates are made of.",
        "scope":
            "Four aspects only. scenery, price_value and crowd have no human "
            "labels in this repository, so no polarity accuracy can be "
            "reported for them and none should be quoted.",
        "how_to_read_it":
            "Claims rest on the LOWER bound of ci95, not the point estimate: "
            "11 to 33 pairs per aspect means one row moves an aspect several "
            "points. Read every accuracy against human_ceiling for the same "
            "aspect -- two people reading these sentences agree 83-98% of the "
            "time, so 100% is not the standard. unanimous_pairs is the fairest "
            "single figure: a pair the two readers themselves split on has no "
            "defensible right answer to score against.",
        "supplementary_sheet": loaded.get("supplementary"),
        "comparing_the_two_samples":
            "The focused gold set and the supplementary sheet are drawn from "
            "the same tagging frame -- both are rule-lexicon tagged, and all "
            "420 supplementary pairs pass the same rule gate the gold pairs "
            "do -- so the two are directly comparable. What differs is sample "
            "size and, more importantly, WHO READ THEM. roads_access scores "
            "0.421 against annotator 1 (n=19), 0.571 against annotator 2 "
            "(n=19) and 0.800 against the supplementary reader (n=60): three "
            "readers, three answers, on the same task. The spread between "
            "readers is larger than the spread between any two methods this "
            "project has compared, which is the single most important thing "
            "to carry into a write-up of these numbers.",
        "two_errors_separated":
            "supplementary_sample scores the verdict on every pair the "
            "pipeline tags -- which is the population the published complaint "
            "rates are computed over, and therefore the right figure for "
            "'how accurate is what we count'. It carries two mistakes at once: "
            "a wrong tag and a wrong verdict. supplementary_correctly_tagged "
            "removes the first by keeping only pairs a human says really are "
            "about the topic, so the verdict is the only thing being scored. "
            "Read them together: the gap between the two is the cost of "
            "extraction error, and the second figure is the ceiling the "
            "polarity model would reach if extraction were perfect.",
        "supplementary_limitation":
            "ONE reader, so there is no agreement figure and no ceiling for "
            "the three aspects it alone covers -- scenery, price_value and "
            "crowd. That reader is also the system's author, which is the "
            "same class of limitation as open problem #1. It is mitigated but "
            "not removed by the sheet being blind: the system's verdict was "
            "not shown, so the labelling could not be anchored on the answer "
            "being tested. A second reader over a subset would close it, the "
            "way the focused gold set was closed.",
        "extraction_misses":
            loaded["extraction_misses"],
        "extraction_misses_note":
            "Pairs a human judged present that the extractor did not find. "
            "Not scored here -- that is aspect extraction, measured by "
            "reports/gold_evaluation.json.",
        "human_ceiling": ceiling,
        "results": results,
    }


def _cell(v):
    """Render a figure, or a dash where there is nothing to show.

    The supplementary sample has no second reader and no human ceiling -- one
    person labelled it -- so those columns are genuinely empty rather than
    zero, and must print as empty.
    """
    return "-" if v is None else v


def format_report(rep: Dict) -> str:
    out = []
    for key, title in (("part_a_headline", "PART A -- representative (headline)"),
                       ("part_b_contested", "PART B -- contested cases"),
                       ("supplementary_sample",
                        "SUPPLEMENTARY SHEET -- uniform sample, all aspects"),
                       ("supplementary_correctly_tagged",
                        "SUPPLEMENTARY -- pairs a human says ARE about the topic"),
                       ("all_rows", "ALL ROWS")):
        e = rep["results"].get(key)
        if not e:
            continue
        out.append("")
        out.append("  {}  (pairs: {})".format(title, e["n_pairs"]))
        out.append("  {:<15} {:>4} {:>9} {:>15} {:>9} {:>9}".format(
            "aspect", "n", "vs A1", "95% CI", "vs A2", "ceiling"))
        out.append("  " + "-" * 68)
        for a in _aspects_in_report(e):
            v = e["vs_annotator1"]["per_aspect"].get(a)
            if not v:
                continue
            v2 = e["vs_annotator2"]["per_aspect"].get(a) or {}
            c = rep["human_ceiling"]["per_aspect"].get(a) or {}
            out.append("  {:<15} {:>4} {:>9} {:>15} {:>9} {:>9}".format(
                a, v["n"], _cell(v["accuracy"]),
                "[{}, {}]".format(*v["ci95"]),
                _cell(v2.get("accuracy")), _cell(c.get("human_agreement"))))
        out.append("  {:<15} {:>4} {:>9} {:>15} {:>9} {:>9}".format(
            "macro", "", _cell(e["vs_annotator1"]["macro_accuracy"]), "",
            _cell(e["vs_annotator2"]["macro_accuracy"]),
            _cell(rep["human_ceiling"]["macro"] if key != "supplementary_sample"
                  else None)))
        u = e["unanimous_pairs"]
        if u["n_pairs"]:
            out.append("  {:<15} {:>4} {:>9} {:>15}".format(
                "unanimous only", u["n_pairs"], _cell(u["macro_accuracy"]),
                "[{}, {}]".format(*u["pooled_ci95"])))
    return "\n".join(out)


def main() -> None:
    print("\nLostinSriLanka -- polarity accuracy vs the human gold set\n" + "=" * 70)
    rep = build()
    print("  (segment, aspect) pairs available : {}".format(
        rep["results"]["all_rows"]["n_pairs"]))
    print("  extraction misses (scored by 38, not here) : {}".format(
        rep["extraction_misses"]))
    print(format_report(rep))

    dest = C.REPORTS / "polarity_accuracy.json"
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(str(dest), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, ensure_ascii=False)
    print("\n  wrote {}\n".format(dest))


if __name__ == "__main__":
    main()
