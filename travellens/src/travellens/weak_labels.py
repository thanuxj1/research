"""
LostinSriLanka -- weak supervision from star ratings.

Purpose
-------
Hand-labelling is expensive: 600 rows costs about three hours. Star ratings are
free and unlimited -- every newly scraped Google review carries one. This module
converts stars into WEAK training labels so a model can be pre-trained on
thousands of examples before it is fine-tuned on the few hundred human ones.

The honest limits of a star rating -- state these in the thesis
--------------------------------------------------------------
1. A star rating describes the WHOLE review, not one aspect. A 5-star review
   may still contain "but the road is terrible". Applying the review's star to
   every segment inside it is therefore WRONG for a measurable fraction of
   segments.

2. Ratings are J-shaped. Most Google reviews are 4 or 5 stars, so naive use
   floods the training set with positives and teaches the model to say "praise"
   for everything.

3. 3-star reviews are genuinely ambiguous and are discarded rather than guessed.

Because of (1), weak labels are used for PRE-TRAINING ONLY. They are never
mixed into the gold set, never used for evaluation, and never allowed to touch
the held-out test split. The gold set stays purely human, which is what makes
every reported number meaningful.

Mitigation for (1)
------------------
Only single-opinion reviews contribute. If a review split into more than one
segment, or contains a contrast marker ("but", "however"), its star rating
cannot be attributed to any one segment and the review is skipped. This
throws away a lot of data -- deliberately. Cheap labels are only worth having
if they are mostly right.

Run with:  python scripts/12_weak_labels.py
"""
import json
import re
from typing import Dict, Optional

import pandas as pd

from . import config as C

# Reviews at 3 stars are discarded: the rating carries no clear direction.
STAR_TO_LABEL = {1: "N", 2: "N", 4: "P", 5: "P"}

CONTRAST_RE = re.compile(r"\b(but|however|although|though|except)\b", re.IGNORECASE)

# Cap on how many segments any one class may contribute, to counter the
# J-shaped distribution. Without this the model sees ~8 praise for every
# complaint and learns to answer "praise" unconditionally.
MAX_PER_CLASS_RATIO = 1.5


