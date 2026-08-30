"""Scenery names the features themselves, so the noun fires wherever it appears.

The scenery lexicon lists lake, waterfall, hill, animal, elephant, because
"surrounded by green hills" is a scenery statement carrying none of the
abstract words the list was built from. Recall was 0.509 before the nouns
were added, so removing them is not an option.

The cost was misattribution. Measured on the corpus, 10,967 of 40,071 scenery
mentions (27%) rested on a bare noun with nothing in the segment saying the
feature was seen or admired, and the ones that also carried another aspect
were consistently about that other aspect:

    "Bad smell in some areas close to lake"                 -> scenery complaint
    "Animal cages should be more cleaned."                  -> scenery complaint
    "but wish they had more signage regarding the plants."  -> scenery complaint
    "Not the best facilities for all of the animals"        -> scenery complaint

config.SCENERY_ATTRIBUTION_RULE drops scenery in exactly that case: bare noun,
no cue, and another aspect already present. Measured effect on the published
figures -- scenery's complaint rate 10.2% -> 8.9%, every other aspect
unchanged to the decimal.

These tests pin both directions. The false-positive cases must lose the tag;
the recall cases must keep it, because an over-eager version of this rule
would drop 3,343 positive opinions like "One of the best waterfalls in Sri
Lanka" and undo the recall work the nouns were added for.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import config as C            # noqa: E402
from travellens.aspects import tag_segment    # noqa: E402


# --------------------------------------------------------------------------
# The misattributions the rule exists to remove. Every one of these is a real
# corpus segment that was counted as a scenery complaint.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("text,belongs_to", [
    ("Bad smell in some areas close to lake", "cleanliness"),
    ("Animal cages should be more cleaned.", "cleanliness"),
    ("but wish they had more signage regarding the plants.", "facilities"),
    ("Not the best facilities for all of the animals", "facilities"),
    ("The waters of the lake are also quite polluted, conditioning the "
     "created environment.", "cleanliness"),
    ("Sometimes bad smell spreading due to polluted water in lake.", "cleanliness"),
])
def test_a_bare_noun_does_not_make_it_scenery(text, belongs_to):
    keys = tag_segment(text)
    assert belongs_to in keys, "the real aspect must still be found"
    assert "scenery" not in keys, (
        "{!r} is about {}, not about how the place looks".format(text, belongs_to))


# --------------------------------------------------------------------------
# Recall. The rule must not touch any of these.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    # scenery-solo: the rule never fires, whatever the wording
    "One of the best waterfalls in Sri Lanka.",
    "Great Western mountain range.",
    "That was a super safari!",
    "We enjoyed the walk around the lake.",
    # an appearance word makes the evidence non-bare
    "Beautiful lake but the road is bad.",
    "Stunning views of the hills from the top of the climb.",
    # a sighting cue does the same -- the aspect's description covers
    # "wildlife sightings", and these carry no beauty word at all
    "We saw elephants and a few deer.",
    "The lake is surrounded by green hills.",
    "Good area to watch birds, though the path is rough.",
])
def test_genuine_scenery_keeps_its_tag(text):
    assert "scenery" in tag_segment(text), (
        "{!r} is a scenery mention and must survive the rule".format(text))


def test_the_rule_never_fires_on_a_scenery_only_segment():
    """The rule is about ATTRIBUTION between aspects, so a segment with
    nothing to re-attribute to must be left alone -- that is what keeps the
    3,343 bare-noun positives ("Birds and Elephants!") in the corpus."""
    for text in ("Birds and Elephants!", "Just a lake.", "Lots of trees.",
                 "Elephants.", "The river."):
        keys = tag_segment(text)
        if "scenery" in keys:
            assert keys == ["scenery"], keys


def test_the_rule_has_an_off_switch(monkeypatch):
    """SCENERY_ATTRIBUTION_RULE = False restores the pre-rule behaviour, so
    the change can be ablated the way every other hand-written rule in this
    project can. It is not yet confirmed against human labels -- no scenery
    label file exists in the repository -- and a rule that cannot be turned
    off cannot be answered for."""
    text = "Animal cages should be more cleaned."
    assert "scenery" not in tag_segment(text)
    monkeypatch.setattr(C, "SCENERY_ATTRIBUTION_RULE", False)
    assert "scenery" in tag_segment(text), "switch did not restore old behaviour"


def test_bare_noun_patterns_are_real_regexes():
    """A guard against the escaping accident that produced this list: the
    first version was written through a code generator that turned every
    \\b into a literal backspace character, so no pattern matched anything
    and the rule silently did nothing."""
    import re
    assert C.SCENERY_BARE_NOUNS, "list is empty"
    for pattern in C.SCENERY_BARE_NOUNS:
        assert "\x08" not in pattern, repr(pattern)
        re.compile(pattern)
    assert "\x08" not in C.SCENERY_CONTEXT_CUES
    re.compile(C.SCENERY_CONTEXT_CUES)
    assert re.search(C.SCENERY_BARE_NOUNS[1], "beside the lake"), \
        "lake pattern does not match the word it names"
