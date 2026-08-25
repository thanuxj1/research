"""Author-labelled PRICE test set: 64 real segments, 21 true positives.

Question: does the segment make a statement about cost, fees, charges, tips,
budget, or value FOR MONEY?

Boundary rule that decides many cases: bare "worth it" / "worth a visit" /
"worth the drive" is a RECOMMENDATION, not a price statement, and is labelled
NO. "worth the money", "worth 5 dollars", or "worth it" in an explicit cost
context is YES. The lexicon's r"\bworth (it|the)\b" trigger does not make this
distinction, which is the main source of its false positives here.

PROVENANCE: labelled by the assistant that built the pipeline. Developer test set.
"""
PRICE_POSITIVE = {
    "RULE":             {1,4,5,7,8,9,10,11,13,15,16,17},
    "TRAINED_NOT_RULE": {0,1,3,4,6,7,12,13},
    "HINT_NO_TAG":      {1},
    "RANDOM":           set(),
}
