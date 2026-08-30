"""Guards on the single-command build and launch.

Two failures this is written against.

**A page older than the tree it renders.** The dashboard is a static file with
the numbers baked in. Rebuild the tree and forget to rebuild the page and it
keeps showing yesterday's figures, looking completely normal while doing it.
Nothing downstream can detect that, so preflight compares the timestamps.

**Serving a write endpoint into the research corpus.** SUBMISSIONS_DATABASE_URL
is set in this repository's .env, and every POST /analyse writes to it. Bound
to loopback that is a deliberate choice; bound to 0.0.0.0 it publishes a write
endpoint into the data the thesis rests on.
"""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import config as C  # noqa: E402
from travellens import launch as L  # noqa: E402


def _by_name(checks):
    return {c.name: c for c in checks}


def test_every_build_step_names_a_script_that_exists():
    for script, what in L.BUILD_STEPS:
        assert (ROOT / "scripts" / script).exists(), (
            "{} is in the build chain but does not exist".format(script))
        assert what, "{} has no description".format(script)


def test_the_build_chain_aggregates_before_it_renders():
    """Order matters: the pages read what aggregation writes."""
    names = [s for s, _ in L.BUILD_STEPS]
    assert names.index("07_aggregate.py") < names.index("08_build_dashboard.py")
    assert names.index("07_aggregate.py") < names.index("45_build_portal.py")
    # And the accuracy report must precede the portal, which embeds it.
    assert names.index("44_accuracy_report.py") < names.index("45_build_portal.py")


def test_preflight_passes_on_the_current_checkout():
    checks = L.preflight()
    failed = [c.name for c in checks if not c.ok and c.fatal]
    assert not failed, "preflight fails here: {}".format(failed)


def test_preflight_catches_a_page_older_than_the_tree(tmp_path, monkeypatch):
    """The silent failure: a stale dashboard looks exactly like a fresh one."""
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    reports = tmp_path / "reports"
    reports.mkdir()
    for name in ("reviews_clean.csv", "segments_scored.csv", "scorecards.csv"):
        (processed / name).write_text("x", encoding="utf-8")
    for page in ("dashboard", "portal"):
        d = tmp_path / page
        d.mkdir()
        (d / "index.html").write_text("<p>old</p>", encoding="utf-8")
    # Timestamps set explicitly rather than relying on write order: on this
    # filesystem several writes can land in the same mtime tick, and the check
    # treats an equal timestamp as fresh (a page rebuilt in the same second as
    # the tree IS current). The case being tested is a page genuinely older.
    (processed / "hierarchy.json").write_text("{}", encoding="utf-8")
    tree_time = 1_800_000_000
    os.utime(processed / "hierarchy.json", (tree_time, tree_time))
    for page in ("dashboard", "portal"):
        os.utime(tmp_path / page / "index.html",
                 (tree_time - 3600, tree_time - 3600))

    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(C, "DATA_PROCESSED", processed)
    monkeypatch.setattr(C, "REPORTS", reports)

    checks = _by_name(L.preflight())
    assert not checks["dashboard is current"].ok
    assert not checks["portal is current"].ok
    assert "OLDER" in checks["dashboard is current"].detail
    assert checks["dashboard is current"].fix


def test_preflight_names_the_command_for_anything_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(C, "DATA_PROCESSED", tmp_path / "nope")
    monkeypatch.setattr(C, "REPORTS", tmp_path / "nope")
    for c in L.preflight():
        if not c.ok:
            assert c.fix, "{} fails with no command to fix it".format(c.name)


def test_serving_the_research_corpus_publicly_is_refused(monkeypatch):
    monkeypatch.setenv("SUBMISSIONS_DATABASE_URL", "postgres://example")
    assert L.serve(host="0.0.0.0", port=0) == 2
    assert L.serve(host="192.168.1.10", port=0) == 2


def test_report_returns_false_when_a_fatal_check_fails():
    checks = [L.Check("fine", True), L.Check("broken", False, fatal=True)]
    assert L.report(checks) is False
    warn_only = [L.Check("fine", True), L.Check("noted", False, fatal=False)]
    assert L.report(warn_only) is True


def test_the_thresholds_check_reads_the_measured_value():
    """It must compare config against reliability.json, not a literal."""
    src = (ROOT / "src" / "travellens" / "launch.py").read_text(encoding="utf-8")
    assert "reliability.json" in src
    assert "MIN_MENTIONS_DISPLAY" in src


@pytest.fixture(scope="module")
def client():
    os.environ["SUBMISSIONS_DATABASE_URL"] = ""
    from fastapi.testclient import TestClient
    from travellens.api import app
    return TestClient(app)


def test_one_port_serves_both_pages_and_the_api(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (307, 302)
    assert r.headers["location"] == "/portal/index.html"

    for path in ("/portal/index.html", "/dashboard/index.html"):
        page = client.get(path)
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assert len(page.content) > 1000

    # And the pages must not have shadowed the API.
    assert client.get("/health").status_code == 200
    assert client.get("/aspects").json()["aspects"]


def test_pages_are_served_uncached(client):
    """Both files are rebuilt in place under the same URL, so a cached copy is
    indistinguishable from a rebuild that did not happen.

    no-store rather than no-cache: the weaker header only asks for
    revalidation, and was observed still serving a previous build after a
    rebuild.
    """
    for path in ("/dashboard/index.html", "/portal/index.html"):
        cc = client.get(path).headers.get("cache-control", "")
        assert "no-store" in cc, "{} may be cached: {!r}".format(path, cc)


def test_a_missing_page_answers_with_the_command_that_builds_it(monkeypatch):
    from travellens import api
    monkeypatch.setitem(api._PAGES, "portal", Path("does/not/exist.html"))
    from fastapi.testclient import TestClient
    r = TestClient(api.app).get("/portal/index.html")
    assert r.status_code == 503
    assert "45_build_portal.py" in r.text
