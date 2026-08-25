"""
TravelLens LK -- Stage 6: hierarchical aggregation.

Turns 27,000 scored opinion units into the drill-down tree:

    Sri Lanka -> District -> Destination -> Aspect -> evidence quotes

Two metrics are reported for every node, never one alone
-------------------------------------------------------
  n_negative      how BIG the problem is. Raw complaint count.
                  Popular places score high simply because more people wrote
                  about them, so this number must never be compared across
                  destinations on its own.

  complaint_rate  how BAD the problem is. n_negative / (n_negative + n_positive).
                  Comparable across destinations, but unstable when the
                  denominator is small -- which is what the evidence
                  thresholds below exist to control.

Evidence thresholds (config.MIN_MENTIONS_*)
-------------------------------------------
  < 5    node is SUPPRESSED entirely -- three complaints is an anecdote
  5-14   node is shown, flagged "low confidence"
  >= 15  node is shown normally

Suppression is a reported statistic, not a silent filter: the output records
how many nodes were hidden so the thesis can state the coverage honestly.

Run with:  python scripts/07_aggregate.py
"""
import json
from typing import Dict, List, Optional

import pandas as pd

from . import config as C

# Which polarity column drives the tree.
#
# pol_hybrid = the transformer with the documented domain correction applied
# (see polarity.py Method C: the base model inherits film-review semantics in
# which "calm", "quiet" and "uncrowded" are negative). pol_model and
# pol_lexicon are retained so the entire tree can be rebuilt with either and
# the three compared against the gold set in the results chapter.
DEFAULT_POLARITY_COL = "pol_final"

# How many example quotes to carry on each aspect node for the dashboard.
QUOTES_PER_NODE = 14


def _confidence(n_opinions: int) -> str:
    if n_opinions < C.MIN_MENTIONS_DISPLAY:
        return "suppressed"
    if n_opinions < C.MIN_MENTIONS_CONFIDENT:
        return "low"
    return "ok"


# --------------------------------------------------------------------------
# Recency weighting -- MEASURED, and the measurement says do almost nothing.
#
# The concern is legitimate: a road complained about in 2018 and repaired in
# 2022 would keep being reported as broken. An earlier version of this file
# applied decay weights of 1.0 / 0.7 / 0.4 / 0.2 by age band. Those numbers were
# invented. They had no justification, and a sensitivity test showed the choice
# is not harmless -- at a six-month half-life the destination ranking correlates
# only 0.674 with the undecayed one and individual rates move by up to 79 points.
#
# So the decay rate was derived from the data instead. For each destination,
# how well does an OLDER complaint rate predict the rate in the most recent
# twelve months? (Google corpus only; mixing corpora would confound time with
# audience.)
#
#     older window          n dests   Pearson r
#     12-24 months ago           57       0.587
#     24-36 months ago           76       0.574
#     36-48 months ago           94       0.641
#     48-60 months ago           75       0.609
#     60-84 months ago           31       0.649
#
# The correlation is FLAT out to seven years. A complaint rate from 2017
# predicts the 2024 rate as well as one from 2023 does. There is no measurable
# decay in informativeness, so weighting old reviews down would discard valid
# evidence to correct a problem this corpus cannot show happening.
#
# Interpretation: destination characteristics are persistent. A waterfall's
# access road is much the same across five years, and the ~0.6 ceiling looks
# like measurement noise rather than genuine change.
#
# DECISION: weights default to 1.0 -- no decay -- and the justification is the
# table above rather than intuition. The machinery is kept and configurable so
# the analysis can be re-run on a corpus with real temporal spread.
#
# What replaces decay: a per-destination TREND flag (below). The aggregate shows
# no systematic drift, but an individual road genuinely being repaired would be
# an outlier, invisible in a correlation and visible in a trend. That is the
# right instrument for the question.
RECENCY_WEIGHTS = {"0-1y": 1.0, "1-3y": 1.0, "3-5y": 1.0, "5y+": 1.0, "unknown": 1.0}


