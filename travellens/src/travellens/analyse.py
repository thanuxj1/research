"""Analyse ONE review, end to end.

This is the whole pipeline applied to a single piece of text, which is what a
portal needs: text in, categories out. Every stage the corpus goes through is
the same stage used here, so what this prints is what the dashboard counts.

    review -> repair punctuation -> split into opinion units
           -> tag each unit with the aspects it is about
           -> classify each unit as complaint / praise / neutral

Two things it deliberately does NOT do
--------------------------------------
It does not pretend to certainty. Every aspect carries a measured F1 from the
gold set, and a verdict on a weak aspect is reported as low confidence rather
than dressed up as a fact. Abstention is a feature: a system that says
"unclear" on the ambiguous 15% is more useful, and far more defensible, than
one that guesses and is quietly wrong.

It uses the deployed scoring by default. The lexicon path is instant and needs
no download, but it is measurably weaker on exactly the cases a portal will
meet: "a monkey snatched my bag" and "foreigners are charged ten times what
locals pay" both came out NEUTRAL under the lexicon and COMPLAINT under the
transformer. Defaulting to the fast path would have shipped a portal that
quietly under-reports complaints, so speed is now the opt-in
(use_transformer=False) rather than the default.

Run with:  python scripts/40_analyse.py "your review text here"
"""
from __future__ import annotations

from typing import Dict, List, Optional

from . import config as C
from .aspects import matched_terms, tag_segment
from .polarity import lexicon_polarity
from .segment import repair_punctuation, split_into_segments, MIN_SEGMENT_WORDS

