"""The API and the dashboard must give the same sentence the same verdict.

api.py's docstring claimed they already did. They did not. A QA replay of
every segment-aspect pair in segments_scored.csv -- 85,539 of them, the same
count the dashboard reports as n_aspect_mentions -- found 360 disagreements:

    scenery rescue (api.py only)                       133
    site rule skipped unless cleanliness was tagged     73
    safety recall applied segment-wide, not per aspect  69
    post-model safety override (api.py only)            58
    crowd override (api.py only)                        13
    strong-lexicon override (api.py only)               10
    cleanliness rescue (api.py only)                     3
    roads difficulty override (api.py only)              1

The worst of them inverted real complaints: "A beautiful natural place killed
by humans." is a complaint on the dashboard and came back from /analyse as
praise, along with 96 other scenery segments.

The fix was to delete the six API-only rules and give both callers one
function, polarity.aspect_polarity(). These tests exist so it stays that way
-- a rule added to one surface and not the other fails here rather than in a
viva.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import config as C                      # noqa: E402
from travellens.aspects import tag_segment              # noqa: E402
from travellens.polarity import (                       # noqa: E402
    aspect_polarity,
    lexicon_polarity,
    safety_recall_rule,
    site_rule_is_not_a_complaint,
)

SCORED = C.DATA_PROCESSED / "segments_scored.csv"
ASPECT_KEYS = list(C.ASPECTS.keys())

# How many corpus rows to replay. The whole file is 177,840 rows; a few
# thousand is enough to catch a rule that fires on a recognisable pattern,
# and keeps the suite fast. Raise it when hunting something rare.
SAMPLE_ROWS = 6000


def _dashboard_label(segment, aspect, pol_final, lex_label):
    """What aggregate.py counts for this (segment, aspect) pair.

    Written out longhand rather than calling aspect_polarity(), so that this
    test still fails if someone changes the shared function's behaviour
    without meaning to. A test that calls the code under test to compute its
    own expectation cannot catch anything.
    """
    label, _ = safety_recall_rule(segment, pol_final, aspect == "safety", lex_label)
    label, _ = site_rule_is_not_a_complaint(segment, label)
    return label


def _corpus_rows():
    pd = pytest.importorskip("pandas")
    if not SCORED.exists():
        pytest.skip("segments_scored.csv not built; run scripts/06_polarity.py")
    df = pd.read_csv(SCORED, nrows=SAMPLE_ROWS)
    df = df[df["n_aspects"] > 0].dropna(subset=["pol_final", "pol_lexicon"])
    if df.empty:
        pytest.skip("no scored, tagged segments in the sample")
    return df


def test_api_chain_matches_the_dashboard_on_the_corpus():
    """Zero disagreements. Not 'few' -- the two are one function now."""
    df = _corpus_rows()
    disagreements = []

    for r in df.itertuples(index=False):
        keys = [a for a in ASPECT_KEYS if getattr(r, "asp_" + a)]
        if not keys:
            continue
        text = str(r.segment)
        for aspect in keys:
            api_label, _, _ = aspect_polarity(
                text, aspect, r.pol_final, r.pol_lexicon)
            dash_label = _dashboard_label(text, aspect, r.pol_final, r.pol_lexicon)
            if api_label != dash_label:
                disagreements.append((aspect, dash_label, api_label, text[:90]))

    assert not disagreements, (
        "{} segment-aspect pairs where the API and the dashboard disagree, "
        "e.g. {}".format(len(disagreements), disagreements[:5]))


def test_the_safety_recall_does_not_leak_onto_other_aspects():
    """A sentence can warn about safety and praise the view at once.

    api.py used to call safety_recall_rule once per segment and copy the
    result across every aspect, so the safety verdict became the scenery
    verdict too. aggregate.py has always passed the aspect in, which is why
    the rule takes that argument at all.
    """
    text = "Beautiful spot, the rocks can be slippery when it rains."
    lex_label, _ = lexicon_polarity(text)

    # "X" is the model's verdict on a hedged warning like this one -- neutral
    # at low confidence -- which is the case the safety recall exists for.
    safety, _, _ = aspect_polarity(text, "safety", "X", lex_label)
    scenery, _, _ = aspect_polarity(text, "scenery", "X", lex_label)

    assert safety == "N", "the hedged hazard must be recovered as a complaint"
    assert scenery == "X", "the safety verdict must not overwrite the scenery one"


def test_the_site_rule_applies_to_every_aspect_not_only_cleanliness():
    """A stated regulation is a regulation whichever aspect it is filed under.

    aggregate.py has always run this rule over the whole table. api.py ran it
    only when the segment was tagged cleanliness, so "Out side food not
    permitted" came back as a facilities COMPLAINT while the dashboard
    counted it as neutral -- 73 of the 360 disagreements.
    """
    text = "Out side food not permitted for inside."
    lex_label, _ = lexicon_polarity(text)

    for aspect in ("facilities", "cleanliness", "roads_access", "price_value"):
        label, _, _ = aspect_polarity(text, aspect, "N", lex_label)
        assert label == "X", (
            "{}: a reported regulation is not a complaint".format(aspect))


@pytest.mark.parametrize("text", [
    "A beautiful natural place killed by humans.",
    "Beautiful location marred by trash and the stench of trash everywhere.",
    "This waterfall with beautiful surroundings is not a suitable place for bathing.",
    "Once a beautiful place to hangout, not anymore",
])
def test_the_scenery_rescue_is_gone(text):
    """The deleted rule flipped a negative scenery verdict to positive on the
    strength of one beauty word. Because a complaint about a beautiful place
    almost always names the beauty, it fired on exactly the sentences that
    mattered: 97 dashboard-negative segments were reported as praise.

    A negative segment-level verdict must stay negative unless one of the
    three surviving rules -- which are in the pipeline too -- changes it.
    """
    lex_label, _ = lexicon_polarity(text)
    label, _, _ = aspect_polarity(text, "scenery", "N", lex_label)
    assert label == "N"


def test_the_switches_still_turn_the_rules_off():
    """ablation.py recomputes the published figures without each rule; the
    shared function has to keep honouring that or the ablation reports
    numbers no rule produced."""
    warning = "maybe a bit dangerous for small children."
    lex_label, _ = lexicon_polarity(warning)

    on, fired, _ = aspect_polarity(warning, "safety", "X", lex_label)
    off, not_fired, _ = aspect_polarity(
        warning, "safety", "X", lex_label, safety_recall=False)
    assert fired and on == "N"
    assert not not_fired and off == "X"

    rule = "Out side food not permitted for inside."
    rule_lex, _ = lexicon_polarity(rule)
    _, _, site_fired = aspect_polarity(rule, "facilities", "N", rule_lex)
    kept, _, site_off = aspect_polarity(
        rule, "facilities", "N", rule_lex, site_rule=False)
    assert site_fired
    assert not site_off and kept == "N"
