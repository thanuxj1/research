"""Author-labelled SAFETY test set: 90 real segments, 22 true positives.

Question asked of each segment: does it make a statement about PHYSICAL RISK
to a visitor -- hazard, injury, drowning, unsafe conditions, or an explicit
warning? Wildlife SIGHTINGS are not safety; wildlife WARNINGS are. Financial
warnings ("careful, they overcharge") are not safety. Difficulty alone ("steep
steps") is access, not safety, unless a hazard is asserted.

PROVENANCE: labelled by the assistant that built the pipeline, not an
independent annotator. Developer test set. Replaced by the human gold set.
"""
SAFETY_POSITIVE = {
    "RULE_SAFETY":        {1,3,4,5,6,8,11,12,14,18,20,24},
    "MODEL_SAFETY":       {9,10,11,16,22},
    "HAZARD_WORD_NO_TAG": {3,7,9,19,23},
    "RANDOM_OTHER":       set(),
}
