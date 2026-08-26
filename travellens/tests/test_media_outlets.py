"""
Guard tests: the storyboard must not claim sourcing it does not have.

The panel used to tell the reader that news was "restricted to established Sri
Lankan outlets". It never was -- the targeted collector runs in 'any_named'
mode, and an article about the National Maritime Museum in GREENWICH was
displayed under a museum in Galle. A stated method the artefact does not
follow is worse than a loose method stated plainly, so foreign coverage is now
marked rather than hidden, and these tests fail if either half of that
arrangement is lost.

Run:  python -m pytest tests/test_media_outlets.py -q
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens.media import (CREDIBLE_NEWS_DOMAINS,  # noqa: E402
                              identifying_tokens, is_sri_lankan_outlet,
                              supports_destination)

TEMPLATE = (ROOT / "dashboard" / "template.html").read_text(encoding="utf-8")


def test_local_outlets_are_recognised():
    """Including the name forms Google News actually returns."""
    for name in ["The Sunday Times, Sri Lanka", "Daily Mirror - Sri Lanka",
                 "Island.lk", "Ada Derana", "dailynews.lk", "The Morning",
                 "Sri Lanka Mirror", "EconomyNext", "Daily FT"]:
        assert is_sri_lankan_outlet(name), name


def test_foreign_outlets_are_not_claimed_as_local():
    """The ones that put a London museum on a Galle destination."""
    for name in ["Royal Museums Greenwich", "Mongabay", "Time Out Worldwide",
                 "Xinhua", "Atlas Obscura", "The Times of India",
                 "chinadailyhk", "IDN-InDepthNews"]:
        assert not is_sri_lankan_outlet(name), name


def test_every_curated_outlet_passes_its_own_check():
    """The hand-picked list must never be classified as foreign."""
    for display_name in CREDIBLE_NEWS_DOMAINS.values():
        assert is_sri_lankan_outlet(display_name), display_name


def test_an_unattributed_item_is_never_treated_as_local():
    """Absence of a publisher is not evidence of a local one."""
    for empty in ["", None, "   "]:
        assert not is_sri_lankan_outlet(empty)


def test_the_false_sourcing_claim_is_gone():
    """The specific sentence that the data did not support."""
    assert "restricted to" not in TEMPLATE or \
        "established Sri Lankan outlets" not in TEMPLATE, \
        "the storyboard still claims local-only sourcing"


def test_the_interface_explains_the_marking():
    """A badge nobody can interpret is not a disclosure."""
    assert "non-local source" in TEMPLATE
    assert "story-foreign" in TEMPLATE, "the marker has no style hook"
    assert "not recognisably Sri Lankan" in TEMPLATE, \
        "the note no longer tells the reader what the marker means"


# --------------------------------------------------------------------------
# Relevance: is the item actually about the destination it is filed under?
# --------------------------------------------------------------------------
# The three cards that were displayed under the Galle Maritime Museum. Each
# fails for a different reason, and all three passed every earlier check.
GALLE_MUSEUM_FALSE_POSITIVES = [
    "Journeys from Danger: refugee 'narrative maps' - Royal Museums Greenwich",
    "Sri Lanka Is the Crucial Hub of the Ancient Maritime Silk Road",
    "New venue showcases China's marine heritage - chinadailyhk",
]


def test_the_galle_museum_false_positives_are_rejected():
    """A London museum, a trade route, and a museum in China."""
    for title in GALLE_MUSEUM_FALSE_POSITIVES:
        assert not supports_destination("Maritime Museum", title), title


def test_a_generic_name_needs_its_full_name_present():
    """'maritime' alone must never be enough; 'Maritime Museum' is."""
    assert not supports_destination("Maritime Museum", "Ancient Maritime routes")
    assert supports_destination(
        "Maritime Museum", "Galle Maritime Museum reopens after restoration")


def test_the_article_the_project_wanted_kept_survives():
    """collect_news_targeted.py's docstring defends exactly this headline."""
    assert supports_destination(
        "Horton Plains National Park",
        "Clarion call to protect vulnerable Horton Plains NP - The Sunday Times")


def test_merely_naming_the_region_is_not_enough():
    """An article about the highlands is not an article about the park."""
    assert not supports_destination(
        "Horton Plains National Park",
        "Birdwatching in the highlands of Sri Lanka")
    assert not supports_destination(
        "Moon plains", "The Top Things To See And Do In Nuwara Eliya")


def test_single_word_destinations_are_not_penalised():
    """'Riverston' is its own full name, so the stricter test is the same test."""
    assert supports_destination(
        "Riverston", "Landslides reported in Riverston - Ada Derana")
    assert not supports_destination("Riverston", "Landslides reported in Kandy")


def test_feature_nouns_never_identify_a_place_alone():
    """Matching on 'beach' or 'temple' would attach an item to dozens."""
    for name in ("Jungle Beach", "Gangaramaya (Vihara) Buddhist Temple"):
        for tok in identifying_tokens(name):
            assert tok not in {"beach", "temple", "museum", "falls", "park"}
    assert not supports_destination("Jungle Beach", "Sri Lanka's best beach")


def test_the_hint_is_no_longer_trusted_blindly():
    """normalise() must verify a searched-for destination, not assume it."""
    src = (ROOT / "src" / "travellens" / "media.py").read_text(encoding="utf-8")
    assert "supports_destination(hint" in src, \
        "a destination_hint is being trusted without checking the text"


# --------------------------------------------------------------------------
# 3D terrain map
# --------------------------------------------------------------------------
def test_the_map_needs_no_tile_server_or_key():
    """The dashboard must keep working with no network at all.

    pipeline.py's case for a static rebuild -- "A static rebuild cannot be
    'down'" -- is void if the map fetches tiles from somebody else's CDN, or
    if an API key has to ship inside a file that gets handed around.
    """
    for host in ("maps.googleapis.com", "api.mapbox.com", "tile.openstreetmap.org",
                 "basemaps.cartocdn.com", "maptiler.com", "unpkg.com", "cdn.jsdelivr.net"):
        assert host not in TEMPLATE, "the map reaches out to " + host
    assert "AIza" not in TEMPLATE, "an API key is embedded in the template"


def test_relief_exaggeration_is_disclosed():
    """Every 3D map exaggerates height. This one has to say so."""
    assert "var RELIEF" in TEMPLATE
    assert "exaggerated" in TEMPLATE


def test_no_data_districts_are_hatched_not_shaded():
    """Pale would read as 'few complaints'; the truth is 'never measured'."""
    assert "diagonal hatch = no reviews collected" in TEMPLATE
    assert "never shaded pale" in TEMPLATE


def test_the_two_map_views_agree_about_what_is_clickable():
    """A district with no reviews cannot be opened in either view."""
    assert 'h.hasData ? "pointer" : "not-allowed"' in TEMPLATE


def test_reduced_motion_is_honoured():
    """Spin and fly-to are animation; a reader who opted out gets neither."""
    assert "reduceMotion" in TEMPLATE
    assert "prefers-reduced-motion" in TEMPLATE
