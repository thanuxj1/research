"""
TravelLens LK -- Stage 2: segmentation.

Cuts each review into "opinion units": short pieces of text that each express
ONE opinion about ONE thing.

Why this stage exists
---------------------
A single review often praises and complains at the same time:

    "Nice location but bathing is dangerous here."

Scored as one block, the praise and the complaint cancel out and the safety
warning is lost. Scored as two pieces, both survive.

We therefore split on two kinds of boundary:
  1. Sentence enders  ( . ! ? and line breaks )
  2. Contrast markers ( but / however / although / though / unfortunately )
     -- because these words announce that the OPPOSITE opinion is coming next.

Run with:  python scripts/02_segment.py
"""
import re
from typing import List

import pandas as pd

from . import config as C

# --------------------------------------------------------------------------
# Repair pass
#
# Google Maps reviews are typed on phones. Punctuation is unreliable:
#   "Urban birds watching place.some are thinking..."   <- no space after stop
#   "Nice place must go.. but be carefull"              <- doubled stops
# A standard splitter looks for ". " and finds nothing, returning the whole
# review as one sentence. So we repair spacing before we split.
# --------------------------------------------------------------------------

# a lowercase/uppercase letter glued to the previous sentence by a full stop
_GLUED_RE = re.compile(r"([a-z0-9])([.!?])([A-Za-z])")
# runs of repeated stops: ".." "..." "!!!"
_REPEAT_STOP_RE = re.compile(r"([.!?])\1+")
_WS_RE = re.compile(r"\s+")


def repair_punctuation(text: str) -> str:
    """Insert the missing space after sentence-ending punctuation."""
    text = _REPEAT_STOP_RE.sub(r"\1", text)
    # apply twice: "a.b.c" needs two passes to separate fully
    for _ in range(2):
        text = _GLUED_RE.sub(r"\1\2 \3", text)
    return _WS_RE.sub(" ", text).strip()


# --------------------------------------------------------------------------
# Splitting
# --------------------------------------------------------------------------
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# Contrast markers. The marker STAYS with the piece that follows it, because
# "but the road is bad" carries the negative signal in the "but".
_CONTRAST_RE = re.compile(
    r"\s+(?=(?:but|however|although|though|unfortunately|otherwise|except)\b)",
    re.IGNORECASE,
)

# A piece shorter than this is almost always a fragment ("Nice.", "Wow"),
# not an opinion about anything specific.
MIN_SEGMENT_WORDS = 3


def split_into_segments(text: str) -> List[str]:
    """Return the opinion units contained in one review."""
    text = repair_punctuation(text)
    segments = []
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        for part in _CONTRAST_RE.split(sentence):
            part = part.strip(" ,;:-")
            if part:
                segments.append(part)
    return segments


def segment_corpus(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Explode a cleaned review table into one row per opinion unit."""
    rows = []
    for r in df.itertuples(index=False):
        pieces = split_into_segments(r.text)
        for i, piece in enumerate(pieces):
            n_words = len(piece.split())
            rows.append({
                "segment_id": "{}_{}".format(r.review_id, i),
                "review_id": r.review_id,
                "seg_index": i,
                "destination": r.destination,
                "district": r.district,
                "segment": piece,
                "n_words": n_words,
                "is_truncated": r.is_truncated,
                "recency": r.recency,
                # Kept rather than dropped so the count is auditable; the
                # aspect stage ignores anything flagged too short.
                "too_short": n_words < MIN_SEGMENT_WORDS,
            })
    out = pd.DataFrame(rows)

    if verbose:
        usable = out[~out["too_short"]]
        print("  reviews in            : {}".format(len(df)))
        print("  segments out          : {}".format(len(out)))
        print("  usable segments       : {}  (>= {} words)".format(
            len(usable), MIN_SEGMENT_WORDS))
        print("  avg segments / review : {:.2f}".format(len(out) / max(len(df), 1)))
        print("  reviews that split    : {} ({:.1f}%)".format(
            int((out.groupby("review_id").size() > 1).sum()),
            100 * (out.groupby("review_id").size() > 1).mean()))
    return out


def main():
    print("\nTravelLens LK -- Stage 2: segmentation\n" + "=" * 60)
    df = pd.read_csv(C.CLEAN_REVIEWS_CSV)
    seg = segment_corpus(df)

    out_path = C.DATA_PROCESSED / "segments.csv"
    seg.to_csv(out_path, index=False, encoding="utf-8")
    print("\nwrote {}".format(out_path))


if __name__ == "__main__":
    main()
