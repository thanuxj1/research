""""Free" means two unrelated things in this corpus, and the price aspect
was claiming both.

Found by reading the dashboard's own praise list for Horton Plains: four
consecutive "praise" quotes under Price & Value that were nothing of the
kind --

    "free tourist visas ... a great way of encouraging tourists"
    "a clean litter free environment"
    "National Parks that is just as beautiful and free to all"
    "In the UK national parks are free..."   (a complaint, by comparison)

-- all tagged price_value because the bare trigger r"\bfree\b" matched. The
praise side is what exposed it: a wrong quote among complaints reads as a
harsh judgement, but a wrong quote among PRAISE reads as nonsense, so the
error had been invisible until both sides became readable.

Deleting the trigger was not an option. Most uses here really are about
price -- free entry, free food, free airport pickup, ~800 segments of it --
so this needed sense disambiguation, not removal:

    FREE_PRICE_CUE   admits the price senses, including the ones with no
                     money word at all ("free food", "all is free there")
    blocked          vetoes the compound-adjective sense outright
                     ("litter free", "free from plastic pollution"), which
                     a cue cannot catch: those sentences can legitimately
                     mention a fee elsewhere and still not be about price.

Measured on the human-labelled price sample after the change: precision
0.797 -> 0.823, recall unchanged at 0.962, F1 0.872 -> 0.887.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens.aspects import matched_terms, tag_segment  # noqa: E402


def is_price(text):
    return "price_value" in tag_segment(text)


# The real false positives from the dashboard, plus the other non-price
# senses the corpus actually contains.
NOT_ABOUT_PRICE = [
    "The recent implementation of free tourist visas for stays of less than "
    "one month is a great way of encouraging tourists to return.",
    "After witnessing the litter problem in Sri Lanka it was very pleasant "
    "to visit such a clean litter free environment.",
    "but we felt we could be doing a walk in one of our National Parks that "
    "is just as beautiful and free to all.",
    "A free environment.",
    "It can be called as one of the few places that are free from polythene "
    "and plastic pollution.",
    "Nice place to spend free time.",
    "Great place visit in your free times.",
    "a new kind of free environment for couples",
]


@pytest.mark.parametrize("text", NOT_ABOUT_PRICE)
def test_the_non_monetary_senses_are_not_price(text):
    assert not is_price(text), (
        "tagged price_value, but 'free' here means unencumbered / absent / "
        "at liberty -- not costing nothing"
    )


# The same word where it IS a price statement. If the fix swallowed these it
# would have traded a precision problem for a worse recall one -- which it
# did on the first attempt, dropping 1,061 segments including genuine ones,
# and is why this half of the test matters as much as the half above.
IS_ABOUT_PRICE = [
    "Free food and alcohol.",
    "Free drinks and food, staff most helpful.",
    "Bellagio offer free pickup drop service from the Airport as well as Hotel.",
    "All is free there",
    "But can park by the roadside close to the entrance for free.",
    "Entrance free unless you hire a guide.",
    "if you play or 5k and above food and drinks are free.",
    "Drink and food free.",
    "the casino gives drop service free till the hotel",
    "Free to enter, this working tea factory offers you an informative tour.",
    "There was a free cup of tea at the end of the tour.",
]


@pytest.mark.parametrize("text", IS_ABOUT_PRICE)
def test_the_monetary_sense_is_still_caught(text):
    assert is_price(text), "a genuine 'costs nothing' price statement was lost"


def test_explanation_agrees_with_the_tag():
    """matched_terms() is what shows a reader WHY a segment was filed under
    an aspect. It must not name words for an aspect that was vetoed -- an
    explanation for a tag that does not exist is worse than none."""
    blocked_text = "a clean litter free environment"
    assert not is_price(blocked_text)
    assert matched_terms(blocked_text, "price_value") == []


def test_blocked_is_declared_deliberately_and_not_everywhere():
    """A veto is stronger than a gate and should stay rare: it discards a
    match no matter what else the sentence says. Any aspect acquiring one
    should be a measured decision with its own evidence, so this pins the
    set the way the gated set is pinned.

    Each veto here covers a phrase where the trigger word simply never
    carries the aspect's sense, so a condition would be the wrong shape:

        price_value   "litter free", "hassle free" -- compound adjectives
                      where "free" has no monetary meaning at all.
        facilities    "guide book" -- a printed book, not a guide service.
        crowd         "busy capital", "escape from the busy ..." -- 109
                      corpus segments where "busy" is the only crowd
                      evidence and it describes the CITY the site sits in,
                      in a sentence calling the site the opposite of
                      crowded. Measured on the corpus: crowd has no human
                      labels, so this rests on the pattern's consistency
                      rather than on a precision figure.
    """
    from travellens import config as C
    blocked = {k for k, a in C.ASPECTS.items() if getattr(a, "blocked", [])}
    assert blocked == {"price_value", "facilities", "crowd"}, (
        "an aspect gained blocked patterns -- add it here with the "
        "measurement that justified it")