def derive(seg: pd.DataFrame, reviews: pd.DataFrame,
           verbose: bool = True) -> pd.DataFrame:
    """Build the weak training table from segments plus rated reviews."""
    rated = reviews.dropna(subset=["rating"]).copy()
    rated["rating"] = pd.to_numeric(rated["rating"], errors="coerce")
    rated = rated.dropna(subset=["rating"])
    rated["star_label"] = rated["rating"].round().astype(int).map(STAR_TO_LABEL)

    stats = {
        "reviews_with_rating": int(len(rated)),
        "discarded_3_star": int(rated["star_label"].isna().sum()),
    }
    rated = rated.dropna(subset=["star_label"])

    # Attribute the star only where it can honestly belong to one opinion.
    #
    # Two tiers, because a single strict rule discards almost the entire
    # TripAdvisor corpus: those reviews average 56 words and nearly always split
    # into several segments, so "single-segment reviews only" removed 41,053 of
    # them and left 755 examples.
    #
    #   TIER 1 (high confidence)  -- the review produced exactly one segment.
    #       The star can only refer to that one opinion.
    #
    #   TIER 2 (medium confidence) -- the review produced several segments BUT
    #       carries an EXTREME rating (1 or 5 stars) and the segment itself
    #       contains no contrast marker. A 1-star review is overwhelmingly
    #       complaint throughout; a 5-star review overwhelmingly praise. This is
    #       weaker than tier 1 and is recorded as such in the `tier` column, so
    #       the thesis can report results with and without it.
    #
    # 2- and 4-star reviews are admitted only under tier 1: they are the ratings
    # most likely to be mixed, and attributing them across segments would be the
    # least defensible extrapolation available.
    seg = seg[(seg["n_aspects"] > 0) & (~seg["too_short"])].copy()
    per_review = seg.groupby("review_id").size()
    single = set(per_review[per_review == 1].index)

    rating_map = rated.set_index("review_id")["rating"].round().astype(int).to_dict()
    label_map = rated.set_index("review_id")["star_label"].to_dict()

    seg = seg[seg["review_id"].isin(label_map)].copy()
    stats["segments_in_rated_reviews"] = int(len(seg))

    seg["label"] = seg["review_id"].map(label_map)
    seg["stars"] = seg["review_id"].map(rating_map)
    has_contrast = seg["segment"].str.contains(CONTRAST_RE.pattern, na=False,
                                               regex=True, case=False)

    tier1 = seg["review_id"].isin(single)
    tier2 = (~tier1) & seg["stars"].isin([1, 5]) & (~has_contrast)

    stats["tier1_single_segment"] = int(tier1.sum())
    stats["tier2_extreme_rating"] = int(tier2.sum())
    stats["dropped_unattributable"] = int((~tier1 & ~tier2).sum())

    usable = seg[tier1 | tier2].copy()
    usable["tier"] = ["tier1_single" if t else "tier2_extreme"
                      for t in tier1[tier1 | tier2]]

    before = len(usable)
    usable = usable[~(usable["tier"].eq("tier1_single") &
                      usable["segment"].str.contains(CONTRAST_RE.pattern, na=False,
                                                     regex=True, case=False))]
    stats["dropped_contrast"] = int(before - len(usable))

    # ------------------------------------------------------------------
    # Weak NEUTRAL labels.
    #
    # Star ratings cannot supply these: a rating is always positive or
    # negative, never "this is a plain statement of fact". Training on stars
    # alone therefore produces a model with no neutral class at all -- which
    # would undo the single biggest gain of moving to a 3-class model, since
    # roughly a third of this corpus is factual ("Entrance fee is 150 LKR",
    # "It is an 8 km walk", "Open until 2pm").
    #
    # So neutrals are mined by RULE, not by a model. A segment qualifies when
    # it states a measurable fact and carries no sentiment vocabulary at all:
    #
    #   * contains a number with a unit, price, time or distance
    #   * contains NO positive or negative lexicon word
    #   * contains no negator and no improvement request
    #
    # Deriving these from a rule rather than from a model's predictions keeps
    # the training labels independent of the systems being evaluated. Using
    # 3-star reviews was considered and rejected: a 3-star review is MEDIOCRE,
    # which is a sentiment, not the absence of one.
    # ------------------------------------------------------------------
    from .polarity import (NEGATIVE_WORDS, NEGATORS, POSITIVE_WORDS,
                           REQUEST_PATTERNS, _TOKEN_RE)

    FACTUAL = re.compile(
        r"\b\d+\s*(km|kilomet|m\b|meters?|metres?|min|minutes?|hours?|hrs?|"
        r"rs\.?|lkr|rupees?|usd|\$|euro|€|am\b|pm\b|o'?clock|feet|ft\b|acres?|"
        r"steps?|people|persons?)\b|\b(rs\.?|lkr|usd|\$)\s*\d+", re.IGNORECASE)

    # A factual statement is short. Opinions ramble, and a long segment that
    # merely happens to contain a number is usually an opinion with a number in
    # it -- "after half an hour it got very busy with flippers in everyone's
    # faces" states a time and is plainly a complaint. Capping the length is a
    # cheap and effective guard against admitting those as neutral.
    MAX_FACTUAL_WORDS = 15

    sentiment_words = POSITIVE_WORDS | NEGATIVE_WORDS | NEGATORS
    cand = seg[seg["segment"].str.contains(FACTUAL, na=False)].copy()
    keep = []
    for r in cand.itertuples(index=False):
        words = str(r.segment).split()
        if len(words) > MAX_FACTUAL_WORDS:
            continue
        toks = set(_TOKEN_RE.findall(str(r.segment).lower()))
        if toks & sentiment_words:
            continue
        if REQUEST_PATTERNS.search(str(r.segment)):
            continue
        # A contrast marker means an opinion is being set against something.
        # "although this is common, foreigners get charged 300 rupees" states a
        # price and is a complaint about it.
        if CONTRAST_RE.search(str(r.segment)):
            continue
        keep.append(r)
    neutral = pd.DataFrame(keep)
    if not neutral.empty:
        neutral = neutral.drop_duplicates(subset=["segment_id"]).copy()
        neutral["label"] = "X"
        neutral["tier"] = "tier3_factual_rule"
    stats["tier3_factual_neutral"] = int(len(neutral))

    usable = pd.concat([usable, neutral], ignore_index=True) if not neutral.empty else usable
    usable = usable.drop_duplicates(subset=["segment_id"])

    # One training row per (segment, aspect) -- same shape the fine-tuner uses.
    rows = []
    for r in usable.itertuples(index=False):
        for aspect in C.ASPECTS:
            if getattr(r, "asp_" + aspect, False):
                rows.append({
                    "segment_id": r.segment_id,
                    "text": r.segment,
                    "aspect": aspect,
                    "label": r.label,
                    "tier": r.tier,
                    "stars": r.stars,
                    "source": "weak_star",
                })
    weak = pd.DataFrame(rows)

    # Balance the classes.
    if not weak.empty:
        counts = weak["label"].value_counts()
        if len(counts) > 1:
            floor = counts.min()
            cap = int(floor * MAX_PER_CLASS_RATIO)
            weak = (weak.groupby("label", group_keys=False)[weak.columns.tolist()]
                        .apply(lambda g: g.sample(min(len(g), cap), random_state=42))
                        .reset_index(drop=True))
        stats["after_balancing"] = weak["label"].value_counts().to_dict()
        stats["by_tier"] = weak["tier"].value_counts().to_dict()

    stats["weak_examples"] = int(len(weak))

    if verbose:
        print("  reviews carrying a star rating   : {}".format(stats["reviews_with_rating"]))
        print("  discarded (3-star, ambiguous)    : {}".format(stats["discarded_3_star"]))
        print()
        print("  tier 1 (single-segment review)   : {}".format(stats["tier1_single_segment"]))
        print("  tier 2 (1 or 5 star, no contrast): {}".format(stats["tier2_extreme_rating"]))
        print("  tier 3 (factual, rule-derived X) : {}".format(stats.get("tier3_factual_neutral",0)))
        print("  dropped (cannot attribute star)  : {}".format(stats["dropped_unattributable"]))
        print("  dropped (contrast in tier 1)     : {}".format(stats["dropped_contrast"]))
        print()
        print("  WEAK TRAINING EXAMPLES           : {}".format(stats["weak_examples"]))
        if "after_balancing" in stats:
            print("  class balance after capping      : {}".format(stats["after_balancing"]))
            print("  by tier                          : {}".format(stats["by_tier"]))

    weak.attrs["stats"] = stats
    return weak


