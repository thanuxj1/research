"""Split-half reliability of the published complaint rates.

The question this answers
-------------------------
Every other check in this project validates a *component*: the gold set says
whether a sentence was tagged correctly, `external_validity.py` says whether
the rates move with an independent measure. None of them validates the number
the dashboard actually prints -- "Kandy Lake, Cleanliness, 46.8%, n=47" --
because there is no ground truth for it. Nobody has ever counted the true
cleanliness complaint rate at Kandy Lake. It is an estimate of an opinion, and
no authority holds the right answer to compare against.

So the number cannot be validated by comparison. It can be validated by
**reproducibility**, which is the standard move when a quantity has no external
criterion: if the rate measures something real about the place, then an
independent sample of opinions about the same place must produce roughly the
same rate. If it is noise, the two samples disagree.

That is what this module does. For every destination-aspect cell it splits the
opinions in half at random, computes the rate on each half separately, and asks
how well the two halves agree across all cells. The corpus comparison in
`reports/corpus_comparison.json` is the same argument made once, between Google
and TripAdvisor, at whole-corpus level; this is the same argument made per cell,
hundreds of times, at the level the dashboard actually publishes.

What comes out, and why each piece is there
-------------------------------------------
**Spearman-Brown.** A half carries half the evidence, so split-half agreement
understates the reliability of the full-length measure -- and the full-length
measure is what gets published. The Spearman-Brown prophecy formula corrects
for that: `r_full = 2r / (1 + r)`. Quoting the raw half-to-half correlation
would report a number nothing in this project actually uses.

**Averaged over many splits.** One random split is itself a coin toss. Every
figure here is the average over `N_SPLITS` different splits, combined through
Fisher's z rather than by averaging correlations directly, because correlations
are not additive.

**Binned by n.** This is the point of the exercise. The median
destination-aspect cell in this corpus holds about 20 opinions, and the
dashboard currently suppresses below 5 and flags "low confidence" below 15 --
two thresholds that were chosen rather than measured. Reliability by bin
replaces them with a number: below some n the two halves stop agreeing, and
that is where a rate should stop being shown as a rate.

**A permutation null, and what it caught.** A reliability figure means nothing
without knowing what the method returns when there is nothing to find, so the
whole study is re-run with verdicts shuffled between cells inside each aspect.
That destroys every real place-to-rate association while leaving cell sizes and
each aspect's overall complaint rate untouched.

The first run of this null came back at **0.53**, not zero -- and finding that
is the reason the headline figure is what it is. Pooling cells across aspects
lets the aspect base rates do the work: scenery cells sit near 9% and safety
cells near 70%, so two halves of any cell agree merely by belonging to the same
aspect. The published figures are therefore computed **within aspect**, by
removing each aspect's mean rate from both halves before correlating. The null
collapses once that is done, which is what licenses the number.

Run with:  python scripts/46_reliability.py
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import config as C

N_SPLITS = 200
SEED = 20260830

# Lower edges. A cell lands in the last bin whose edge it reaches.
BINS = [2, 10, 15, 20, 30, 50, 100]

# Conventional reliability floors. Named here rather than buried in a
# comparison so that the thresholds this study recommends are traceable to a
# stated standard instead of to the number that happened to look good.
ACCEPTABLE = 0.70
GOOD = 0.80


def cells_from_long(long: pd.DataFrame, pol_col: str) -> Dict:
    """Per destination-aspect cell, the opinion verdicts as 1 (complaint) / 0.

    X is dropped, exactly as `aggregate._aspect_stats` drops it: a factual
    statement is not an opinion and is not in the denominator of any published
    rate. Measuring reliability over a different denominator than the dashboard
    publishes would answer a question nobody asked.
    """
    df = long[long[pol_col].isin(["N", "P"])]
    cells = {}
    for (district, dest, aspect), g in df.groupby(["district", "destination",
                                                   "aspect"], sort=True):
        v = (g[pol_col].to_numpy() == "N").astype(np.int8)
        if len(v) >= BINS[0]:
            cells[(district, dest, aspect)] = v
    return cells


def _fisher_mean(rs: List[float]) -> Optional[float]:
    """Average correlations through Fisher's z. They do not average directly."""
    vals = [r for r in rs if r is not None and np.isfinite(r) and abs(r) < 1.0]
    if not vals:
        return None
    z = np.arctanh(np.asarray(vals, dtype=float))
    return float(np.tanh(z.mean()))


