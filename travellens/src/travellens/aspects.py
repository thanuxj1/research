"""
TravelLens LK -- Stage 3: aspect tagging (rule-based baseline).

Assigns each opinion unit to zero, one, or many of the seven aspects defined in
config.ASPECTS, by matching the trigger words for each aspect.

STATUS: this is the BASELINE, not the final system.

It answers "what is this piece of text ABOUT?" reasonably well, because topic
words are reliable -- a sentence containing "toilet" really is about facilities.
It says nothing at all about whether the opinion is a complaint or praise. That
is Stage 5's job, and the reason it needs a real model is documented in
reports/aspect_tagging_report.json: keyword matching alone produces obvious
false positives that no amount of extra keywords can fix.

Run with:  python scripts/03_tag_aspects.py
"""
import json
import re
from typing import Dict, List

import pandas as pd

from . import config as C

# Compile every aspect pattern once. re.IGNORECASE because reviewers type in
# any casing; we kept original casing in Stage 1 for the transformer's benefit.
_COMPILED: Dict[str, "re.Pattern"] = {
    key: re.compile(aspect.pattern(), re.IGNORECASE)
    for key, aspect in C.ASPECTS.items()
}


def tag_segment(text: str) -> List[str]:
    """Return every aspect key whose trigger words appear in this text."""
    if not isinstance(text, str) or not text:
        return []
    return [key for key, rx in _COMPILED.items() if rx.search(text)]


def matched_terms(text: str, aspect_key: str) -> List[str]:
    """The actual words that caused a match -- used for error analysis and for
    showing the reader WHY a piece was filed under an aspect."""
    rx = _COMPILED[aspect_key]
    return sorted(set(m.group(0).lower() for m in rx.finditer(text or "")))


def tag_corpus(seg: pd.DataFrame, verbose: bool = True):
    """Add one boolean column per aspect to the segment table."""
    seg = seg.copy()
    usable = ~seg["too_short"]

    tags = seg["segment"].where(usable, "").map(tag_segment)
    for key in C.ASPECTS:
        seg["asp_" + key] = tags.map(lambda t, k=key: k in t)

    aspect_cols = ["asp_" + k for k in C.ASPECTS]
    seg["n_aspects"] = seg[aspect_cols].sum(axis=1)

    report = {
        "segments_total": int(len(seg)),
        "segments_usable": int(usable.sum()),
        "segments_with_aspect": int((seg["n_aspects"] > 0).sum()),
        "coverage_pct": round(100 * (seg["n_aspects"] > 0).sum() / max(int(usable.sum()), 1), 2),
        "multi_aspect_segments": int((seg["n_aspects"] > 1).sum()),
        "per_aspect": {},
    }
    for key, aspect in C.ASPECTS.items():
        col = "asp_" + key
        report["per_aspect"][key] = {
            "label": aspect.label,
            "segments": int(seg[col].sum()),
            "destinations": int(seg.loc[seg[col], "destination"].nunique()),
            "districts": int(seg.loc[seg[col], "district"].nunique()),
        }

    if verbose:
        print("  usable segments       : {}".format(report["segments_usable"]))
        print("  matched >= 1 aspect   : {} ({}%)".format(
            report["segments_with_aspect"], report["coverage_pct"]))
        print("  matched >= 2 aspects  : {}".format(report["multi_aspect_segments"]))
        print()
        print("  {:<22} {:>8} {:>7} {:>6}".format("aspect", "segments", "dests", "dists"))
        print("  " + "-" * 46)
        for key, info in sorted(report["per_aspect"].items(),
                                key=lambda kv: -kv[1]["segments"]):
            print("  {:<22} {:>8} {:>7} {:>6}".format(
                info["label"], info["segments"], info["destinations"], info["districts"]))
    return seg, report


def main():
    print("\nTravelLens LK -- Stage 3: aspect tagging\n" + "=" * 60)
    seg = pd.read_csv(C.DATA_PROCESSED / "segments.csv")
    seg, report = tag_corpus(seg)

    out_path = C.DATA_PROCESSED / "segments_tagged.csv"
    seg.to_csv(out_path, index=False, encoding="utf-8")
    with open(C.REPORTS / "aspect_tagging_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("\nwrote {}".format(out_path))
    print("wrote {}".format(C.REPORTS / "aspect_tagging_report.json"))


if __name__ == "__main__":
    main()
