"""submissions_db.py: the SQLite path, and the parts of the Postgres path
that don't require a live database.

A real Neon connection is not available in CI or on a machine without
SUBMISSIONS_DATABASE_URL set, so a live round trip against Postgres itself
is not exercised here. What IS tested without one:

  - placeholder translation against api.py's ACTUAL queries, not
    hypothetical ones, because a query added later with a literal "?" in a
    string value would defeat the blind regex substitution
  - _Row, in isolation, against every access style api.py actually uses

_Row exists because of a real bug this project shipped: the first version
of the Postgres path used psycopg2.extras.RealDictCursor, whose rows are
plain dicts with string keys only. api.py has seven call sites written as
`.fetchone()[0]` -- exactly how sqlite3.Row is meant to be read, since it
supports both positional and named access -- and every one of them raised
`KeyError: 0` against a dict row. Every database-touching endpoint 500'd on
Postgres until a QA pass caught it by actually calling the running server;
SQLite's own Row silently supports both styles, so nothing local ever
exercised the difference. These tests exist so that gap cannot reopen
silently.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from travellens import submissions_db as db  # noqa: E402


class _FakeCursor:
    """Just enough psycopg2 cursor for _checkout()'s SELECT 1 probe."""

    def __init__(self, alive=True):
        self._alive = alive

    def execute(self, sql, params=()):
        if not self._alive:
            raise OSError("server closed the connection unexpectedly")

    def fetchone(self):
        return (1,)

    def close(self):
        pass


class _FakeRaw:
    """A stand-in psycopg2 connection. `alive=False` models the case this
    exists for: Neon dropped the socket while the connection sat in the pool,
    and the pool has no idea."""

    def __init__(self, alive=True):
        self.alive = alive
        self.autocommit = False
        self.closed = False

    def cursor(self):
        return _FakeCursor(self.alive)

    def commit(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def sqlite_env(tmp_path, monkeypatch):
    """A throwaway SQLite file, and SUBMISSIONS_DATABASE_URL unset."""
    monkeypatch.delenv(db.ENV_VAR, raising=False)
    monkeypatch.setattr(db, "SUBMISSIONS_DB", tmp_path / "test_submissions.db")
    yield


def test_default_backend_is_sqlite(sqlite_env):
    assert db.active_backend() == "sqlite"


def test_sqlite_round_trip(sqlite_env):
    """The exact sequence api.py's /analyse endpoint runs: two inserts, a
    commit, then a read back -- proves the schema and the connection object
    behave the way api.py's call sites expect."""
    con = db.get_connection()
    con.execute(
        "INSERT INTO user_reviews "
        "(review_id, destination, district, raw_text, source, submitted_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("r1", "Kandy Lake", "Kandy", "Nice place.", "user_submission",
         "2026-08-27T00:00:00+00:00"),
    )
    con.execute(
        "INSERT INTO user_segments "
        "(review_id, seg_index, segment_text, aspects, polarity, "
        " polarity_score, triggered_words) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("r1", 0, "Nice place.", "[]", "X", 0.0, "[]"),
    )
    con.commit()

    row = con.execute(
        "SELECT * FROM user_reviews WHERE review_id = ?", ("r1",)
    ).fetchone()
    con.close()

    assert row["destination"] == "Kandy Lake"
    assert dict(row)["district"] == "Kandy"       # dict-like access, both ways


def test_schema_is_idempotent(sqlite_env):
    """get_connection() runs the schema on every call for SQLite (matching
    what api.py did before this module existed) -- must not error on a
    table that already exists."""
    db.get_connection().close()
    db.get_connection().close()   # would raise if CREATE TABLE lacked IF NOT EXISTS


# --------------------------------------------------------------------------
# Placeholder translation, checked against api.py's REAL queries.
# --------------------------------------------------------------------------
def _queries_from_api_source():
    """Pull every literal SQL string passed to con.execute(...) out of
    api.py, so this test tracks the real call sites rather than a
    hand-copied list that could drift out of sync with them."""
    src = (ROOT / "src" / "travellens" / "api.py").read_text(encoding="utf-8")
    # Concatenated adjacent string literals inside con.execute("...", ...)
    # -- good enough for this file's straightforward call sites.
    calls = re.findall(r'con\.execute\(\s*((?:"[^"]*"\s*)+)', src)
    queries = []
    for c in calls:
        pieces = re.findall(r'"([^"]*)"', c)
        queries.append("".join(pieces))
    return queries