def spearman_brown(r: Optional[float]) -> Optional[float]:
    """Reliability of the full-length measure, from its split-half correlation."""
    if r is None or r <= -1.0:
        return None
    return float(2.0 * r / (1.0 + r))


def _spearman(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    """Rank correlation, computed here so scipy is not a hard dependency."""
    if len(a) < 3:
        return None
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _pearson(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _one_split(cells: Dict, rng, keys: List) -> Dict:
    """One random half-split. Returns the two rate vectors and the sizes."""
    ra, rb, ns, asp = [], [], [], []
    for k in keys:
        v = cells[k]
        idx = rng.permutation(len(v))
        half = len(v) // 2
        a, b = v[idx[:half]], v[idx[half:half * 2]]
        if len(a) == 0 or len(b) == 0:
            continue
        ra.append(a.mean())
        rb.append(b.mean())
        ns.append(len(v))
        asp.append(k[2])
    return {"a": np.asarray(ra), "b": np.asarray(rb), "n": np.asarray(ns),
            "aspect": np.asarray(asp)}


def _bin_of(n: int) -> str:
    edge = BINS[0]
    for b in BINS:
        if n >= b:
            edge = b
    i = BINS.index(edge)
    return ("{}+".format(edge) if i == len(BINS) - 1
            else "{}-{}".format(edge, BINS[i + 1] - 1))


def _centre_within_aspect(a: np.ndarray, b: np.ndarray,
                          aspect: np.ndarray):
    """Remove each aspect's mean rate from both halves.

    Without this the pooled correlation is mostly an artefact. Scenery cells
    sit near 9% and safety cells near 70%, so both halves of every cell agree
    simply by belonging to the same aspect -- and the permutation null proves
    it: shuffling verdicts *within* each aspect, which destroys every real
    place-to-rate association, still returned a corrected reliability of 0.53
    on the uncentred figure. That 0.53 is the aspect base rates showing
    through, not evidence about any destination.

    Centring asks the question that was meant: given that this is a cleanliness
    cell, do two halves of THIS PLACE agree on where it sits relative to other
    cleanliness cells? The null collapses to zero once it is applied, which is
    what makes the centred figure the reportable one.
    """
    a, b = a.astype(float).copy(), b.astype(float).copy()
    keep = np.zeros(len(a), dtype=bool)
    for asp in np.unique(aspect):
        m = aspect == asp
        # An aspect contributing a single cell to this subset is DROPPED, not
        # left uncentred. Its mean cannot be estimated from one observation,
        # and leaving it raw puts one point at its aspect base rate -- say 0.70
        # for safety -- among centred points sitting near zero, where it acts
        # as a leverage outlier and manufactures correlation on its own. The
        # permutation null caught exactly this: it read 0.82 in the 100+ bin
        # while every other bin was flat.
        if m.sum() < 2:
            continue
        a[m] -= a[m].mean()
        b[m] -= b[m].mean()
        keep |= m
    return a[keep], b[keep]


def _summarise(splits: List[Dict], mask_fn=None, centre: bool = True) -> Dict:
    """Fisher-averaged agreement across splits, for the cells mask_fn selects."""
    pear, spear, mads = [], [], []
    n_cells = 0
    for s in splits:
        m = np.ones(len(s["a"]), dtype=bool) if mask_fn is None else mask_fn(s["n"])
        if m.sum() < 3:
            continue
        a, b = s["a"][m], s["b"][m]
        n_cells = int(m.sum())
        # The gap in percentage points is reported on the RAW rates: it is
        # meant to be read in the units on the dashboard, and a centred rate
        # is not a rate anyone sees.
        mads.append(float(np.abs(a - b).mean()))
        if centre:
            a, b = _centre_within_aspect(a, b, s["aspect"][m])
        pear.append(_pearson(a, b))
        spear.append(_spearman(a, b))
    r = _fisher_mean(pear)
    return {
        "n_cells": n_cells,
        "half_to_half_r": None if r is None else round(r, 3),
        "spearman_brown": (None if spearman_brown(r) is None
                           else round(spearman_brown(r), 3)),
        "rank_correlation": (None if _fisher_mean(spear) is None
                             else round(_fisher_mean(spear), 3)),
        "mean_abs_diff_pp": (None if not mads
                             else round(100.0 * float(np.mean(mads)), 1)),
    }


def run(long: pd.DataFrame, pol_col: str, n_splits: int = N_SPLITS,
        seed: int = SEED, shuffle: bool = False) -> Dict:
    """The whole study. `shuffle=True` runs the permutation null instead."""
    if shuffle:
        long = long.copy()
        rng = np.random.default_rng(seed + 1)
        # Shuffle verdicts WITHIN each aspect. That destroys the association
        # between a place and its rate -- the thing being tested -- while
        # leaving each aspect's overall complaint rate, and every cell size,
        # exactly as they were. A null that also changed those would be a
        # different dataset, not a control.
        for aspect, idx in long.groupby("aspect").groups.items():
            vals = long.loc[idx, pol_col].to_numpy()
            long.loc[idx, pol_col] = rng.permutation(vals)

    cells = cells_from_long(long, pol_col)
    keys = sorted(cells)
    rng = np.random.default_rng(seed)
    splits = [_one_split(cells, rng, keys) for _ in range(n_splits)]

    overall = _summarise(splits)

    by_bin = {}
    for i, edge in enumerate(BINS):
        hi = BINS[i + 1] if i + 1 < len(BINS) else None
        label = "{}+".format(edge) if hi is None else "{}-{}".format(edge, hi - 1)
        by_bin[label] = _summarise(
            splits,
            (lambda lo, hi_: (lambda n: (n >= lo) if hi_ is None
                              else ((n >= lo) & (n < hi_))))(edge, hi))

    # From n upward, rather than inside a band: an authority reading a rate
    # wants to know whether everything at or above this size is trustworthy,
    # not whether one narrow band happens to be.
    cumulative = {}
    for edge in BINS:
        cumulative["n>={}".format(edge)] = _summarise(
            splits, (lambda lo: (lambda n: n >= lo))(edge))

    by_aspect, by_aspect_at_10 = {}, {}
    for aspect in C.ASPECTS:
        akeys = [k for k in keys if k[2] == aspect]
        if len(akeys) < 3:
            continue
        arng = np.random.default_rng(seed)
        asplits = [_one_split(cells, arng, akeys) for _ in range(n_splits)]
        by_aspect[aspect] = _summarise(asplits)
        # The same aspect restricted to cells that clear the measured floor.
        # Pooling in the 2-9 cells, which this study shows are noise, tells you
        # about the small cells rather than about the aspect.
        at10 = _summarise(asplits, lambda n: n >= 10)
        if at10["n_cells"] >= 3:
            by_aspect_at_10[aspect] = at10

    return {
        "n_cells": len(cells),
        "n_splits": n_splits,
        "overall": overall,
        "by_cell_size": by_bin,
        "cumulative_from": cumulative,
        "by_aspect": by_aspect,
        "by_aspect_cells_n10_plus": by_aspect_at_10,
    }


def recommend_threshold(cumulative: Dict, floor: float = ACCEPTABLE):
    """The smallest n at which the full-length measure clears `floor`."""
    for key in sorted(cumulative, key=lambda k: int(k.split(">=")[1])):
        sb = cumulative[key]["spearman_brown"]
        if sb is not None and sb >= floor:
            return int(key.split(">=")[1]), sb
    return None, None


def build(n_splits: int = N_SPLITS, seed: int = SEED) -> Dict:
    from .aggregate import DEFAULT_POLARITY_COL, long_table

    seg = pd.read_csv(C.DATA_PROCESSED / "segments_scored.csv")
    long = long_table(seg, verbose=False)
    pol_col = DEFAULT_POLARITY_COL

    observed = run(long, pol_col, n_splits=n_splits, seed=seed)
    null = run(long, pol_col, n_splits=max(20, n_splits // 4), seed=seed,
               shuffle=True)

    ok_n, ok_sb = recommend_threshold(observed["cumulative_from"], ACCEPTABLE)
    good_n, good_sb = recommend_threshold(observed["cumulative_from"], GOOD)

    return {
        "what_this_is":
            "Split-half reliability of the published destination-aspect "
            "complaint rates. There is no ground truth for a complaint rate, "
            "so it is validated by reproducibility instead of by comparison: "
            "if the rate measures something real about a place, an independent "
            "half of the opinions about that place reproduces it.",
        "reliability_depends_on_spread":
            "A correlation can only detect variation that exists. Scenery has "
            "the SMALLEST half-to-half gap of any aspect -- its two halves land "
            "6.4 percentage points apart, against 22-25 for cleanliness and "
            "safety -- yet it scores the lowest reliability, because every "
            "scenery cell sits near the same low rate and there is almost no "
            "between-place variation left to reproduce. Read the gap and the "
            "correlation together: a low correlation with a small gap means "
            "the aspect does not discriminate between places, not that the "
            "estimate is imprecise.",
        "how_to_read_it":
            "spearman_brown is the reliability of the FULL-length published "
            "rate, corrected from the half-to-half correlation. 0.70 is the "
            "conventional floor for a group-level measure, 0.80 for a "
            "confident one. mean_abs_diff_pp is how far apart the two halves "
            "land, in percentage points, which is the same figure in the units "
            "a reader sees on the dashboard.",
        "observed": observed,
        "permutation_null": {
            "what_this_is":
                "The identical study with verdicts shuffled between cells "
                "inside each aspect. Cell sizes and each aspect's overall "
                "complaint rate are unchanged; only the link between a place "
                "and its rate is destroyed. Any reliability surviving here is "
                "an artefact of the method rather than a property of the data.",
            "overall": null["overall"],
            "by_cell_size": null["by_cell_size"],
        },
        "thresholds": {
            "current_dashboard": {
                "suppress_below": C.MIN_MENTIONS_DISPLAY,
                "low_confidence_below": C.MIN_MENTIONS_CONFIDENT,
                "note": "Both were chosen, not measured. This study is what "
                        "measures them.",
            },
            "acceptable_at_or_above": ok_n,
            "acceptable_reliability": ok_sb,
            "good_at_or_above": good_n,
            "good_reliability": good_sb,
        },
    }


def format_report(rep: Dict) -> str:
    out = []
    o = rep["observed"]
    out.append("cells: {}   random splits per figure: {}".format(
        o["n_cells"], o["n_splits"]))
    out.append("")
    out.append("{:<12} {:>6} {:>9} {:>10} {:>9}".format(
        "cell size", "cells", "half-half", "corrected", "gap pp"))
    out.append("-" * 50)
    for label, s in o["by_cell_size"].items():
        out.append("{:<12} {:>6} {:>9} {:>10} {:>9}".format(
            label, s["n_cells"],
            "-" if s["half_to_half_r"] is None else s["half_to_half_r"],
            "-" if s["spearman_brown"] is None else s["spearman_brown"],
            "-" if s["mean_abs_diff_pp"] is None else s["mean_abs_diff_pp"]))

    out.append("")
    out.append("from n upward:")
    for label, s in o["cumulative_from"].items():
        out.append("   {:<8} cells {:>5}   corrected reliability {}".format(
            label, s["n_cells"],
            "-" if s["spearman_brown"] is None else s["spearman_brown"]))

    out.append("")
    out.append("by aspect, cells with n>=10 only:")
    for aspect, s in sorted(o["by_aspect_cells_n10_plus"].items(),
                            key=lambda kv: -(kv[1]["spearman_brown"] or -1)):
        out.append("   {:<14} cells {:>4}   corrected {}   gap {} pp".format(
            aspect, s["n_cells"],
            "-" if s["spearman_brown"] is None else s["spearman_brown"],
            "-" if s["mean_abs_diff_pp"] is None else s["mean_abs_diff_pp"]))

    n = rep["permutation_null"]["overall"]
    out.append("")
    out.append("permutation null (verdicts shuffled between cells):")
    out.append("   corrected reliability {}   gap {} pp".format(
        n["spearman_brown"], n["mean_abs_diff_pp"]))

    t = rep["thresholds"]
    out.append("")
    out.append("thresholds")
    out.append("   dashboard today : suppress below {}, low-confidence below {}"
               " (both chosen, not measured)".format(
                   t["current_dashboard"]["suppress_below"],
                   t["current_dashboard"]["low_confidence_below"]))
    out.append("   measured        : acceptable (>={}) from n>={}".format(
        ACCEPTABLE, t["acceptable_at_or_above"]))
    out.append("                     good (>={}) from n>={}".format(
        GOOD, t["good_at_or_above"]))
    return "\n".join(out)


def main() -> None:
    print("\nLostinSriLanka -- split-half reliability\n" + "=" * 60)
    rep = build()
    print()
    print(format_report(rep))
    dest = C.REPORTS / "reliability.json"
    with open(str(dest), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, ensure_ascii=False)
    print("\nwrote {}".format(dest))


if __name__ == "__main__":
    main()