def exclude_gold(weak: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Remove any segment that appears in the human gold set.

    Non-negotiable. A weak label leaking into the evaluation set would mean the
    model is partly graded on labels it was trained on, and every reported score
    would be inflated by an unknown amount.
    """
    gold_path = C.REPORTS / "goldset_annotator1.csv"
    if not gold_path.exists():
        return weak
    gold_ids = set(pd.read_csv(gold_path)["segment_id"])
    before = len(weak)
    weak = weak[~weak["segment_id"].isin(gold_ids)].reset_index(drop=True)
    if verbose:
        print("  removed {} weak rows overlapping the gold set".format(before - len(weak)))
    return weak


def main():
    print("\nLostinSriLanka -- weak supervision from star ratings\n" + "=" * 60)

    reviews = pd.read_csv(C.CLEAN_REVIEWS_CSV)
    if "rating" not in reviews.columns or reviews["rating"].notna().sum() == 0:
        print("\n  No star ratings in the corpus yet.\n")
        print("  The Kaggle scrape did not capture ratings. Newly collected")
        print("  Google reviews do carry them -- your collector already reads")
        print("  `stars`. Once you have ingested rated reviews, re-run this.\n")
        print("  Collect, then:")
        print("    python scripts/09_ingest.py data/incoming/<batch>.json")
        print("    python scripts/10_refresh.py")
        print("    python scripts/12_weak_labels.py\n")
        return

    seg = pd.read_csv(C.DATA_PROCESSED / "segments_tagged.csv")
    weak = derive(seg, reviews)
    weak = exclude_gold(weak)

    out = C.DATA_PROCESSED / "weak_training_set.csv"
    weak.to_csv(out, index=False, encoding="utf-8")
    with open(C.REPORTS / "weak_labels_report.json", "w", encoding="utf-8") as fh:
        json.dump(weak.attrs.get("stats", {}), fh, indent=2)
    print("\nwrote {}".format(out))


if __name__ == "__main__":
    main()
