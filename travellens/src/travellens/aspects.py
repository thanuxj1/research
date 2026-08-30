"""
LostinSriLanka -- Stage 3: aspect tagging (rule-based baseline).

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

# Gated triggers: (trigger, required context), both compiled once. A gated
# trigger marks the aspect present only when BOTH appear in the same segment --
# see Aspect.gated for why three safety words needed this.
_GATED: Dict[str, list] = {
    key: [(re.compile(t, re.IGNORECASE), re.compile(c, re.IGNORECASE))
          for t, c in getattr(aspect, "gated", [])]
    for key, aspect in C.ASPECTS.items()
}

# Vetoes: patterns that rule the aspect OUT no matter what matched. See
# Aspect.blocked -- gating is a condition, this is an override, and the two
# are needed for different failure shapes.
_BLOCKED: Dict[str, list] = {
    key: [re.compile(p, re.IGNORECASE) for p in getattr(aspect, "blocked", [])]
    for key, aspect in C.ASPECTS.items()
}


def _is_blocked(text: str, key: str) -> bool:
    return any(rx.search(text) for rx in _BLOCKED.get(key, []))


# Scenery attribution: the bare feature nouns, and the cues that show one is
# being looked at rather than merely mentioned. See config.SCENERY_BARE_NOUNS
# for the measurement that motivates this.
_SCENERY_BARE = [re.compile(p, re.IGNORECASE)
                 for p in getattr(C, "SCENERY_BARE_NOUNS", [])]
_SCENERY_CUE = (re.compile(C.SCENERY_CONTEXT_CUES, re.IGNORECASE)
                if getattr(C, "SCENERY_CONTEXT_CUES", None) else None)
# Everything in the scenery lexicon that is NOT a bare noun is itself a cue:
# "beautiful", "view", "picturesque" all say how the place looks.
_SCENERY_APPEARANCE = [
    re.compile(t, re.IGNORECASE) for t in C.ASPECTS["scenery"].triggers
    if t not in set(getattr(C, "SCENERY_BARE_NOUNS", []))
]


def _scenery_is_bare(text: str) -> bool:
    """True when scenery's only evidence is a feature noun with nothing in the
    segment saying the feature was seen, enjoyed or admired."""
    if any(rx.search(text) for rx in _SCENERY_APPEARANCE):
        return False
    if _SCENERY_CUE is not None and _SCENERY_CUE.search(text):
        return False
    return any(rx.search(text) for rx in _SCENERY_BARE)


def tag_segment(text: str) -> List[str]:
    """Return every aspect key whose trigger words appear in this text.

    An aspect is present if any plain trigger matches, OR if a gated trigger
    matches together with its required context -- and in neither case if a
    blocked pattern vetoes it.

    One cross-aspect rule runs last. Scenery names the features themselves
    (lake, waterfall, elephant), so the noun fires in sentences that are
    plainly about something else: "Animal cages should be more cleaned" was a
    scenery complaint, and so was "Bad smell in some areas close to lake".
    When scenery's only evidence is a bare noun AND the segment already
    carries another aspect, the mention is attributed to that other aspect
    alone. A segment that is only about the lake keeps its scenery tag, and
    "Beautiful lake but the road is bad" is untouched because "beautiful" is
    not a bare noun. See config.SCENERY_ATTRIBUTION_RULE.
    """
    if not isinstance(text, str) or not text:
        return []
    out = []
    for key, rx in _COMPILED.items():
        if _is_blocked(text, key):
            continue
        if rx.search(text):
            out.append(key)
            continue
        if any(t.search(text) and c.search(text) for t, c in _GATED.get(key, [])):
            out.append(key)

    if (getattr(C, "SCENERY_ATTRIBUTION_RULE", False)
            and "scenery" in out and len(out) > 1
            and _scenery_is_bare(text)):
        out = [k for k in out if k != "scenery"]
    return out


def matched_terms(text: str, aspect_key: str) -> List[str]:
    """The actual words that caused a match -- used for error analysis and for
    showing the reader WHY a piece was filed under an aspect."""
    text = text or ""
    # Must agree with tag_segment: explaining WHY a segment was filed under an
    # aspect that was in fact vetoed would be worse than saying nothing.
    if _is_blocked(text, aspect_key):
        return []
    rx = _COMPILED[aspect_key]
    found = set(m.group(0).lower() for m in rx.finditer(text))
    # A gated trigger only earns its place in the explanation alongside the
    # context that admitted it, so the reader can see WHY it counted.
    for t, c in _GATED.get(aspect_key, []):
        tm, cm = t.search(text), c.search(text)
        if tm and cm:
            found.add(tm.group(0).lower() + " + " + cm.group(0).lower())
    return sorted(found)


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
    print("\nLostinSriLanka -- Stage 3: aspect tagging\n" + "=" * 60)
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
