"""Guards on the single three-tab app.

The system is one page -- Map, Stories & videos, Add a review -- with the map
tab hosting `dashboard/index.html` in a frame. That framing is a deliberate
engineering choice, and these tests hold the two things it depends on.

**The two documents must stay separate.** They share seven CSS class names and
the dashboard styles bare `body`, `table`, `th`, `td`, `button` and `input`.
Inlined into one document each would silently restyle the other. If somebody
later "simplifies" this by pasting the dashboard's markup in, the collision
test below is what says why not.

**The frame must not nest.** The dashboard carries its own link back to the
portal for when it is opened standalone. Inside the map tab that link would
load the whole app into its own map panel.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PORTAL = ROOT / "portal" / "index.html"
DASHBOARD = ROOT / "dashboard" / "index.html"

TABS = ["map", "stories", "share"]


@pytest.fixture(scope="module")
def portal():
    if not PORTAL.exists():
        pytest.skip("run python scripts/45_build_portal.py first")
    return PORTAL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dashboard():
    if not DASHBOARD.exists():
        pytest.skip("run python scripts/08_build_dashboard.py first")
    return DASHBOARD.read_text(encoding="utf-8")


def test_three_tabs_and_three_panels(portal):
    for name in TABS:
        assert 'id="tab-{}"'.format(name) in portal, "no {} tab".format(name)
        assert 'id="panel-{}"'.format(name) in portal, "no {} panel".format(name)


def test_exactly_one_tab_starts_selected(portal):
    selected = re.findall(r'id="tab-(\w+)"[^>]*aria-selected="true"', portal)
    assert selected == ["map"], (
        "expected the map tab selected on load, got {}".format(selected))


def test_the_map_tab_frames_the_dashboard_rather_than_inlining_it(portal):
    assert 'id="map-frame"' in portal
    assert "../dashboard/index.html" in portal
    # The dashboard's payload must not have been pasted in: it is 3.8 MB, and
    # the portal is two orders of magnitude smaller.
    assert len(portal) < 1_500_000, (
        "the portal has grown to {} bytes -- the dashboard looks inlined, "
        "which breaks both stylesheets".format(len(portal)))


def test_the_two_documents_would_collide_if_merged(portal, dashboard):
    """The reason for the frame, asserted rather than left in a comment."""
    def css_classes(doc):
        css = doc.split("</style>")[0]
        return set(re.findall(r"\.([a-zA-Z][\w-]*)\s*[,{ >:]", css))

    shared = css_classes(portal) & css_classes(dashboard)
    assert shared, (
        "the two stylesheets no longer collide -- if that is really true, "
        "inlining becomes possible and this test should be revisited")
    # And the dashboard restyles bare elements the portal's forms rely on.
    dash_css = dashboard.split("</style>")[0]
    bare = [t for t in ("body", "table", "th", "td", "button", "input")
            if re.search(r"^{}\b".format(t), dash_css, re.M)]
    assert bare, "dashboard no longer styles bare elements"


def test_the_frame_loads_only_when_the_tab_is_opened(portal):
    """3.8 MB should not be fetched by tabs that do not show it."""
    frame = re.search(r"<iframe id=\"map-frame\"[^>]*>", portal).group(0)
    assert "src=" not in frame, "the frame ships with a src and loads eagerly"
    assert 'setAttribute("src"' in portal, "nothing ever sets the frame src"


def test_the_dashboard_drops_its_portal_link_when_framed(dashboard):
    assert 'class="to-portal"' in dashboard, "standalone link is gone"
    assert "window.top !== window.self" in dashboard, (
        "nothing detects framing, so the map tab can load the app inside "
        "its own map panel")


def test_the_tab_is_in_the_address_bar(portal):
    """Otherwise a reload silently returns the reader to the first tab."""
    assert "hashchange" in portal
    assert 'history.replaceState' in portal


def test_the_title_names_the_system_not_one_tab(portal):
    title = re.search(r"<title>(.*?)</title>", portal).group(1)
    assert "tell us what you found" not in title.lower(), (
        "the title describes one tab of three")


def test_user_text_cannot_widen_its_container(portal):
    """The bug this guards: a 220-character unbroken word took one story card
    from 467px to 1681px and pushed the whole page 765px wider than the
    viewport, giving it a horizontal scrollbar and shifting the layout.

    Any text a visitor types is rendered somewhere, and a long URL or a pasted
    token has no break opportunity, so the browser widens the container rather
    than wrap.
    """
    css = portal.split("</style>")[0]
    assert "overflow-wrap: anywhere" in css, (
        "nothing forces long words to break")
    for selector in (".story p.body", ".seg-text", ".media-item",
                     ".mine-row .where"):
        assert selector in css, (
            "{} renders user text but is not covered by the wrapping "
            "rule".format(selector))
    # A grid child's default min-width is its content, so wrapping alone does
    # not stop one column blowing out the grid.
    assert ".cols > * { min-width: 0; }" in css


def test_the_map_frame_is_measured_not_guessed(portal):
    """A CSS guess at the header height is wrong as soon as anything wraps,
    and being wrong by any amount puts a second scrollbar beside the
    dashboard's own."""
    assert "function sizeFrame" in portal
    assert "window.scrollY" in portal, (
        "the frame is sized from a viewport-relative top, which is wrong "
        "whenever the page is scrolled -- it produced a frame starting 81px "
        "above the viewport")
    assert 'window.addEventListener("resize", sizeFrame)' in portal


def test_the_dashboard_hides_its_masthead_when_framed(dashboard):
    """Otherwise the map tab shows the brand twice, once above the frame and
    once inside it, and reads as a page embedded in a page."""
    assert 'querySelector(".masthead")' in dashboard
    assert 'data-framed' in dashboard
