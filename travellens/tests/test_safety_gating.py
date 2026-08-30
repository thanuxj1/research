"""Safety triggers that only count in context.

Why these tests exist
---------------------
Safety was the weakest aspect in the pipeline: precision 0.394 on the gold
set's headline sample, meaning most segments tagged "safety" were not about
safety. A per-trigger audit against reports/goldset_focused_annotator1.csv
showed the errors were not spread out -- three triggers produced nearly all
of them, and every one of those errors was the same two mistakes:

    wildlife SIGHTINGS   "we saw deer, elephant, crocodiles, monkeys"
    the adjective        "the current lighthouse", "the current situation"

Deleting the words would have lost the real warnings with them ("a monkey
snatched my bag", "there is a strong rip current"), so the ambiguous ones are
gated instead: they mark safety only when a risk cue appears in the same
segment.

These tests pin both directions. A gate that blocks everything would score
well on precision and be useless, so the "still tagged" cases matter as much
as the "no longer tagged" ones.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens.aspects import matched_terms, tag_segment  # noqa: E402


def is_safety(text):
    return "safety" in tag_segment(text)


# Real segments from the gold set that a human did NOT judge to be about
# safety, and that the ungated lexicon tagged anyway.
SIGHTINGS_NOT_HAZARDS = [
    "We saw a few monkeys, a deer and a few birds",
    "We even saw a lone elephant, few crocs, lots of monkeys and peacocks.",
    "we spotted deer, elephant, crocodiles, peacock, leopards, rare birds, monkey etc in the huge national park.",
    "On the 2nd smaller pond at the rear is a carved 5 headed snake as well as a lion.",
    "The current bell-shaped stupa is encircled by smaller shrines and stone pillars.",
    "the history of the site is The current lighthouse structure was built in 1939",
    "People keep touching statues all over without a thought about the current situation.",
]


@pytest.mark.parametrize("text", SIGHTINGS_NOT_HAZARDS)
def test_a_sighting_is_not_a_hazard(text):
    assert not is_safety(text), (
        "tagged as safety, but it is a wildlife sighting or the adjective "
        "'current' -- this is the failure mode gating exists to stop"
    )


# The same words, in segments that ARE warnings. If gating swallowed these it
# would have traded one error for a worse one.
HAZARDS_STILL_CAUGHT = [
    "A monkey bit my son on the way up, be careful with children.",
    "Beware of the monkeys, they will snatch food straight out of your hand.",
    "Do not swim here, there are crocodiles and it is genuinely dangerous.",
    "Watch out for snakes on the path, one attacked a visitor last month.",
    "But the current is a little strong and you need to be a good swimmer.",
    "there's a bit of a rip current you need to watch out for",
    "Be very careful if you go in the sea with children - there are some VERY strong rip tides",
    "Watch out for slippery rocks and edge of a 200 metre drop.",
    "Leeches everywhere, find out and protect yourself when you go there",
]


@pytest.mark.parametrize("text", HAZARDS_STILL_CAUGHT)
def test_a_real_warning_is_still_caught(text):
    assert is_safety(text), "a genuine hazard warning stopped being tagged"


def test_gating_is_used_deliberately_and_not_everywhere():
    """Gating is a general mechanism now, but it is not a default.

    Every gate below is here because a specific trigger was measured firing
    on its own and being wrong. The measurement is named so a reader can
    check it rather than take the gate on trust.

        safety        wildlife nouns  + RISK_CUE     precision 0.394 -> 0.926
        price_value   foreigner/tips  + MONEY_CUE    precision 0.733 -> 0.800
        roads_access  climb/jeep      + ACCESS_CUE   F1 0.635 -> 0.762
        cleanliness   bottles         + LITTER_CUE   sole evidence 3x on the
                      contested dev sample, wrong all 3 ("carry a water
                      bottle"). Part B F1 0.919 -> 1.000.
        facilities    food     + FOOD_PROVISION_CUE  "don't show them you have
                      any food" is monkey advice, not an amenity.
                      Part B F1 0.703 -> 0.722 with the guidebook veto.
        crowd         many people     + CROWDING_CUE measured on the corpus,
                      not the gold set -- crowd has no human labels. The
                      phrase is the only crowd evidence in 182 segments and
                      128 of them carry no crowding language at all ("many
                      people visit to enjoy the beautiful sunset").

    Any OTHER aspect acquiring gated triggers should be a deliberate act with
    its own evidence, so this pins the set.
    """
    from travellens import config as C
    gated = {k for k, a in C.ASPECTS.items() if getattr(a, "gated", [])}
    assert gated == {"safety", "price_value", "roads_access",
                     "cleanliness", "facilities", "crowd"}, (
        "an aspect gained gated triggers -- add it here with the measurement "
        "that justified it")


def test_the_explanation_names_the_context_that_admitted_it():
    """matched_terms() is what shows a reader WHY a segment was filed here.

    For a gated trigger the trigger alone is not the reason -- the context is
    half of it -- so both are reported.
    """
    terms = matched_terms(
        "Beware of the monkeys, they will snatch food from your hand.", "safety"
    )
    joined = " ".join(terms)
    assert "monkey" in joined
    assert any("+" in t for t in terms), (
        "a gated match should report trigger + context, not the trigger alone"
    )


def test_ungated_triggers_still_work_alone():
    """Unambiguous words need no context and must not have been gated."""
    for text in ["The path is very slippery.",
                 "This place is dangerous.",
                 "It is not safe to swim here."]:
        assert is_safety(text), text


# --------------------------------------------------------------------------
# Caution advice: a warning carried by the imperative, not by a hazard noun
#
# Measured on the human gold set: every safety segment where a human said
# COMPLAINT and the pipeline said neutral was of this shape, and HAZARD_WORDS
# matched none of them. "deep", "narrow" and "slip ... properly" are not
# hazard nouns; the warning is in "be careful". Adding the branch flipped 6 of
# them with 0 new errors -- safety's conditional polarity accuracy 53.8% ->
# 76.9% overall, 36.4% -> 63.6% on the held-out sample.
# --------------------------------------------------------------------------
CAUTION_WARNINGS = [
    "Be careful when bathing as one area is very deep",
    "On the way up to here be careful with u r vehicles coz road is kinda narrow.",
    "Be careful with the lake.",
    "The entry steps can slip if u dont climb properly ,so take care when climbing",
    "If you do have a pair of good hiking shoe will be better else be careful of slipping.",
    "Watch out for the steps near the entrance.",
]


@pytest.mark.parametrize("text", CAUTION_WARNINGS)
def test_caution_advice_is_recovered_as_a_complaint(text):
    """The model calls these neutral. A human calls them warnings, and this
    project exists to surface warnings."""
    from travellens.polarity import safety_recall_rule
    label, fired = safety_recall_rule(text, "X", True, "X")
    assert label == "N" and fired, text


def test_caution_advice_ignores_the_lexicon_guard_on_purpose():
    """The hazard branch stands down when the lexicon reads positive, because
    that guard is what protects "perfectly safe" from being flipped. The
    caution branch does not, because three of the six segments it recovers
    score lexicon-positive -- a reassuring clause sits beside the warning
    ("...so take care when climbing, its not a issue"). A direct instruction
    to be careful is a warning whatever else the sentence says."""
    from travellens.polarity import safety_recall_rule
    text = "Be careful of slipping, though the view is lovely."
    assert safety_recall_rule(text, "X", True, "P") == ("N", True)


def test_the_caution_branch_still_respects_the_other_two_conditions():
    """It must not fire for a non-safety aspect, and it must not overwrite a
    verdict the model already committed to."""
    from travellens.polarity import safety_recall_rule
    text = "Be careful when bathing as one area is very deep"
    assert safety_recall_rule(text, "X", False, "X") == ("X", False), \
        "fired for an aspect that is not safety"
    assert safety_recall_rule(text, "P", True, "X") == ("P", False), \
        "overwrote a confident model verdict"


def test_reassurance_is_not_turned_into_a_warning():
    """The rule needs an instruction, not the word 'careful' anywhere."""
    from travellens.polarity import safety_recall_rule
    for text in ("The staff are careful and the place is well run.",
                 "Careful planning has gone into the layout.",
                 "It is perfectly safe for families."):
        label, fired = safety_recall_rule(text, "X", True, "X")
        assert (label, fired) == ("X", False), text
