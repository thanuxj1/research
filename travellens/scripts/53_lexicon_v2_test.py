"""Would a larger lexicon fix the low recall? Tested, and it does not generalise.

  python scripts/53_lexicon_v2_test.py

Candidate additions (scripts/_lexicon_v2_candidates.py) were chosen from the topic
definitions and from misses on the 500-segment AI-annotated sample, then pruned by
a rule fixed in advance: no false positive on the human gold set (Part A) and a net
gain on the development half. They were then frozen and tested on a FRESH random
sample of 300 segments labelled afterwards (reports/ai_annotated/holdout_sample_claude.csv).

Result (2026-10): macro-F1 0.646 -> 0.651 on the fresh sample, with safety and price
slightly worse. The large gain seen on the sample the additions were chosen from
(0.66 -> 0.82) was fitting. The deployed lexicon is therefore unchanged.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import re  # noqa: E402

from travellens import aspects as AS  # noqa: E402
from _lexicon_v2_candidates import EXTRA  # noqa: E402

T = ["roads_access", "cleanliness", "facilities", "safety", "price_value", "crowd", "scenery"]
EXC = {t: [re.compile(p, re.I) for p in ps] for t, ps in EXTRA.items()}


def old(text):
    return set(AS.tag_segment(text or ""))


def new(text):
    s = old(text)
    for t, pats in EXC.items():
        if t not in s and any(p.search(text or "") for p in pats) and not AS._is_blocked(text or "", t):
            s.add(t)
    return s


def scores(rows, cols, tagger):
    out = {}
    for t in cols:
        tp = sum(1 for x, l in rows if t in tagger(x) and l[t]); fp = sum(1 for x, l in rows if t in tagger(x) and not l[t])
        fn = sum(1 for x, l in rows if t not in tagger(x) and l[t])
        p = tp / (tp + fp) if tp + fp else float("nan"); r = tp / (tp + fn) if tp + fn else float("nan")
        out[t] = 2 * p * r / (p + r) if p == p and r == r and p + r else float("nan")
    return out


def main():
    h = pd.read_csv(ROOT / "reports/ai_annotated/holdout_sample_claude.csv", dtype=str).fillna("")
    rows = [(r.segment, {t: bool(getattr(r, t)) for t in T}) for r in h.itertuples()]
    g = pd.read_csv(ROOT / "reports/goldset_focused_annotator1.csv", encoding="utf-8-sig", dtype=str).fillna("")
    g = g[g.part == "A_representative"]
    G4 = ["roads_access", "cleanliness", "facilities", "safety"]
    grows = [(r.segment, {t: getattr(r, t).strip().upper() in ("N", "P", "X") for t in G4}) for r in g.itertuples()]
    for name, rs, cols in (("fresh AI-annotated hold-out (n=300)", rows, T), ("human gold Part A (n=120)", grows, G4)):
        a, b = scores(rs, cols, old), scores(rs, cols, new)
        print("==", name)
        for t in cols:
            print("  %-13s F1 old %.3f  new %.3f" % (t, a[t], b[t]))
        ma = [v for v in a.values() if v == v]; mb = [v for v in b.values() if v == v]
        print("  macro F1 old %.3f -> new %.3f" % (sum(ma) / len(ma), sum(mb) / len(mb)))


if __name__ == "__main__":
    main()
