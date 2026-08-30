"""Assemble the published aspect-extraction accuracy report.

What this is for
----------------
``reports/accuracy_all_aspects.json`` is the file the rest of the project reads
to decide how much weight an aspect's verdict can carry: ``analyse.confidence``
turns its F1 into the ``[LOW CONFIDENCE]`` flag a reader sees next to a verdict.
It was written by hand, and it drifted from the evaluations it claimed to
summarise in two different ways.

The small drift: cleanliness quoted precision 0.818 / F1 0.885 while
``reports/gold_evaluation.json`` -- the reproducible output of
``scripts/38_evaluate_against_gold.py`` -- said 0.844 / 0.900. A stale figure,
harmless here only by luck, since both sit the same side of the confidence
floor.

The serious drift: scenery, price_value and crowd carried full
precision/recall/F1 rows -- scenery P=0.750 R=0.655 on "55 human positives",
price_value P=1.000, crowd P=1.000 -- against human labels that do not exist
anywhere in this repository. Every aspect column in
``goldset_annotator{1,2}.csv`` is empty (600 and 150 rows, zero labels), and
``LABEL_THESE_price_crowd.csv`` and ``LABEL_THESE_price_crowd_scenery.csv`` are
blank templates. The only human labels in the project are the four aspects of
the focused gold set. Those three rows were not reproducible from anything a
reader could run, and two of them were driving a "high confidence" flag.

Why this module refuses to be helpful
-------------------------------------
The same failure mode ``agreement.py`` was written against applies here: a
number with no labels behind it is indistinguishable, on the page, from one
with two annotators behind it. So the guard is in code rather than in a
caveat. An aspect earns a row only when a label file that *declares human
provenance* actually carries labels for it. Everything else is listed under
``unmeasured`` with the reason and what would fix it -- present in the report,
absent from the figures.

Run with:  python scripts/44_accuracy_report.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pandas as pd

from . import config as C
from .agreement import MachineLabelsRefused, _provenance

# Label files a figure may rest on. Named rather than globbed so that adding a
# new source of truth is a deliberate edit; LABEL_THESE_* sheets are swept in
# too, so that filling one in is enough to make its aspect appear here.
LABEL_FILES = [
    "goldset_focused_annotator1.csv",
    "goldset_focused_annotator2.csv",
    "goldset_annotator1.csv",
    "goldset_annotator2.csv",
]
LABEL_GLOBS = ["LABEL_THESE_*.csv"]

# Anything below this is a figure the pipeline should not be trusted on. Kept
# in step with analyse.CONFIDENCE_FLOOR, which reads what this module writes.
CONFIDENCE_FLOOR = 0.70


class UnlabelledAspectRefused(RuntimeError):
    """Raised when a scored aspect has no human labels standing behind it."""


def _read_json(name: str) -> Dict:
    path = C.REPORTS / name
    if not path.exists():
        raise FileNotFoundError(
            "{} does not exist.\n"
            "Run scripts/38_evaluate_against_gold.py and "
            "scripts/39_agreement.py first -- this module summarises them, it "
            "does not measure anything itself.".format(path))
    with open(str(path), encoding="utf-8") as fh:
        return json.load(fh)


def _column_aliases() -> Dict[str, str]:
    """Column headings that name an aspect, in either sheet's vocabulary.

    The gold sets use the internal key (``price_value``); the LABEL_THESE
    workbooks use the display label ("Price & value"). Matched
    case-insensitively so a sheet is not silently ignored over a capital
    letter.
    """
    out: Dict[str, str] = {}
    for key, spec in C.ASPECTS.items():
        out[key.lower()] = key
        out[spec.label.lower()] = key
    return out


def _candidate_files() -> List[Path]:
    seen, out = set(), []
    for name in LABEL_FILES:
        path = C.REPORTS / name
        if path.exists():
            out.append(path)
            seen.add(path.name)
    for pattern in LABEL_GLOBS:
        for path in sorted(C.REPORTS.glob(pattern)):
            if path.name not in seen:
                out.append(path)
                seen.add(path.name)
    return out


def human_labelled_aspects() -> Dict:
    """Which aspects a human has actually labelled, and in which files.

    A file counts only if it passes the same provenance check
    ``agreement.py`` applies. A blank template has no ``labelled_by`` column,
    so it is skipped for that reason before its emptiness is ever considered --
    which is the right order: an unmarked sheet is refused whether or not
    somebody has typed into it.
    """
    alias = _column_aliases()
    labelled: Dict[str, Dict] = {}
    skipped: List[Dict] = []
    scanned = _candidate_files()

    for path in scanned:
        try:
            df = pd.read_csv(path)
        except (OSError, ValueError) as exc:
            skipped.append({"file": path.name,
                            "reason": "unreadable: {}".format(exc)})
            continue
        try:
            _provenance(df, path)
        except MachineLabelsRefused as exc:
            skipped.append({"file": path.name,
                            "reason": str(exc).splitlines()[0].strip()})
            continue

        aspects_here = []

        # WIDE sheets: one column per aspect, the shape the gold set uses.
        for col in df.columns:
            key = alias.get(str(col).strip().lower())
            if key is None:
                continue
            n = int(df[col].notna().sum())
            if n == 0:
                continue
            rec = labelled.setdefault(key, {"n_labels": 0, "files": [],
                                            "independent_passes": []})
            rec["n_labels"] += n
            rec["files"].append({"file": path.name, "n_labels": n})
            # A wide gold-set file is one independent reader's pass over the
            # whole sample. Counting FILES instead of passes was briefly wrong
            # here: adding the polarity and presence sheets took the gold
            # aspects to "4 readers" when two people had read them.
            rec["independent_passes"].append(path.name)
            aspects_here.append(key)

        # LONG sheets: an `aspect` column naming the topic and one answer
        # column. The polarity and presence sheets are this shape, and they
        # are human labels for the aspects they name -- a detector that only
        # understood the gold set's layout would report those aspects as
        # unlabelled while their figures were being published.
        if "aspect" in df.columns:
            answer = next((c for c in ("verdict", "is_about", "label")
                           if c in df.columns), None)
            if answer:
                marked = df[df[answer].notna()
                            & (df[answer].astype(str).str.strip() != "")]
                for key, g in marked.groupby("aspect"):
                    key = str(key).strip()
                    if key not in C.ASPECTS:
                        continue
                    rec = labelled.setdefault(key, {"n_labels": 0, "files": [],
                                                    "independent_passes": []})
                    rec["n_labels"] += int(len(g))
                    rec["files"].append({"file": path.name,
                                         "n_labels": int(len(g))})
                    # Deliberately NOT an independent pass. The polarity and
                    # presence sheets were read by the same person, and two
                    # sheets from one reader are not two readers.
                    aspects_here.append(key)
        if not aspects_here:
            skipped.append({"file": path.name,
                            "reason": "declares human provenance but carries "
                                      "no labels in any aspect column"})

    return {"labelled": labelled, "skipped": skipped,
            "files_scanned": [p.name for p in scanned]}


PRESENCE_SHEET = "LABEL_THESE_presence.csv"


def presence_precision() -> Dict:
    """Extraction PRECISION from the filled presence sheet, per aspect.

    Of the (segment, aspect) pairs the pipeline tags, how many a human says
    really are about that topic. This is the only accuracy figure that exists
    for scenery, price_value and crowd, because the focused gold set never
    covered them.

    Precision only, and the report says so. The sheet contains nothing but
    pairs the pipeline already tagged, so it cannot see a mention the pipeline
    missed -- recall needs a sample drawn from untagged segments, which is a
    different exercise. Reporting an F1 from this would be inventing the half
    that was never measured.

    Refused unless the file declares human provenance, by the same check
    agreement.py applies.
    """
    from .agreement import MachineLabelsRefused, _provenance

    path = C.REPORTS / PRESENCE_SHEET
    if not path.exists():
        return {"status": "no sheet yet",
                "how_to_make_one": "python scripts/48_presence_sheet.py",
                "per_aspect": {}}
    df = pd.read_csv(path)
    filled = df[df["is_about"].notna()
                & (df["is_about"].astype(str).str.strip() != "")]
    if not len(filled):
        return {"status": "sheet exists but is blank",
                "rows_waiting": int(len(df)), "per_aspect": {}}
    try:
        _provenance(filled, path)
    except MachineLabelsRefused as exc:
        return {"status": "refused",
                "reason": str(exc).splitlines()[0].strip(), "per_aspect": {}}

    filled = filled.copy()
    filled["yes"] = (filled["is_about"].astype(str).str.strip().str.lower()
                     .str[0] == "y")
    per = {}
    for aspect, g in filled.groupby("aspect"):
        if aspect not in C.ASPECTS:
            continue
        n = int(len(g))
        hits = int(g["yes"].sum())
        per[aspect] = {
            "n_pairs_judged": n,
            "n_really_about_it": hits,
            "precision": round(hits / n, 3) if n else None,
            "ci95": _proportion_ci(hits, n),
            "readers": 1,
        }
    return {"status": "in use", "rows_scored": int(len(filled)),
            "per_aspect": per}


def _proportion_ci(hits: int, n: int):
    """Percentile bootstrap interval for a proportion."""
    if n < 2:
        return [None, None]
    import numpy as np
    arr = np.array([1] * hits + [0] * (n - hits), dtype=float)
    rng = np.random.default_rng(20260830)
    draws = arr[rng.integers(0, n, (5000, n))].mean(axis=1)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return [round(float(lo), 3), round(float(hi), 3)]


def build(strict: bool = True) -> Dict:
    """Assemble the report from the two evaluations that produced its numbers."""
    gold = _read_json("gold_evaluation.json")
    agree = _read_json("agreement.json")
    scan = human_labelled_aspects()
    labelled = scan["labelled"]
    presence_sheet = presence_precision()

    part_a = ((gold.get("results") or {}).get("part_a_headline") or {})
    scored = part_a.get("per_aspect") or {}
    n_rows = part_a.get("n_rows")
    kappa_by_aspect = agree.get("presence") or {}

    # The guard. A scored aspect with no labels behind it is the exact defect
    # this module exists to make impossible, so it stops the run rather than
    # quietly dropping the row.
    if strict:
        orphans = sorted(k for k in scored if k not in labelled)
        if orphans:
            raise UnlabelledAspectRefused(
                "gold_evaluation.json scores {} but no human label file "
                "carries those aspects.\n"
                "Files scanned: {}.\n"
                "Either the labels are missing or the evaluation is reading "
                "something it should not. Not summarised either way.".format(
                    orphans, ", ".join(scan["files_scanned"])))

    measured: Dict[str, Dict] = {}
    unmeasured: Dict[str, Dict] = {}

    for key, spec in C.ASPECTS.items():
        row = scored.get(key)
        human = labelled.get(key)

        pres = presence_sheet["per_aspect"].get(key)
        # Gold evaluation wins where it exists; the presence sheet covers what
        # it never reached. Keyed on whether the aspect was SCORED, not on
        # whether any file mentions it -- the long sheets mention all seven,
        # so a `not human` test silently stopped firing once they existed.
        if not row and pres:
            # Not in the gold set, but the presence sheet covers it. This is a
            # real measurement and belongs in `aspects`, with its own shape:
            # precision from one reader, no recall, no F1, no kappa. The
            # fields are named for what they are so nothing downstream can
            # mistake it for the two-reader F1 the gold set produces.
            measured[key] = {
                "label": spec.label,
                "precision": pres["precision"],
                "recall": None,
                "f1": None,
                "human_positives": pres["n_really_about_it"],
                "n_pairs_judged": pres["n_pairs_judged"],
                "precision_ci95": pres["ci95"],
                "confidence": ("high" if (pres["precision"] or 0.0) >= CONFIDENCE_FLOOR
                               else "low"),
                "measured_on": "presence sheet, {} pipeline-tagged pairs, "
                               "1 human pass".format(pres["n_pairs_judged"]),
                "human_readers": 1,
                "cohens_kappa": None,
                "kappa_95ci": None,
                "reliability": "single reader -- extraction PRECISION only. "
                               "The sample holds only pairs the pipeline "
                               "already tagged, so recall is not measured and "
                               "no F1 is reported.",
            }
            continue

        if not human:
            unmeasured[key] = {
                "label": spec.label,
                "reason": "no human labels exist for this aspect in any file "
                          "declaring human provenance",
                "what_would_fix_it":
                    "label an aspect column for it -- the blank sheets are "
                    "reports/LABEL_THESE_price_crowd_scenery.csv and "
                    "reports/LABEL_THESE_price_crowd.csv -- add a "
                    "'labelled_by' column reading 'human', then re-run "
                    "scripts/38_evaluate_against_gold.py and this script",
            }
            continue
        if not row:
            unmeasured[key] = {
                "label": spec.label,
                "n_human_labels": human["n_labels"],
                "reason": "labelled by a human but not scored in "
                          "reports/gold_evaluation.json",
                "what_would_fix_it": "run scripts/38_evaluate_against_gold.py",
            }
            continue

        kap = kappa_by_aspect.get(key) or {}
        n_readers = len(human.get("independent_passes") or human["files"])
        ci = ([kap.get("lo"), kap.get("hi")]
              if kap.get("lo") is not None else None)
        if kap.get("kappa") is not None and n_readers >= 2:
            reliability = ("{} independent human readers, Cohen's kappa "
                           "{}".format(n_readers, kap["kappa"]))
        else:
            reliability = ("single reader -- no agreement figure exists for "
                           "this aspect")

        measured[key] = {
            "label": spec.label,
            "precision": row.get("precision"),
            "recall": row.get("recall"),
            "f1": row.get("f1"),
            "human_positives": row.get("human_positives"),
            "confidence": ("high" if (row.get("f1") or 0.0) >= CONFIDENCE_FLOOR
                           else "low"),
            "measured_on": ("focused gold set, Part A (n={}), {} independent "
                            "human pass{}".format(
                                n_rows, n_readers,
                                "es" if n_readers != 1 else "")),
            "human_readers": n_readers,
            "label_files": human["files"],
            "cohens_kappa": kap.get("kappa"),
            "kappa_95ci": ci,
            "reliability": reliability,
        }

    n_m, n_u = len(measured), len(unmeasured)
    return {
        "what_this_is":
            "Aspect-extraction accuracy, assembled from "
            "reports/gold_evaluation.json (accuracy) and "
            "reports/agreement.json (reliability). Generated by "
            "scripts/44_accuracy_report.py -- do not hand-edit. A hand-written "
            "version of this file published figures for three aspects that had "
            "no labels behind them.",
        "generated_from": ["reports/gold_evaluation.json",
                           "reports/agreement.json",
                           "reports/LABEL_THESE_presence.csv"],
        "presence_sheet": {k: v for k, v in presence_sheet.items()
                           if k != "per_aspect"},
        "aspects": measured,
        "unmeasured": unmeasured,
        "label_files_scanned": scan["files_scanned"],
        "label_files_not_counted": scan["skipped"],
        "honest_summary":
            "{} of {} aspects are measured against human labels ({}). {} are "
            "not ({}): no human has labelled them, so this project has no "
            "accuracy figure for them and none is quoted here. Report those "
            "descriptively -- as mention counts -- or not at all.".format(
                n_m, n_m + n_u, ", ".join(sorted(measured)),
                n_u, ", ".join(sorted(unmeasured))),
    }


def _cell(v):
    """Render a figure, or a dash where there genuinely is none.

    An aspect measured only by the presence sheet has precision and nothing
    else: no recall, no F1, no kappa. Those columns are empty rather than zero,
    and must print that way.
    """
    return "-" if v is None else v


def format_table(report: Dict) -> str:
    out = []
    out.append("{:<14} {:>6} {:>6} {:>6} {:>5} {:>7}  readers".format(
        "aspect", "prec", "rec", "F1", "pos", "kappa"))
    out.append("-" * 62)
    for key, r in sorted(report["aspects"].items()):
        out.append("{:<14} {:>6} {:>6} {:>6} {:>5} {:>7}  {}".format(
            key, _cell(r["precision"]), _cell(r["recall"]), _cell(r["f1"]),
            _cell(r["human_positives"]), _cell(r["cohens_kappa"]),
            r["human_readers"]))
    if report["unmeasured"]:
        out.append("")
        out.append("NOT MEASURED -- no figure exists and none is published:")
        for key, r in sorted(report["unmeasured"].items()):
            out.append("   {:<14} {}".format(key, r["reason"]))
    return "\n".join(out)


def main() -> None:
    print("\nLostinSriLanka -- aspect-extraction accuracy report\n" + "=" * 62)
    try:
        report = build()
    except (UnlabelledAspectRefused, FileNotFoundError) as exc:
        print("\nREFUSED\n-------")
        print(exc)
        raise SystemExit(1)

    print()
    print(format_table(report))

    dest = C.REPORTS / "accuracy_all_aspects.json"
    with open(str(dest), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print("\nwrote {}".format(dest))


if __name__ == "__main__":
    main()
