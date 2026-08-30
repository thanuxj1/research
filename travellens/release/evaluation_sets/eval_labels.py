"""
Author-labelled evaluation set for ASPECT EXTRACTION.

100 real segments drawn from the corpus, stratified into four strata by what
each extractor found (both / rules-only / model-only / neither), so precision
AND recall are both measurable. Labelling covers the four focus aspects only:
roads_access, cleanliness, facilities, safety.

*** PROVENANCE WARNING ***
These labels were produced by the assistant that wrote the pipeline, not by an
independent human annotator. They are therefore a DEVELOPER TEST SET, useful
for comparing extractors against each other, and NOT a substitute for the human
gold set. Any accuracy figure derived from this file must be reported as
"author-labelled" and carries an obvious risk of bias toward the system's own
assumptions. The 200-row human gold set replaces it.

Labelling rule applied: a segment is labelled with an aspect if it makes any
statement about that aspect -- opinion OR plain fact. "There are 199 steps to
the top" is roads_access even though it expresses no sentiment.
"""

# stratum -> index -> list of correct aspects
LABELS = {
    "BOTH": {
        0: ["roads_access", "safety"], 1: ["roads_access"], 2: ["facilities"],
        3: ["facilities"], 4: ["cleanliness"], 5: ["roads_access"],
        6: ["cleanliness"], 7: ["roads_access"], 8: ["roads_access"],
        9: ["roads_access"], 10: ["safety", "roads_access"], 11: ["roads_access"],
        12: ["roads_access"], 13: ["cleanliness"], 14: ["facilities"],
        15: ["safety", "roads_access"], 16: ["facilities"], 17: ["roads_access"],
        18: ["roads_access"], 19: ["facilities", "cleanliness"],
        20: ["facilities", "cleanliness"], 21: ["facilities"],
        22: ["cleanliness"], 23: ["roads_access"], 24: ["roads_access"],
    },
    "RULES_ONLY": {
        0: ["facilities"], 1: ["roads_access"], 2: ["roads_access"],
        3: ["roads_access"], 4: ["roads_access"], 5: ["roads_access"],
        6: ["facilities"], 7: [], 8: [],
        9: ["facilities", "roads_access"], 10: [], 11: ["facilities"],
        12: ["facilities"], 13: ["roads_access"], 14: ["facilities"],
        15: [], 16: ["roads_access"], 17: ["facilities"], 18: ["facilities"],
        19: ["facilities"], 20: ["roads_access"], 21: [], 22: [], 23: [],
        24: ["roads_access"],
    },
    "MODEL_ONLY": {
        0: ["roads_access"], 1: [], 2: ["roads_access"], 3: ["roads_access"],
        4: ["facilities"], 5: ["facilities"], 6: [], 7: [], 8: [], 9: [],
        10: ["roads_access"], 11: [], 12: [], 13: [], 14: [],
        15: ["facilities"], 16: ["roads_access"], 17: ["roads_access"],
        18: ["roads_access"], 19: [], 20: ["roads_access"], 21: [], 22: [],
        23: [], 24: [],
    },
    "NEITHER": {
        0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: [], 7: [],
        8: ["facilities"], 9: [], 10: [], 11: [], 12: [], 13: [], 14: [],
        15: ["facilities"], 16: [], 17: [], 18: [], 19: [], 20: [],
        21: ["roads_access"], 22: [], 23: [], 24: [],
    },
}

FOCUS = ["roads_access", "cleanliness", "facilities", "safety"]
