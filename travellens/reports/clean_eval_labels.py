"""Author-labelled CLEANLINESS test set: 72 real segments, 36 true positives.

Question: does the segment make a statement about litter, waste, pollution,
dirt, smell, water quality, or the general UPKEEP of the place?

Boundary calls made consistently:
  * "well maintained" / "not maintained" = YES (upkeep is cleanliness)
  * "don't waste your time" = NO (waste of time, not refuse)
  * pleasant smell of tea = NO (not a hygiene statement)
  * "no plastic bottles allowed" = YES (a litter-control rule)
  * toilets being repaired = NO (that is facilities)

PROVENANCE: labelled by the assistant that built the pipeline. Developer test
set, superseded by the human gold set.
"""
CLEAN_POSITIVE = {
    "RULE":             {0,1,2,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19},
    "TRAINED_NOT_RULE": {1,8,14,18},
    "HINT_NO_TAG":      {1,2,3,5,6,9,11,12,13,14,15,18,19},
    "RANDOM":           {9},
}