# Measured aspect-extraction F1, READ from the evaluation report rather than
# written here. Hardcoding them was a live bug: after the lexicon fixes every
# figure in this block moved, and a stale F1 does not just mislabel a caption
# -- it drives the confidence flag, so a verdict would have been presented as
# low-confidence when it had become reliable, or worse, the other way round.
#
# reports/accuracy_all_aspects.json carries provenance per aspect, and its
# `aspects` block now holds only what a human actually labelled -- four of the
# seven. It used to quote F1 for scenery, price_value and crowd as well, from
# labels that exist nowhere in this repository, and price_value 0.875 and crowd
# 0.833 were clearing the floor below and flagging those verdicts "high
# confidence". They are in the report's `unmeasured` block instead, which is
# read here as no figure at all, so confidence() answers "unmeasured" for them.
# See src/travellens/accuracy.py; regenerate with scripts/44_accuracy_report.py.
def _load_measured():
    import json
    try:
        with open(str(C.REPORTS / "accuracy_all_aspects.json"), encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return {}, {}
    f1s, readers = {}, {}
    for key, v in (raw.get("aspects") or {}).items():
        if v.get("f1") is None:
            continue
        f1s[key] = v.get("f1")
        readers[key] = v.get("human_readers") or (2 if v.get("cohens_kappa") else 1)
    return f1s, readers


MEASURED_F1, MEASURED_READERS = _load_measured()

CONFIDENCE_FLOOR = 0.70

LABEL_NAMES = {"N": "complaint", "P": "praise", "X": "neutral / factual"}


def confidence(aspect: str) -> str:
    """high / low / unmeasured, from the measured F1 for this aspect."""
    f1 = MEASURED_F1.get(aspect)
    if f1 is None:
        return "unmeasured"
    return "high" if f1 >= CONFIDENCE_FLOOR else "low"


def readers(aspect: str):
    """How many independent humans stand behind this aspect's figure.

    One reader means an accuracy number with no reliability behind it. That is
    weaker evidence than the same number from two, and the difference belongs
    in front of anyone reading a verdict.
    """
    return MEASURED_READERS.get(aspect)


def analyse(review: str, use_transformer: bool = True) -> Dict:
    """Break a review into opinion units and categorise each one."""
    text = repair_punctuation(review or "")
    # Same MIN_SEGMENT_WORDS filter api.py applies. Without it, the second
    # half of a contrast split -- "though.", "but." -- survived here as its
    # own opinion unit even though the deployed API silently drops it. Two
    # engines meant to be identical were segmenting the same review
    # differently; this is the fix on this side of that gap.
    units = [u for u in split_into_segments(text)
            if len(u.split()) >= MIN_SEGMENT_WORDS]

    model_labels: List[str] = []
    if use_transformer and units:
        from .polarity import TransformerPolarity
        preds = TransformerPolarity().predict(units, verbose=False)
        model_labels = [p["label"] for p in preds]

    results = []
    for i, unit in enumerate(units):
        aspects = tag_segment(unit)
        lex_label, lex_score = lexicon_polarity(unit)

        if model_labels:
            from .polarity import final_polarity
            label, corrected = final_polarity(
                unit, model_labels[i], lex_label, lex_score)
            method = "transformer + correction rules"
        else:
            label, corrected = lex_label, False
            method = "lexicon + negation"

        results.append({
            "unit": unit,
            "aspects": [
                {
                    "key": a,
                    "label": C.ASPECTS[a].label,
                    "why": matched_terms(unit, a),
                    "confidence": confidence(a),
                    "measured_f1": MEASURED_F1.get(a),
                    "human_readers": readers(a),
                }
                for a in aspects
            ],
            "polarity": label,
            "polarity_name": LABEL_NAMES.get(label, label),
            "corrected_by_rule": corrected,
            "method": method,
            # An unclassifiable unit is not a failure to report -- it is the
            # honest answer for text carrying no opinion about anything.
            "actionable": bool(aspects) and label in ("N", "P"),
        })

    # Roll up: which categories did this review actually land in?
    buckets: Dict[str, Dict] = {}
    for r in results:
        for a in r["aspects"]:
            b = buckets.setdefault(a["key"], {
                "label": a["label"], "confidence": a["confidence"],
                "complaint": 0, "praise": 0, "neutral": 0})
            b[{"N": "complaint", "P": "praise", "X": "neutral"}[r["polarity"]]] += 1

    return {
        "review": review,
        "n_units": len(units),
        "units": results,
        "categories": buckets,
        "unmatched_units": sum(1 for r in results if not r["aspects"]),
    }


def format_report(res: Dict) -> str:
    """Human-readable rendering -- the shape a portal response would take."""
    out = []
    out.append(f"{res['n_units']} opinion unit(s) found\n")
    for i, r in enumerate(res["units"], 1):
        out.append(f'{i}. "{r["unit"]}"')
        if not r["aspects"]:
            out.append("     -> no category matched (not about any tracked topic)")
        else:
            for a in r["aspects"]:
                f1 = a["measured_f1"]
                rd = a.get("human_readers")
                acc = (f"F1 {f1}, {rd} reader{'s' if rd == 2 else ''}"
                       if f1 is not None else "never measured")
                # "low" and "unmeasured" are different claims: one says the
                # extractor was tested and scored badly, the other says nobody
                # has tested it. Three of the seven aspects are in the second
                # state, so collapsing them into one flag would report an
                # absence of evidence as evidence of weakness.
                flag = {"high": "",
                        "low": "   [LOW CONFIDENCE]"}.get(
                            a["confidence"], "   [NOT MEASURED]")
                out.append(f'     -> {a["label"]}: {r["polarity_name"]}'
                           f'   ({acc}){flag}')
                if a["why"]:
                    out.append(f'        matched: {", ".join(a["why"][:4])}')
        if r["corrected_by_rule"]:
            out.append("        (polarity changed by a correction rule)")
        out.append("")

    out.append("SUMMARY -- categories this review lands in:")
    if not res["categories"]:
        out.append("   none")
    for key, b in sorted(res["categories"].items()):
        bits = [f'{n} {k}' for k, n in
                (("complaint", b["complaint"]), ("praise", b["praise"]),
                 ("neutral", b["neutral"])) if n]
        flag = {"high": "",
                "low": "   [treat as provisional]"}.get(
                    b["confidence"], "   [no accuracy figure exists]")
        out.append(f'   {b["label"]:<18} {", ".join(bits)}{flag}')
    if res["unmatched_units"]:
        out.append(f'\n   {res["unmatched_units"]} unit(s) matched no category.')
    return "\n".join(out)
