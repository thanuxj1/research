"""Build the whole system, check it, and run it.

Why this exists
---------------
This project grew to 56 numbered scripts, and knowing which of them matter --
and in what order -- was knowledge that lived in one person's head. Handing it
to anybody else meant handing over that knowledge too. Worse, the running
system was three processes: this API, a static server for the dashboard, and
another for the portal. The portal calls the API, so a reader who opened the
file directly got a page that looked finished and did nothing.

Two commands now:

    python scripts/49_build_all.py     rebuild every artefact, in order
    python scripts/50_launch.py        check it, then serve it on one port

Neither replaces the numbered scripts. They call them, so there is still
exactly one implementation of each stage, and anything that goes wrong can be
re-run on its own.

What preflight refuses to do
----------------------------
It does not fix anything, and it does not start a server it knows is broken.
The failure this guards against is specific: a dashboard built from a stale
tree, or a portal shipping "not checked" beside figures that were checked,
looks completely normal on screen. Every check below compares two things that
must agree and says which command reconciles them -- so a wrong state is loud
at start-up rather than silent in a published figure.

It also refuses, loudly, to serve while pointed at the hosted research corpus
with a public bind address. That is not a hypothetical: SUBMISSIONS_DATABASE_URL
is set in .env for this repository, and every /analyse call writes to it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from . import config as C

DEFAULT_PORT = 8778

# The build chain, in dependency order. Each is the numbered script that
# already owns that stage.
BUILD_STEPS: List[Tuple[str, str]] = [
    ("07_aggregate.py", "aggregate the corpus into the tree and scorecards"),
    ("33_ablate_rules.py", "rule sensitivity"),
    ("34_external_validity.py", "corroboration against public star ratings"),
    ("39_agreement.py", "inter-annotator agreement"),
    ("38_evaluate_against_gold.py", "aspect extraction vs the gold set"),
    ("43_evaluate_polarity.py", "polarity accuracy"),
    ("44_accuracy_report.py", "assemble the published accuracy report"),
    ("46_reliability.py", "split-half reliability of the published rates"),
    ("08_build_dashboard.py", "build the dashboard"),
    ("45_build_portal.py", "build the portal"),
]


class Check:
    __slots__ = ("name", "ok", "detail", "fix", "fatal")

    def __init__(self, name: str, ok: bool, detail: str = "",
                 fix: str = "", fatal: bool = True):
        self.name, self.ok = name, ok
        self.detail, self.fix, self.fatal = detail, fix, fatal


def _mtime(path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _read_json(path):
    try:
        with open(str(path), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def preflight() -> List[Check]:
    """Everything that must be true before this is worth serving."""
    checks: List[Check] = []
    P, R = C.DATA_PROCESSED, C.REPORTS

    # -- the artefacts exist -------------------------------------------
    for label, path, fix in (
        ("corpus", P / "reviews_clean.csv", "python scripts/01_clean.py"),
        ("scored segments", P / "segments_scored.csv", "python scripts/10_refresh.py"),
        ("tree", P / "hierarchy.json", "python scripts/07_aggregate.py"),
        ("scorecards", P / "scorecards.csv", "python scripts/07_aggregate.py"),
        ("dashboard", C.ROOT / "dashboard" / "index.html",
         "python scripts/08_build_dashboard.py"),
        ("portal", C.ROOT / "portal" / "index.html",
         "python scripts/45_build_portal.py"),
    ):
        checks.append(Check(label, path.exists(),
                            str(path) if path.exists() else "missing", fix))

    # -- the built pages are not older than the tree they render -------
    # A dashboard built before the last aggregation shows yesterday's numbers
    # and looks entirely normal doing it.
    tree_t = _mtime(P / "hierarchy.json")
    for label, path, fix in (
        ("dashboard is current", C.ROOT / "dashboard" / "index.html",
         "python scripts/08_build_dashboard.py"),
        ("portal is current", C.ROOT / "portal" / "index.html",
         "python scripts/45_build_portal.py"),
    ):
        page_t = _mtime(path)
        if tree_t is None or page_t is None:
            checks.append(Check(label, False, "cannot compare", fix))
        else:
            fresh = page_t >= tree_t
            checks.append(Check(
                label, fresh,
                "built after the tree" if fresh else
                "OLDER than hierarchy.json -- it is showing stale numbers", fix))

    # -- the published thresholds match the ones measured --------------
    rel = _read_json(R / "reliability.json")
    if rel is None:
        checks.append(Check("thresholds measured", False,
                            "reports/reliability.json missing",
                            "python scripts/46_reliability.py"))
    else:
        want = rel.get("thresholds", {}).get("acceptable_at_or_above")
        have = C.MIN_MENTIONS_DISPLAY
        ok = want is None or have >= want
        checks.append(Check(
            "evidence threshold", ok,
            "suppress below {} (reliability says {} or more)".format(have, want),
            "raise MIN_MENTIONS_DISPLAY in config.py, then rebuild"))

    # -- no aspect publishes a figure without labels -------------------
    acc = _read_json(R / "accuracy_all_aspects.json")
    if acc is None:
        checks.append(Check("accuracy report", False, "missing",
                            "python scripts/44_accuracy_report.py"))
    else:
        measured = acc.get("aspects") or {}
        unmeasured = acc.get("unmeasured") or {}
        checks.append(Check(
            "accuracy coverage", True,
            "{} of {} aspects measured{}".format(
                len(measured), len(measured) + len(unmeasured),
                "" if not unmeasured else
                " -- {} still unmeasured".format(", ".join(sorted(unmeasured)))),
            "python scripts/47_polarity_sheet.py", fatal=False))
        bad = [k for k, v in measured.items() if v.get("precision") is None]
        checks.append(Check("every published aspect has a figure", not bad,
                            "missing precision: {}".format(bad) if bad else "ok",
                            "python scripts/44_accuracy_report.py"))

    # -- where submissions go ------------------------------------------
    dsn = os.environ.get("SUBMISSIONS_DATABASE_URL") or ""
    if dsn:
        checks.append(Check(
            "submission store", True,
            "Postgres -- THE HOSTED RESEARCH CORPUS. Every /analyse writes to "
            "it.", "unset SUBMISSIONS_DATABASE_URL to use local SQLite",
            fatal=False))
    else:
        checks.append(Check("submission store", True,
                            "local SQLite ({})".format("user_submissions.db"),
                            "", fatal=False))
    return checks


def report(checks: List[Check]) -> bool:
    print("\npreflight")
    print("-" * 68)
    for c in checks:
        mark = "  ok  " if c.ok else ("FAIL  " if c.fatal else "warn  ")
        print("{}{:<32} {}".format(mark, c.name, c.detail))
        if not c.ok and c.fix:
            print("      -> {}".format(c.fix))
    failed = [c for c in checks if not c.ok and c.fatal]
    print("-" * 68)
    if failed:
        print("{} check(s) failed. Nothing served.".format(len(failed)))
    return not failed


def build(only: Optional[str] = None) -> int:
    """Run the build chain, stopping at the first failure."""
    print("\nLostinSriLanka -- full build\n" + "=" * 68)
    started = datetime.now(timezone.utc)
    steps = [s for s in BUILD_STEPS if only is None or only in s[0]]
    if not steps:
        print("no step matches {!r}".format(only))
        return 1

    for i, (script, what) in enumerate(steps, 1):
        path = C.ROOT / "scripts" / script
        if not path.exists():
            print("\n[{}/{}] {} -- MISSING, skipped".format(i, len(steps), script))
            continue
        print("\n[{}/{}] {}  ({})".format(i, len(steps), script, what))
        sys.stdout.flush()
        # Inherit stdio: each stage already prints what it did, and hiding that
        # behind a spinner would remove the only record of what was rebuilt.
        rc = subprocess.call([sys.executable, str(path)], cwd=str(C.ROOT))
        if rc != 0:
            print("\n{} exited {}. Build stopped -- later stages read what it "
                  "writes, so continuing would build on a stale file.".format(
                      script, rc))
            return rc

    mins = (datetime.now(timezone.utc) - started).total_seconds() / 60.0
    print("\n" + "=" * 68)
    print("build complete in {:.1f} min".format(mins))
    print("next:  python scripts/50_launch.py")
    return 0


def serve(port: int = DEFAULT_PORT, host: str = "127.0.0.1",
          skip_checks: bool = False) -> int:
    checks = preflight()
    if not skip_checks and not report(checks):
        print("\nRun `python scripts/49_build_all.py` to rebuild everything, "
              "or fix the items above individually.")
        return 1
    if skip_checks:
        report(checks)
        print("\n--force: starting despite the above.")

    # Writing submissions to the hosted research corpus from a publicly bound
    # port is the one combination worth refusing outright. Either alone is a
    # deliberate choice; together they publish a write endpoint into the data
    # the thesis is built from.
    if os.environ.get("SUBMISSIONS_DATABASE_URL") and host not in (
            "127.0.0.1", "localhost"):
        print("\nREFUSED: SUBMISSIONS_DATABASE_URL is set (writes go to the "
              "hosted research corpus) and the host is {}, which is not "
              "loopback.\nEither unset the variable or bind to 127.0.0.1."
              .format(host))
        return 2

    import uvicorn
    print("\nLostinSriLanka is running")
    print("-" * 68)
    print("  portal     http://localhost:{}/".format(port))
    print("  dashboard  http://localhost:{}/dashboard".format(port))
    print("  API docs   http://localhost:{}/docs".format(port))
    print("-" * 68)
    print("  one process, one port. Ctrl-C to stop.\n")
    sys.stdout.flush()
    uvicorn.run("travellens.api:app", host=host, port=port, log_level="info")
    return 0
