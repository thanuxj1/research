"""The portal must not present an unmeasured aspect as a measured one.

portal/index.html shows a visitor which categories their review landed in.
Four of the seven have human labels behind them; three do not (see
src/travellens/accuracy.py). The page marks that difference, and the marking
is built from reports/accuracy_all_aspects.json rather than typed into the
template -- so these tests check the two cannot drift apart, and that no
unfilled placeholder ever ships.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import config as C  # noqa: E402

PORTAL = ROOT / "portal"


def _payload(html: str, name: str):
    """Pull one injected JSON payload back out of the built page."""
    m = re.search(r"^const {} *= *(.+);$".format(name), html, re.M)
    assert m, "{} was not injected into the page".format(name)
    return json.loads(m.group(1).replace("\\u003c", "<"))


@pytest.fixture(scope="module")
def built():
    if not (PORTAL / "index.html").exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "45_build_portal.py")],
                       check=True, cwd=str(ROOT))
    return (PORTAL / "index.html").read_text(encoding="utf-8")


def test_no_placeholder_survives(built):
    leftovers = sorted(set(re.findall(r"__[A-Z_]+__", built)))
    assert not leftovers, "unfilled placeholders in the built page: {}".format(
        leftovers)


def test_every_aspect_is_present_and_carries_its_provenance(built):
    aspects = _payload(built, "ASPECTS")
    assert [a["key"] for a in aspects] == list(C.ASPECTS.keys())
    for a in aspects:
        assert "f1" in a, "{} has no provenance field at all".format(a["key"])


def test_provenance_matches_the_accuracy_report(built):
    with open(str(C.REPORTS / "accuracy_all_aspects.json"), encoding="utf-8") as fh:
        report = json.load(fh)
    for a in _payload(built, "ASPECTS"):
        if a["key"] in report["aspects"]:
            assert a["f1"] == report["aspects"][a["key"]]["f1"]
            assert a["human_readers"] == report["aspects"][a["key"]]["human_readers"]
        else:
            assert a["key"] in report["unmeasured"]
            assert a["f1"] is None and a["precision"] is None, (
                "{} is unmeasured in the report but the portal ships a figure "
                "for it -- rebuild with scripts/45_build_portal.py".format(
                    a["key"]))


def test_the_page_warns_where_nothing_has_been_checked(built):
    # "Checked" means PRECISION was measured -- that is what the visitor-facing
    # sentence is built from. Three aspects are measured by the presence sheet,
    # which honestly yields no recall and therefore no F1, so keying this on F1
    # would demand a warning beside a figure that was checked.
    unmeasured = [a for a in _payload(built, "ASPECTS")
                  if a["plain_accuracy"] is None]
    if not unmeasured:
        pytest.skip("every aspect is measured now -- nothing to mark")
    # The renderer decides the wording; this only checks the page is capable of
    # saying it, so the marking cannot be dropped from the template unnoticed.
    assert "not checked" in built
    assert "have not checked" in built
    # And every unchecked aspect must ship without a plain-English accuracy
    # claim, which is the string the visitor actually reads.
    for a in unmeasured:
        assert a["plain_accuracy"] is None, (
            "{} has no human labels but ships an accuracy sentence".format(
                a["key"]))


def test_checked_aspects_ship_a_plain_english_accuracy(built):
    """The visitor-facing sentence is built from precision, not F1.

    Precision answers "when we put this label on a sentence, how often is it
    right?" -- which is the question the sentence claims to answer. F1 mixes
    in recall and cannot be phrased that way.
    """
    for a in _payload(built, "ASPECTS"):
        if a["precision"] is None:
            continue
        assert a["plain_accuracy"], "{} has no plain sentence".format(a["key"])
        expected = int(round(a["precision"] * 10))
        assert "{} times in 10".format(expected) in a["plain_accuracy"]


def test_baseline_rows_carry_their_denominator(built):
    """A complaint rate without n invites 1-of-3 being read as 33%."""
    baseline = _payload(built, "BASELINE")
    assert baseline, "no baseline was embedded"
    for dest, rec in baseline.items():
        assert rec["aspects"], "{} has an empty aspect block".format(dest)
        for key, cell in rec["aspects"].items():
            assert key in C.ASPECTS
            assert cell["n"] > 0, "{}/{} has a rate with no opinions".format(
                dest, key)
            assert 0.0 <= cell["rate"] <= 1.0


def test_districts_are_the_ones_the_api_accepts(built):
    names = [d["name"] for d in _payload(built, "DISTRICTS")]
    assert names == list(C.DISTRICTS), (
        "the portal offers districts POST /analyse would reject")


def test_observation_end_is_stated_not_implied(built):
    meta = _payload(built, "META")
    assert meta["observation_end"], "the historical layer ships undated"
    assert meta["observation_end"] in built
