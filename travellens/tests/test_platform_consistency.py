"""The Reviews component must agree with itself and look like the rest of the platform.

1. /corpus-summary (the portal's Analytics tab and ReviewsPanel.jsx) once recounted
   the corpus without the per-aspect correction chain and showed safety at 60.2%
   beside the dashboard's 69.8%. It now reads hierarchy.json; this holds it there.
2. The pages carry the shared platform theme (scripts/60_apply_platform_theme.py):
   Inter instead of serif/monospace, emerald actions, navy + gold brand bar.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import config as C  # noqa: E402

HIER = C.DATA_PROCESSED / "hierarchy.json"
PAGES = [ROOT / "portal" / "index.html", ROOT / "portal" / "template.html",
         ROOT / "dashboard" / "index.html", ROOT / "dashboard" / "template.html"]


@pytest.mark.skipif(not HIER.exists(), reason="pipeline outputs not present in this checkout")
def test_analytics_rates_are_the_dashboard_rates():
    from travellens.api import _build_corpus_summary, _HIER_KEY
    h = json.loads(HIER.read_text(encoding="utf8"))
    got = _build_corpus_summary()
    for a in got["aspects"]:
        want = round(100 * h["aspects"][_HIER_KEY.get(a["key"], a["key"])]["complaint_rate"], 1)
        assert a["complaint_rate"] == want, a["key"]
    assert got["destinations"] == h["coverage"]["n_destinations"]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: "%s/%s" % (p.parent.name, p.name))
def test_page_carries_the_platform_theme(page):
    s = page.read_text(encoding="utf8")
    assert s.count("/* platform-theme:start */") == 1
    theme = s[s.index("/* platform-theme:start */"):s.index("/* platform-theme:end */")]
    for token in ('--f-display: "Inter"', '--f-mono:    "Inter"', "--accent-fill: #059669",
                  "--brand-ink: #0D1B2A", "--brand-gold: #E8B84B"):
        assert token in theme, token
    # the theme must come after the original rules, or they would win
    first_style_end = s.index("</style>")
    assert s.index("/* platform-theme:end */") < first_style_end
    assert "classList.add('embedded')" in s
