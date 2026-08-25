"""
LostinSriLanka -- destination name canonicalisation.

The problem this solves
-----------------------
Place names arrive spelled differently from every source. The corpus already
contains:

    "Horton plains national park"   1,007 reviews   (Google Maps corpus)
    "Horton Plains National Park"     193 reviews   (TripAdvisor corpus)

Those are one place held as two destinations, so its reviews were split, its
scorecard understated, and the two corpora could not be compared at the place
that has the most data in both.

Newly scraped reviews make this worse, not better. The Google Places API
returns names like "Sembuwatta Lake" and "Sembuwatta Lake, Elkaduwa"; without
canonicalisation each variant becomes a NEW destination and the corpus
fragments a little more with every refresh.

How it works
------------
Each name is reduced to a key: lowercased, punctuation removed, articles and
country words dropped, whitespace collapsed. Names sharing a key are one place.

A second, looser key drops any trailing ", <area>" suffix, because Google
frequently appends the locality. It is tried only after the strict key fails.

What it deliberately does NOT do
--------------------------------
No fuzzy or substring matching. "Galle Fort" and "Galle Fort Clock Tower" share
a prefix and are different places; "Jungle Beach" and "Jungle Beach, Unawatuna"
are the same one. Substring matching cannot tell those apart, so merging is
restricted to exact key equality, where it can be justified. Remaining variants
are left separate rather than merged on a guess -- an under-merge loses some
data, an over-merge invents a place that does not exist.

Run with:  python scripts/16_canonicalise.py
"""
import re
from collections import Counter, defaultdict
from typing import Dict, Optional

import pandas as pd

from . import config as C

_PUNCT = re.compile(r"[^a-z0-9 ]")
_NOISE = re.compile(r"\b(the|a|an|of|at|in|sri lanka|srilanka|lk)\b")
_WS = re.compile(r"\s+")


def destination_key(name: str) -> str:
    """Strict key. Two names sharing this are treated as the same place."""
    s = _PUNCT.sub(" ", str(name).lower().strip())
    s = _NOISE.sub(" ", s)
    return _WS.sub(" ", s).strip()


def loose_key(name: str) -> str:
    """Strict key with any trailing ', <locality>' removed."""
    base = str(name).split(",")[0]
    return destination_key(base)


# Display names that the automatic rule cannot recover.
#
# Once a merge has collapsed a group, the better-capitalised variant no longer
# exists in the data, so the capitalisation preference has nothing to choose
# from on a later run. These are keyed on the canonical KEY, so they survive
# any spelling that maps into the group.
DISPLAY_OVERRIDES: Dict[str, str] = {
    "horton plains national park": "Horton Plains National Park",
}


def _capitalisation_score(name: str) -> int:
    """How many words are capitalised. A proxy for proper-noun styling."""
    return sum(1 for w in str(name).split() if w[:1].isupper())


def _preferred(variants) -> str:
    """Pick the display name for a group.

    This is a presentation choice only -- grouping is already decided by the
    key. Preference order:
      1. best capitalisation ("Horton Plains National Park" over
         "Horton plains national park"), because the dashboard shows this name
      2. most reviews
      3. longest, which usually carries the fuller official title
    """
    return sorted(
        variants.items(),
        key=lambda kv: (-_capitalisation_score(kv[0]), -kv[1], -len(kv[0])),
    )[0][0]


def build_map(destinations: pd.Series) -> Dict[str, str]:
    """variant name -> canonical display name."""
    counts = Counter(destinations.dropna())
    groups = defaultdict(dict)
    for name, n in counts.items():
        groups[destination_key(name)][name] = n

    mapping = {}
    for key, variants in groups.items():
        canon = DISPLAY_OVERRIDES.get(key) or _preferred(variants)
        for name in variants:
            mapping[name] = canon
    return mapping


def resolve(name: str, mapping: Dict[str, str],
            loose_index: Optional[Dict[str, str]] = None) -> str:
    """Route an incoming place name to an existing destination, or keep it.

    Called on every newly collected review. Strict key first; loose key only
    if the strict one finds nothing.
    """
    if name in mapping:
        return mapping[name]
    key = destination_key(name)
    for variant, canon in mapping.items():
        if destination_key(variant) == key:
            return canon
    if loose_index is not None:
        hit = loose_index.get(loose_key(name))
        if hit:
            return hit
    return name


def build_loose_index(mapping: Dict[str, str]) -> Dict[str, str]:
    """loose key -> canonical name, for suffix-stripped matching.

    Keys that would map to more than one canonical name are dropped: an
    ambiguous match must not silently pick one.
    """
    seen = defaultdict(set)
    for variant, canon in mapping.items():
        seen[loose_key(variant)].add(canon)
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def apply_to_corpus(corpus_path=None, dry_run: bool = False,
                    verbose: bool = True) -> Dict:
    """Merge existing duplicate destinations in the stored corpus."""
    corpus_path = corpus_path or C.CLEAN_REVIEWS_CSV
    df = pd.read_csv(corpus_path)
    mapping = build_map(df["destination"])

    merged = {canon: [v for v, c in mapping.items() if c == canon and v != canon]
              for canon in set(mapping.values())}
    merged = {k: v for k, v in merged.items() if v}

    before = df["destination"].nunique()
    df["destination"] = df["destination"].map(lambda d: mapping.get(d, d))
    after = df["destination"].nunique()

    report = {
        "destinations_before": int(before),
        "destinations_after": int(after),
        "groups_merged": len(merged),
        "merges": {k: v for k, v in merged.items()},
    }

    if verbose:
        print("  destinations: {} -> {}  ({} groups merged)".format(
            before, after, len(merged)))
        for canon, variants in merged.items():
            n = int((df["destination"] == canon).sum())
            print("    {} <- {}   ({} reviews now together)".format(
                canon, ", ".join(repr(v) for v in variants), n))

    if not dry_run and merged:
        df.to_csv(corpus_path, index=False, encoding="utf-8")
        if verbose:
            print("\n  wrote {}".format(corpus_path))
    elif dry_run:
        print("\n  (dry run -- nothing written)")
    return report


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Merge duplicate destination names.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("\nLostinSriLanka -- destination canonicalisation\n" + "=" * 60)
    apply_to_corpus(dry_run=args.dry_run)
    print("\n  next: python scripts/10_refresh.py")


if __name__ == "__main__":
    main()
