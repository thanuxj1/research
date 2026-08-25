"""Author-labelled CROWDING + SCENERY test set: 66 real segments.

CROWD question: does the segment say something about how busy, quiet, noisy or
peaceful the PLACE is? "relative calm" describing WATER is not crowding.

SCENERY question: does it say something about views, landscape or natural
beauty? Photographs of the view count; photographs of a factory process do not.
Wall paintings are artwork, not scenery.

PROVENANCE: labelled by the assistant that built the pipeline. Developer test set.
"""
CROWD_POSITIVE = {
    "CROWD_RULE":       {0,1,2,3,5,6,7,8,9,10,11,12,13},
    "CROWD_HINT_NOTAG": {4,10},
    "SCEN_RULE":        {3},
    "SCEN_HINT_NOTAG":  set(),
    "NEITHER":          set(),
}
SCENERY_POSITIVE = {
    "CROWD_RULE":       {0,9,11,13},
    "CROWD_HINT_NOTAG": {9},
    "SCEN_RULE":        {0,1,2,3,4,5,7,8,9,11,12,13},
    "SCEN_HINT_NOTAG":  {3,4,6,8,9,10,12},
    "NEITHER":          {3},
}