def _aspect_stats(group: pd.DataFrame, pol_col: str) -> Dict:
    """N / P / X counts and the headline metrics for one aspect at one node."""
    n_neg = int((group[pol_col] == "N").sum())
    n_pos = int((group[pol_col] == "P").sum())
    n_neu = int((group[pol_col] == "X").sum())
    opinions = n_neg + n_pos            # X excluded: a fact is not an opinion
    rate = round(n_neg / opinions, 3) if opinions else None

    # -- recency-weighted rate ------------------------------------------
    w_neg = w_pos = 0.0
    recent_neg = recent_pos = 0
    if "recency" in group.columns:
        for rec, pol in zip(group["recency"], group[pol_col]):
            w = RECENCY_WEIGHTS.get(rec, 0.5)
            if pol == "N":
                w_neg += w
                if rec in ("0-1y", "1-3y"):
                    recent_neg += 1
            elif pol == "P":
                w_pos += w
                if rec in ("0-1y", "1-3y"):
                    recent_pos += 1
    w_total = w_neg + w_pos
    weighted_rate = round(w_neg / w_total, 3) if w_total else None

    # -- timeline: the complaint rate in each age band ---------------------
    #
    # Published as raw counts per band rather than as a verdict. An earlier
    # version emitted an "improving / worsening / stable" label using a
    # 10-percentage-point threshold and a 10-opinion minimum. Both numbers were
    # invented, and a label hides the evidence behind a judgement the reader
    # cannot check.
    #
    # A timeline shows the same information without imposing either cutoff: the
    # reader sees the rate at each point AND how many opinions it rests on, so a
    # swing built on four reviews is visibly built on four reviews. No threshold
    # is needed because nothing is being decided on the reader's behalf.
    timeline = []
    if "recency" in group.columns:
        for band in ("5y+", "3-5y", "1-3y", "0-1y"):
            sub = group[group["recency"] == band]
            bn = int((sub[pol_col] == "N").sum())
            bp = int((sub[pol_col] == "P").sum())
            timeline.append({
                "band": band,
                "n_negative": bn,
                "n_positive": bp,
                "n_opinions": bn + bp,
                "rate": round(bn / (bn + bp), 3) if bn + bp else None,
            })
    trend = timeline if any(t["n_opinions"] for t in timeline) else None

    return {
        "n_negative": n_neg,
        "n_positive": n_pos,
        "n_neutral": n_neu,
        "n_opinions": opinions,
        "n_mentions": n_neg + n_pos + n_neu,
        "complaint_rate": rate,
        "weighted_rate": weighted_rate,
        "timeline": trend,
        "confidence": _confidence(opinions),
    }


def _quotes(group: pd.DataFrame, pol_col: str, limit: int = QUOTES_PER_NODE) -> List[Dict]:
    """Complaint quotes -- the evidence behind the number.

    Each quote carries the fields the reader needs in order to sort them
    themselves: which period it came from, how long it is, and how strongly the
    classifier read it as negative.

    On that last field: it is the MODEL'S CONFIDENCE, not a severity score.
    Nothing in this corpus states how serious a problem is, and inventing a
    severity scale would be exactly the kind of unjustified number this project
    has removed elsewhere. A confident "the road is terrible" and a hesitant
    "the road is a bit rough" differ in how clearly they were written, which is
    a reasonable thing to sort by, and is labelled as such in the interface.

    Selection is longest-first so the retained set is the most informative,
    then the reader re-sorts client-side.
    """
    neg = group[group[pol_col] == "N"].copy()
    if neg.empty:
        return []
    neg = neg.assign(_len=neg["segment"].astype(str).str.len())
    neg = neg.sort_values("_len", ascending=False).head(limit)

    conf_col = "pol_roberta_conf" if "pol_roberta_conf" in neg.columns else None
    out = []
    for r in neg.itertuples(index=False):
        conf = getattr(r, conf_col, None) if conf_col else None
        out.append({
            "text": r.segment,
            "review_id": r.review_id,
            "destination": r.destination,
            "band": getattr(r, "recency", None),
            "len": int(getattr(r, "_len", 0)),
            "conf": round(float(conf), 3) if conf is not None and pd.notna(conf) else None,
        })
    return out