def test_no_query_contains_a_literal_question_mark_in_a_value():
    """The regex substitution in _PgConnection.execute() replaces EVERY '?'
    with '%s', with no awareness of string literals. That is only safe
    because none of api.py's queries has a literal '?' inside a quoted SQL
    string value (as opposed to as a placeholder). This is the test that
    would fail the day someone adds one."""
    queries = _queries_from_api_source()
    assert queries, "no con.execute(...) calls found -- source pattern changed"
    for q in queries:
        # Every '?' in a real query is a placeholder token, "?", surrounded
        # by punctuation/whitespow -- not embedded in a word or quote.
        for m in re.finditer(r"\?", q):
            before = q[max(0, m.start() - 1):m.start()]
            after = q[m.end():m.end() + 1]
            assert before in ("", " ", "(", ","), (q, before)
            assert after in ("", " ", ")", ","), (q, after)


def test_placeholder_translation_matches_param_count():
    """For every real query, the number of '?' placeholders equals the
    number of '%s' after translation -- i.e. the substitution changes
    nothing else about the query."""
    queries = _queries_from_api_source()
    for q in queries:
        n_q = q.count("?")
        translated = db._PLACEHOLDER_RE.sub("%s", q)
        assert translated.count("%s") == n_q
        assert "?" not in translated


def test_postgres_path_refuses_without_the_driver(monkeypatch):
    """If SUBMISSIONS_DATABASE_URL is set but psycopg2 is not installed,
    fail loudly at connection time -- not by silently falling back to
    SQLite, which would put a hosted deploy's data on a filesystem that
    does not survive a restart without anyone noticing."""
    monkeypatch.setenv(db.ENV_VAR, "postgresql://example/db")
    monkeypatch.setattr(db, "_pg_driver_available", lambda: False)
    with pytest.raises(RuntimeError, match="psycopg2"):
        db.get_connection()


def test_dsn_is_never_logged(sqlite_env, monkeypatch, capsys):
    """A Postgres DSN carries a password. Only the fact that Postgres is
    active may reach stdout, never the string itself."""
    secret_dsn = "postgresql://realuser:supersecretpassword@example.neon.tech/db"
    monkeypatch.setenv(db.ENV_VAR, secret_dsn)
    monkeypatch.setattr(db, "_pg_driver_available", lambda: True)
    monkeypatch.setattr(db, "_backend_logged", False)
    monkeypatch.setattr(db, "_schema_ensured", True)  # skip real DDL

    class _FakeCon:
        def executescript(self, sql):
            pass

    class _FakePool:
        def getconn(self):
            # _checkout() probes the connection with SELECT 1 before handing
            # it over, so the stand-in has to answer that much.
            return _FakeRaw()

        def putconn(self, raw, close=False):
            pass

    # get_connection() now goes through _get_pool(dsn) -> _checkout(pool) ->
    # _PgConnection(raw, pool). Faking both keeps this test from opening a
    # real network connection to a DSN that does not exist.
    monkeypatch.setattr(db, "_get_pool", lambda dsn: _FakePool())
    monkeypatch.setattr(db, "_PgConnection", lambda raw, pool=None: _FakeCon())

    db.get_connection()
    out = capsys.readouterr().out
    assert "supersecretpassword" not in out
    assert secret_dsn not in out


# --------------------------------------------------------------------------
# _Row -- every access style api.py actually uses, against every one of
# api.py's real .fetchone()[0]-shaped queries.
# --------------------------------------------------------------------------
def test_row_positional_access_matches_sqlite_row():
    """The exact bug: .fetchone()[0] on a COUNT(*) query."""
    row = db._Row(["id", "district"], (7, "Kandy"))
    assert row[0] == 7
    assert row[1] == "Kandy"


def test_row_named_access():
    row = db._Row(["id", "district"], (7, "Kandy"))
    assert row["district"] == "Kandy"
    assert row["id"] == 7


def test_row_dict_conversion():
    row = db._Row(["id", "district"], (7, "Kandy"))
    assert dict(row) == {"id": 7, "district": "Kandy"}


def test_row_supports_both_styles_on_the_same_row():
    """Not one or the other -- api.py's 20-odd call sites use a mix, often
    on the very same query result."""
    row = db._Row(["review_id", "destination", "district"],
                  ("r1", "Kandy Lake", "Kandy"))
    assert row[0] == "r1"
    assert row["destination"] == "Kandy Lake"
    assert dict(row)["district"] == "Kandy"


