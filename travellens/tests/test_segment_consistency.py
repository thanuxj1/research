"""api.py and analyse.py are supposed to be the same engine -- api.py is the
deployed REST endpoint, analyse.py is the CLI/library version used for
single-review testing and documented as running "the same stage used here"
as the corpus.

They disagreed. split_into_segments() returns every piece a sentence splits
into, including the tail end of a contrast split ("though.", "but.") which
carries no opinion of its own. api.py filtered those out with a hardcoded
`len(p.split()) >= 3`; analyse.py applied no filter at all. So the same
review, sent through the two "identical" engines, produced a different
number of segments -- caught during QA, not by design.

Both now import MIN_SEGMENT_WORDS from segment.py rather than each picking
their own number (api.py had 3, matching the real constant only by
coincidence). These tests pin that they stay in agreement.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens.segment import split_into_segments, MIN_SEGMENT_WORDS  # noqa: E402
from travellens.analyse import analyse  # noqa: E402

CONTRAST_FRAGMENT_TEXT = (
    "The view from the top is absolutely stunning though. "
    "The toilets were filthy but ok I guess."
)


def test_a_contrast_tail_fragment_does_not_survive_as_its_own_unit():
    """"though." on its own is exactly the failure this pins -- it carries
    no opinion, but split_into_segments() will hand it back as a segment
    unless a caller filters by MIN_SEGMENT_WORDS."""
    units = [u for u in split_into_segments(CONTRAST_FRAGMENT_TEXT)
            if len(u.split()) >= MIN_SEGMENT_WORDS]
    assert not any(u.strip().rstrip(".").lower() == "though" for u in units)


def test_analyse_applies_the_same_filter_api_py_does():
    """analyse.py (the CLI engine) must not emit units api.py (the deployed
    endpoint) would have dropped -- that gap is what this file exists to
    close."""
    res = analyse(CONTRAST_FRAGMENT_TEXT, use_transformer=False)
    unit_texts = [u["unit"] for u in res["units"]]
    assert not any(len(u.split()) < MIN_SEGMENT_WORDS for u in unit_texts), (
        f"analyse.py emitted a sub-threshold fragment: {unit_texts}")


def test_real_opinion_units_are_not_collateral_damage():
    """The filter must only remove fragments, not shrink a genuine short
    opinion like "Very peaceful." (3 words, at the threshold)."""
    res = analyse("Very peaceful here.", use_transformer=False)
    assert len(res["units"]) == 1
    assert res["units"][0]["unit"] == "Very peaceful here."