def build_tree(seg: pd.DataFrame, pol_col: str = DEFAULT_POLARITY_COL,
               sources=None, reviews: Optional[pd.DataFrame] = None,
               use_trained: bool = False) -> Dict:
    """Build the full Sri Lanka -> district -> destination -> aspect tree.

    `sources` optionally restricts the tree to reviews from particular
    collection batches, e.g. sources=["apify_google_places"] rebuilds the whole
    dashboard from freshly scraped reviews only, with the training corpus
    excluded. This makes the strict train/inference separation demonstrable on
    demand rather than merely asserted.
    """
    n_col = "u_n_aspects" if "u_n_aspects" in seg.columns else "n_aspects"
    df = seg[(seg[n_col] > 0) & seg[pol_col].notna()].copy()

    if sources:
        if reviews is None:
            reviews = pd.read_csv(C.CLEAN_REVIEWS_CSV)
        keep = set(reviews.loc[reviews["source"].isin(sources), "review_id"])
        before = len(df)
        df = df[df["review_id"].isin(keep)]
        print("  source filter {}: {} -> {} segments".format(
            sources, before, len(df)))

    # One row per (segment, aspect) pair: a segment tagged with two aspects
    # must be counted once under each.
    # Aspect membership: prefer the UNION of the rule lexicon and the embedding
    # tagger when it is available, falling back to rules alone.
    #
    # The union raises tagged coverage from 57,621 to 73,291 segments (+27%) and
    # recovers cases the lexicon structurally cannot -- "sewage was running into
    # the stream" contains no word on the cleanliness list. Measured impact on
    # the published complaint RATES is under 2.5 percentage points for every
    # aspect and under 1 point for most, so the findings are stable under either
    # extractor. That stability is itself a reported robustness result.
    try:
        from .aspects_model import ASPECT_EXTRACTOR
    except ImportError:
        ASPECT_EXTRACTOR = {}
    have_union = ("uAsp_" + next(iter(C.ASPECTS))) in df.columns

    long_rows = []
    chosen = {}
    for key in C.ASPECTS:
        pick = ASPECT_EXTRACTOR.get(key, "rules")
        if pick == "safety_model" and ("sAsp_" + key) in df.columns:
            col = "sAsp_" + key
        elif pick == "trained" and ("tAsp_" + key) in df.columns:
            col = "tAsp_" + key
        elif pick == "union" and have_union:
            col = "uAsp_" + key
        else:
            pick, col = "rules", "asp_" + key
        chosen[key] = pick
        sub = df[df[col]].copy()
        sub["aspect"] = key
        long_rows.append(sub)
    print("  aspect extractor per aspect: {}".format(chosen))
    long = pd.concat(long_rows, ignore_index=True)

    # The locally trained model (Method F) is attached for comparison but is
    # NOT used to drive the tree.
    #
    # It was trained on star-derived weak labels, and measurement showed that
    # this makes it unsafe here: on 1,200 safety segments it re-labelled 257 of
    # 446 complaints (58%) as PRAISE, including "don't bath in beach because
    # it's dangerous" and "need to build a safety fence on sides of the walking
    # path".
    #
    # The cause is structural, not a tuning problem. A visitor who writes "be
    # careful, the rocks are slippery" very often still awards five stars --
    # they enjoyed the place AND warned other people. The star therefore labels
    # that warning POSITIVE, and the model learned exactly that. Weak
    # supervision inherits the review-level rating, so it cannot teach
    # aspect-level judgement, and it fails hardest on the aspect where a wrong
    # answer matters most.
    #
    # Deploying it would degrade the safety signal this project exists to
    # surface. Set use_trained=True only once the model has been retrained on
    # human aspect-level labels and measured against the gold set.
    trained_path = C.DATA_PROCESSED / "polarity_by_aspect.csv"
    if trained_path.exists():
        tr = pd.read_csv(trained_path)
        long = long.merge(tr, on=["segment_id", "aspect"], how="left")
        if use_trained:
            long[pol_col] = long["pol_trained"].fillna(long[pol_col])
            print("  WARNING: tree built from Method F (trained on weak labels)")
        else:
            print("  Method F attached for comparison only -- tree uses {}".format(
                pol_col))

    # Safety recall rule. Applied here rather than in polarity.py because it
    # depends on WHICH aspect a segment is being counted under -- the same
    # sentence keeps its ordinary verdict for every other aspect.
    from .polarity import safety_recall_rule
    if "pol_lexicon" in long.columns:
        recovered = 0
        labels = []
        for r in long.itertuples(index=False):
            lab = getattr(r, pol_col)
            new, fired = safety_recall_rule(
                getattr(r, "segment", ""), lab,
                getattr(r, "aspect", "") == "safety",
                getattr(r, "pol_lexicon", None))
            recovered += fired
            labels.append(new)
        long[pol_col] = labels
        if recovered:
            print("  safety recall rule: {} hedged warnings recovered".format(recovered))

    suppressed = {"destination_aspect": 0, "district_aspect": 0}

    # ---------------- destination level ----------------
    destinations = {}
    for (district, dest), dgroup in long.groupby(["district", "destination"]):
        aspects = {}
        for aspect, agroup in dgroup.groupby("aspect"):
            stats = _aspect_stats(agroup, pol_col)
            if stats["confidence"] == "suppressed":
                suppressed["destination_aspect"] += 1
                continue
            stats["aspect"] = aspect
            stats["label"] = C.ASPECTS[aspect].label
            stats["quotes"] = _quotes(agroup, pol_col)
            aspects[aspect] = stats

        complaints = {k: v for k, v in aspects.items() if k in C.COMPLAINT_ASPECTS}
        top = max(complaints.items(), key=lambda kv: kv[1]["n_negative"]) if complaints else None
        destinations.setdefault(district, {})[dest] = {
            "destination": dest,
            "district": district,
            "n_reviews": int(dgroup["review_id"].nunique()),
            "n_segments": int(dgroup["segment_id"].nunique()),
            "aspects": aspects,
            "aspects_shown": len(aspects),
            "top_complaint": top[0] if top else None,
            "top_complaint_n": top[1]["n_negative"] if top else 0,
        }

    # ---------------- district level ----------------
    districts = {}
    for district, dgroup in long.groupby("district"):
        aspects = {}
        for aspect, agroup in dgroup.groupby("aspect"):
            stats = _aspect_stats(agroup, pol_col)
            if stats["confidence"] == "suppressed":
                suppressed["district_aspect"] += 1
                continue
            stats["aspect"] = aspect
            stats["label"] = C.ASPECTS[aspect].label
            # Which places drive this district's complaints -- the useful
            # question for anyone who could actually fix it.
            worst = (agroup[agroup[pol_col] == "N"]
                     .groupby("destination").size()
                     .sort_values(ascending=False).head(5))
            stats["worst_destinations"] = [
                {"destination": d, "n_negative": int(n)} for d, n in worst.items()
            ]
            aspects[aspect] = stats

        complaints = {k: v for k, v in aspects.items() if k in C.COMPLAINT_ASPECTS}
        top = max(complaints.items(), key=lambda kv: kv[1]["n_negative"]) if complaints else None
        districts[district] = {
            "district": district,
            "n_destinations": int(dgroup["destination"].nunique()),
            "n_reviews": int(dgroup["review_id"].nunique()),
            "aspects": aspects,
            "top_complaint": top[0] if top else None,
            "destinations": destinations.get(district, {}),
        }

    # ---------------- country level ----------------
    country_aspects = {}
    for aspect, agroup in long.groupby("aspect"):
        stats = _aspect_stats(agroup, pol_col)
        stats["aspect"] = aspect
        stats["label"] = C.ASPECTS[aspect].label
        worst = (agroup[agroup[pol_col] == "N"]
                 .groupby("district").size().sort_values(ascending=False).head(12))
        stats["worst_districts"] = [
            {"district": d, "n_negative": int(n)} for d, n in worst.items()
        ]
        country_aspects[aspect] = stats

    return {
        "country": "Sri Lanka",
        "polarity_method": pol_col,
        "thresholds": {
            "suppress_below": C.MIN_MENTIONS_DISPLAY,
            "low_confidence_below": C.MIN_MENTIONS_CONFIDENT,
        },
        "coverage": {
            "n_districts": len(districts),
            "n_destinations": int(long["destination"].nunique()),
            "n_reviews": int(long["review_id"].nunique()),
            "n_aspect_mentions": int(len(long)),
            "suppressed_nodes": suppressed,
        },
        "aspects": country_aspects,
        "districts": districts,
    }