def _count_star_queries_from_api_source():
    """Every literal query in api.py shaped like the one that broke:
    SELECT COUNT(*) ... .fetchone()[0]. Tracks the real call sites rather
    than a hand-copied list."""
    src = (ROOT / "src" / "travellens" / "api.py").read_text(encoding="utf-8")
    calls = re.findall(
        r'con\.execute\(\s*((?:"[^"]*"\s*)+)[^)]*\)\.fetchone\(\)\[0\]', src)
    return ["".join(re.findall(r'"([^"]*)"', c)) for c in calls]


def test_every_fetchone_zero_call_site_is_a_single_column_query():
    """.fetchone()[0] only makes sense if the query selects exactly one
    column (typically COUNT(*)). If a future query selected more than one
    column and still used [0], that would silently read the wrong thing on
    both backends alike -- not a Postgres-specific bug, but this is the
    natural place to guard it since it inspects the same call sites."""
    queries = _count_star_queries_from_api_source()
    assert queries, "no .fetchone()[0] call sites found -- source pattern changed"
    for q in queries:
        assert q.strip().upper().startswith("SELECT COUNT("), q


# --------------------------------------------------------------------------
# Connection pooling: opening a fresh psycopg2.connect(dsn) per request
# measured a consistent ~3s -- checked across three back-to-back calls, so
# it was the real handshake cost every time, not a one-off cold start. Every
# database-touching endpoint paid that before pooling existed.
# --------------------------------------------------------------------------
class _FakeRawConnection:
    """Stands in for a real psycopg2 connection: records whether autocommit
    was set and whether close() vs a pool return happened."""
    def __init__(self):
        self.autocommit = False
        self.closed_for_real = False
        self.committed = False

    def cursor(self):
        class _Cur:
            description = []
            def execute(self, *a, **kw): pass
            def fetchone(self): return None
            def fetchall(self): return []
        return _Cur()

    def commit(self):
        self.committed = True

    def close(self):
        self.closed_for_real = True


class _FakePool:
    def __init__(self):
        self.returned = []

    def getconn(self):
        return _FakeRawConnection()

    def putconn(self, con):
        self.returned.append(con)


def test_pooled_connection_is_set_to_autocommit():
    """Without this, a read-only request (which never calls .commit()) would
    leave an open transaction on a connection that then goes back into the
    pool for the NEXT request to inherit -- a stale snapshot at best."""
    raw = _FakeRawConnection()
    db._PgConnection(raw, pool=_FakePool())
    assert raw.autocommit is True


def test_closing_a_pooled_connection_returns_it_rather_than_closing_the_socket():
    pool = _FakePool()
    raw = _FakeRawConnection()
    con = db._PgConnection(raw, pool=pool)
    con.close()
    assert raw.closed_for_real is False
    assert pool.returned == [raw]


def test_closing_an_unpooled_connection_still_closes_it():
    """The pool argument is optional -- a direct _PgConnection(raw) with no
    pool (e.g. if pooling is ever bypassed) must still tear the socket down
    rather than leaking it."""
    raw = _FakeRawConnection()
    con = db._PgConnection(raw, pool=None)
    con.close()
    assert raw.closed_for_real is True


def test_get_pool_is_created_once_and_reused(monkeypatch):
    """A pool created fresh on every call would defeat the entire point --
    it would just move the ~3s handshake cost from 'per request' to 'per
    call to _get_pool', which is the same place if get_connection() calls it
    every time. This pins that _pg_pool is a real module-level singleton."""
    monkeypatch.setattr(db, "_pg_pool", None)
    calls = []

    class _Recording(_FakePool):
        pass

    def fake_threaded_pool(minc, maxc, dsn):
        calls.append(dsn)
        return _Recording()

    import sys
    import types
    fake_pool_module = types.SimpleNamespace(ThreadedConnectionPool=fake_threaded_pool)
    monkeypatch.setitem(sys.modules, "psycopg2.pool", fake_pool_module)

    p1 = db._get_pool("postgresql://example/db")
    p2 = db._get_pool("postgresql://example/db")
    assert p1 is p2
    assert len(calls) == 1


# --------------------------------------------------------------------------
# connection(): the leak that emptied the pool
#
# api.py's endpoints used to call get_connection() and then close() on the
# happy path -- inside the try in /analyse, after the query on the read
# endpoints. A query that raised skipped the close. Against SQLite that leaks
# nothing anyone notices; on the pooled Postgres backend close() IS
# putconn(), so each failed request permanently removed one connection from a
# pool of five, and the fifth failure wedged the process.
# --------------------------------------------------------------------------
def test_connection_is_returned_when_the_block_succeeds(sqlite_env):
    with db.connection() as con:
        con.execute("SELECT 1")
    # sqlite3 raises on a closed connection; that is the observable proof.
    with pytest.raises(Exception):
        con.execute("SELECT 1")


