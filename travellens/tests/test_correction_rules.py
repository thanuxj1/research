"""
Guard tests: the hand-written correction rules must stay narrow, and must
stay switchable.

Three hand-written rules reach the published numbers, and the ablation
(scripts/33_ablate_rules.py) shows the headline claim turns on one of them:
switch off the safety recall and safety drops 50.9% -> 46.7%, below price &
value. A rule with that much leverage has to be exactly as narrow as it
claims, and has to remain possible to switch off and re-measure.

These test IMPACT and SCOPE, not correctness. Whether a flipped label is the
right label needs the human gold set -- see open problem #1.

Run:  python -m pytest tests/test_correction_rules.py -q
"""
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import aggregate, polarity  # noqa: E402
from travellens.polarity import (safety_recall_rule,  # noqa: E402
                                 site_rule_is_not_a_complaint)


# --------------------------------------------------------------------------
# The site-rule correction
# --------------------------------------------------------------------------
def test_a_reported_regulation_is_not_a_complaint():
    """The 18 real segments this was written for."""
    for text in [
        "Its is prohibited to take polythene , plastic bottles inside the park.",
        "Not allowed to bring any plastic or polythene.",
        "polythene and food items are not allowed here.",
        "You're not allowed to take non-biodegradable items such as plastic bags.",
    ]:
        label, fired = site_rule_is_not_a_complaint(text, "N")
        assert fired and label == "X", text


def test_an_actual_complaint_survives_the_rule():
    """'Polythene and plastic wastes are left everywhere' is a real grievance."""
    for text in [
        "Polythene and plastic wastes are left everywhere.",
        "Plastic is not allowed but people litter anyway.",
        "Prohibited, yet the place is filthy with rubbish.",
    ]:
        label, fired = site_rule_is_not_a_complaint(text, "N")
        assert not fired and label == "N", text


def test_a_prohibition_carrying_a_hazard_keeps_its_warning():
    """One correction rule must not undo another.

    The safety recall rule exists to recover hedged hazard warnings. If the
    site rule neutralised "not allowed to swim, the current is dangerous", it
    would erase exactly what the other rule recovered.
    """
    for text in [
        "Not allowed to swim here, the current is dangerous.",
        "Swimming is prohibited - people have drowned here.",
    ]:
        label, fired = site_rule_is_not_a_complaint(text, "N")
        assert not fired and label == "N", text


def test_the_site_rule_only_ever_neutralises():
    """It may turn N into X. It must never manufacture praise."""
    for start in ("P", "X"):
        label, fired = site_rule_is_not_a_complaint(
            "Plastic bottles are prohibited inside the park.", start)
        assert not fired and label == start
    label, _ = site_rule_is_not_a_complaint(
        "Plastic bottles are prohibited inside the park.", "N")
    assert label == "X", "a regulation must not become praise"


# --------------------------------------------------------------------------
# The safety recall rule -- the one the headline depends on
# --------------------------------------------------------------------------
def test_safety_recall_needs_all_of_its_conditions():
    """It fires only on a safety segment the model called neutral with an
    explicit hazard word and no positive lexicon reading."""
    hazard = "The rocks are slippery and it is dangerous near the edge."
    assert safety_recall_rule(hazard, "X", True, "N")[1], "should fire"
    assert not safety_recall_rule(hazard, "X", False, "N")[1], "not a safety segment"
    assert not safety_recall_rule(hazard, "N", True, "N")[1], "already negative"
    assert not safety_recall_rule(hazard, "X", True, "P")[1], "lexicon reads positive"
    assert not safety_recall_rule(
        "A calm and pleasant walk by the lake.", "X", True, "N")[1], "no hazard word"


def test_safety_recall_leaves_reassurance_alone():
    """'perfectly safe' must not become a complaint."""
    for text in ["It is perfectly safe for children.",
                 "Not dangerous at all, we felt fine."]:
        assert not safety_recall_rule(text, "X", True, "P")[1], text


# --------------------------------------------------------------------------
# Both must stay switchable, or they cannot be re-measured
# --------------------------------------------------------------------------
def test_every_deployed_rule_can_be_switched_off():
    """The ablation is only possible while these flags exist."""
    params = inspect.signature(aggregate.build_tree).parameters
    assert "safety_recall" in params, "the safety recall rule is not switchable"
    assert "site_rule" in params, "the site-rule correction is not switchable"
    assert params["safety_recall"].default is True
    assert params["site_rule"].default is True


def test_the_domain_patch_is_not_in_the_published_path():
    """hybrid_polarity feeds a comparison column, not the tree.

    If DEFAULT_POLARITY_COL ever became pol_hybrid, a rule documented as
    'not deployed' would start moving published figures.
    """
    assert aggregate.DEFAULT_POLARITY_COL == "pol_final"
    assert hasattr(polarity, "hybrid_polarity")