def flat_scorecards(tree: Dict) -> pd.DataFrame:
    """One row per (destination, aspect) -- the tabular release artifact."""
    rows = []
    for district, dinfo in tree["districts"].items():
        for dest, info in dinfo["destinations"].items():
            for aspect, s in info["aspects"].items():
                rows.append({
                    "district": district,
                    "destination": dest,
                    "aspect": aspect,
                    "aspect_label": s["label"],
                    "n_negative": s["n_negative"],
                    "n_positive": s["n_positive"],
                    "n_neutral": s["n_neutral"],
                    "n_opinions": s["n_opinions"],
                    "complaint_rate": s["complaint_rate"],
                    "confidence": s["confidence"],
                    "destination_reviews": info["n_reviews"],
                })
    return pd.DataFrame(rows).sort_values(
        ["district", "destination", "aspect"]).reset_index(drop=True)


def main():
    print("\nTravelLens LK -- Stage 6: aggregation\n" + "=" * 60)
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_scored.csv")
    tree = build_tree(seg)

    out_json = C.DATA_PROCESSED / "hierarchy.json"
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(tree, fh, indent=2, ensure_ascii=False)

    cards = flat_scorecards(tree)
    out_csv = C.DATA_PROCESSED / "scorecards.csv"
    cards.to_csv(out_csv, index=False, encoding="utf-8")

    cov = tree["coverage"]
    print("  districts            : {}".format(cov["n_districts"]))
    print("  destinations         : {}".format(cov["n_destinations"]))
    print("  aspect mentions      : {}".format(cov["n_aspect_mentions"]))
    print("  scorecard rows       : {}".format(len(cards)))
    print("  suppressed (dest)    : {}  -- below {} opinions".format(
        cov["suppressed_nodes"]["destination_aspect"], C.MIN_MENTIONS_DISPLAY))
    print()
    print("  NATIONAL PICTURE (complaint rate = share of opinions that complain)")
    print("  {:<20} {:>8} {:>8} {:>7}".format("aspect", "complaints", "praise", "rate"))
    print("  " + "-" * 46)
    for key, s in sorted(tree["aspects"].items(), key=lambda kv: -kv[1]["n_negative"]):
        print("  {:<20} {:>8} {:>8} {:>6}%".format(
            s["label"], s["n_negative"], s["n_positive"],
            "" if s["complaint_rate"] is None else round(100 * s["complaint_rate"], 1)))

    print("\nwrote {}".format(out_json))
    print("wrote {}".format(out_csv))


if __name__ == "__main__":
    main()