def test_connection_is_returned_when_the_query_raises(monkeypatch):
    """The whole point. A failing query must not cost a connection."""
    closed = []

    class _Failing:
        def execute(self, sql, params=()):
            raise RuntimeError("simulated: connection dropped mid-query")

        def close(self):
            closed.append(1)

    monkeypatch.setattr(db, "get_connection", lambda: _Failing())

    with pytest.raises(RuntimeError):
        with db.connection() as con:
            con.execute("SELECT 1")

    assert closed == [1], "the connection must be given back even on failure"


def test_a_failed_schema_check_returns_the_connection(monkeypatch):
    """get_connection()'s own DDL had the same gap: the connection was
    checked out before executescript() and lost if that raised."""
    raw = _FakeRaw()
    returned = []

    class _Pool:
        def getconn(self):
            return raw

        def putconn(self, con, close=False):
            returned.append(con)

    monkeypatch.setenv(db.ENV_VAR, "postgresql://u:p@example.neon.tech/db")
    monkeypatch.setattr(db, "_pg_driver_available", lambda: True)
    monkeypatch.setattr(db, "_get_pool", lambda dsn: _Pool())
    monkeypatch.setattr(db, "_schema_ensured", False)
    monkeypatch.setattr(db, "_backend_logged", True)

    def _boom(self, sql):
        raise RuntimeError("DDL failed")

    monkeypatch.setattr(db._PgConnection, "executescript", _boom)

    with pytest.raises(RuntimeError):
        db.get_connection()

    assert returned == [raw], "a failed schema check must not eat a connection"


# --------------------------------------------------------------------------
# _checkout(): the stale connection Neon hands back after an idle period
# --------------------------------------------------------------------------
def test_a_dead_pooled_connection_is_discarded_and_retried(monkeypatch):
    """Observed against the running server: the first request after roughly
    25 minutes idle returned a 500, and an immediate retry of the same URL
    succeeded. Neon closes connections when a free-tier project scales to
    zero; psycopg2's pool does not check before handing one over."""
    dead, alive = _FakeRaw(alive=False), _FakeRaw(alive=True)
    handed_out, discarded = [dead, alive], []

    class _Pool:
        def getconn(self):
            return handed_out.pop(0)

        def putconn(self, con, close=False):
            if close:
                discarded.append(con)

    con = db._checkout(_Pool())

    assert discarded == [dead], "the dead connection must not go back in the pool"
    assert con._con is alive
    assert alive.autocommit is True


def test_checkout_gives_up_rather_than_looping_forever(monkeypatch):
    class _Pool:
        def getconn(self):
            return _FakeRaw(alive=False)

        def putconn(self, con, close=False):
            pass

    with pytest.raises(RuntimeError, match="live Postgres connection"):
        db._checkout(_Pool(), attempts=2)


# --------------------------------------------------------------------------
# Schema migration: CREATE TABLE IF NOT EXISTS cannot add a column
# --------------------------------------------------------------------------
def test_aspect_polarity_is_added_to_a_pre_existing_table(sqlite_env):
    """A database created before per-aspect scoring must gain the column.

    IF NOT EXISTS is a no-op on a table that already exists, so without an
    explicit migration the new column never reaches an older file and every
    INSERT naming it fails.
    """
    import sqlite3

    old_schema = """
        CREATE TABLE user_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, review_id TEXT UNIQUE NOT NULL,
            destination TEXT NOT NULL, district TEXT NOT NULL,
            raw_text TEXT NOT NULL, source TEXT NOT NULL, submitted_at TEXT NOT NULL);
        CREATE TABLE user_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, review_id TEXT NOT NULL,
            seg_index INTEGER NOT NULL, segment_text TEXT NOT NULL,
            aspects TEXT NOT NULL, polarity TEXT NOT NULL,
            polarity_score REAL NOT NULL, triggered_words TEXT NOT NULL);
    """
    pre = sqlite3.connect(str(db.SUBMISSIONS_DB))
    pre.executescript(old_schema)
    pre.commit()
    pre.close()

    with db.connection() as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(user_segments)")}

    assert "aspect_polarity" in cols
