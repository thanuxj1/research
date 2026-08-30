"""
Storage for user-submitted reviews -- the only database this project writes
to at request time. Everything else (travellens.db, hierarchy.json,
scorecards.csv) is built once by the batch pipeline and is read-only from
the API's perspective, and none of that moves.

Why this file exists
---------------------
SQLite is a single file on disk. That is fine on a laptop and stays the
default here -- nothing changes for local development. It stops being fine
the moment this API runs somewhere with an ephemeral filesystem, which is
most free-tier hosts (Render, Railway, Vercel serverless functions): every
redeploy or cold start wipes local files, and every review a user submitted
before that is gone.

So: if SUBMISSIONS_DATABASE_URL is set (a Postgres connection string --
Neon, in this project), submissions go there instead. Unset, everything
behaves exactly as it did before this file existed.

This is a compatibility shim, not an ORM. api.py's ~20 call sites were
written against sqlite3.Connection.execute() and sqlite3.Row for dict-like
row access. Rather than rewrite every call site for two driver APIs,
_PgConnection presents the same two methods sqlite3.Connection offers, so
api.py did not need to change at all -- only its `import sqlite3` /
`_db()` became an import from here.
"""
import os
import re
import sqlite3
from contextlib import contextmanager
from typing import Optional

from . import config as C

SUBMISSIONS_DB = C.ROOT / "user_submissions.db"

# Set to a Postgres URL to use it instead of the local SQLite file.
ENV_VAR = "SUBMISSIONS_DATABASE_URL"

# sqlite3 placeholders are "?"; psycopg2 wants "%s". Every query in api.py is
# a plain parameterized SELECT/INSERT with no literal "?" in any string
# value (checked in tests/test_submissions_db.py against the real queries),
# so a blind substitution is safe -- there is no SQL string-literal case to
# worry about escaping around.
_PLACEHOLDER_RE = re.compile(r"\?")


def _pg_driver_available() -> bool:
    try:
        import psycopg2  # noqa: F401
        return True
    except ImportError:
        return False


class _PgCursorResult:
    """What sqlite3.Connection.execute() returns, re-created around a
    psycopg2 cursor: just .fetchone() / .fetchall(). Nothing else in api.py
    is used (no .lastrowid -- review_id is a UUID generated in Python, not
    an autoincrement id, so there is nothing to retrieve after an INSERT)."""

    def __init__(self, cur):
        self._cur = cur

    def _wrap(self, row):
        if row is None:
            return None
        cols = [c.name for c in self._cur.description]
        return _Row(cols, row)

    def fetchone(self):
        return self._wrap(self._cur.fetchone())

    def fetchall(self):
        cols = [c.name for c in self._cur.description] if self._cur.description else []
        return [_Row(cols, r) for r in self._cur.fetchall()]


class _Row:
    """sqlite3.Row, re-created for a plain psycopg2 tuple row: readable by
    integer position (row[0]) AND by column name (row["col"]), and dict(row)
    works too.

    This exists because of a real bug this project shipped once: the first
    version of this adapter used psycopg2.extras.RealDictCursor, whose rows
    are plain dicts -- string keys only. api.py has seven call sites written
    as `.fetchone()[0]` (COUNT(*) queries, mostly), which is exactly how
    sqlite3.Row is meant to be read but raises `KeyError: 0` on a dict row.
    Every endpoint that touched the database failed with a 500 on Postgres
    until this was caught by a QA pass that actually exercised the running
    server rather than testing SQLite alone -- SQLite's Row silently
    supports both access styles, so it never failed the same way there.
    """
    __slots__ = ("_cols", "_data")

    def __init__(self, cols, data):
        self._cols = cols          # list[str], in cursor.description order
        self._data = tuple(data)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._data[key]
        return self._data[self._cols.index(key)]

    def keys(self):
        return list(self._cols)

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return f"_Row({dict(zip(self._cols, self._data))!r})"


class _PgConnection:
    """The two methods api.py actually calls on a connection: execute() and
    commit()/close(). Rows come back as _Row (see above), which reads like
    sqlite3.Row in every way api.py uses it: row[0], row["col"], dict(row)."""

    def __init__(self, raw_con, pool=None):
        # raw_con is a real psycopg2 connection -- either freshly opened, or
        # checked out of _pg_pool (see get_connection()). autocommit=True
        # regardless of source: api.py's read-only endpoints (/districts,
        # /stats, /reviews...) call .close() without ever calling .commit(),
        # which is fine on a connection that is opened and closed once, but
        # is NOT fine on a pooled one -- psycopg2 defaults to
        # autocommit=False, so a read leaves an open transaction on the
        # connection, and the NEXT request to borrow it from the pool
        # inherits that half-open transaction (a stale MVCC snapshot at
        # best; Neon can also kill a connection sitting "idle in
        # transaction"). autocommit makes every statement self-contained,
        # so a connection returned to the pool is always clean.
        raw_con.autocommit = True
        self._con = raw_con
        self._pool = pool

    def execute(self, sql: str, params: tuple = ()):
        cur = self._con.cursor()
        cur.execute(_PLACEHOLDER_RE.sub("%s", sql), params)
        return _PgCursorResult(cur)

    def executescript(self, sql: str):
        cur = self._con.cursor()
        cur.execute(sql)
        self._con.commit()   # a no-op under autocommit; harmless either way

    def commit(self):
        self._con.commit()   # ditto

    def close(self):
        # "Close" means "give it back", not "tear down the TCP+TLS session".
        # That distinction is the entire point of pooling: opening a fresh
        # connection to Neon measured a consistent ~3s per request --
        # verified across three back-to-back calls, so it was NOT a one-time
        # cold start, it was the real per-connection handshake cost every
        # single time. Every database-touching endpoint paid that on every
        # request before this existed.
        if self._pool is not None:
            self._pool.putconn(self._con)
        else:
            self._con.close()


# Postgres has no AUTOINCREMENT keyword, and INTEGER PRIMARY KEY does not
# self-increment the way SQLite's does -- SERIAL is the equivalent. Every
# other statement here (TEXT, REFERENCES, CREATE INDEX IF NOT EXISTS) is
# valid, unchanged, in both engines.
_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS user_reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id    TEXT    UNIQUE NOT NULL,
    destination  TEXT    NOT NULL,
    district     TEXT    NOT NULL,
    raw_text     TEXT    NOT NULL,
    source       TEXT    NOT NULL DEFAULT 'user_submission',
    submitted_at TEXT    NOT NULL,
    -- Withdrawal is a timestamp, not a DELETE. A review is evidence: the fact
    -- that somebody wrote it and then withdrew it is itself part of the
    -- record, and a hard delete would also orphan its segments and silently
    -- change every figure derived from them. Withdrawn rows are excluded from
    -- reads and counts and stay on disk.
    withdrawn_at TEXT,
    manage_token_hash TEXT
);

CREATE TABLE IF NOT EXISTS user_segments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id       TEXT    NOT NULL REFERENCES user_reviews(review_id),
    seg_index       INTEGER NOT NULL,
    segment_text    TEXT    NOT NULL,
    aspects         TEXT    NOT NULL,
    polarity        TEXT    NOT NULL,
    aspect_polarity TEXT,
    polarity_score  REAL    NOT NULL,
    triggered_words TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS user_corrections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    correction_id   TEXT    UNIQUE NOT NULL,
    review_id       TEXT    NOT NULL REFERENCES user_reviews(review_id),
    seg_index       INTEGER NOT NULL,
    segment_text    TEXT    NOT NULL,
    aspect          TEXT    NOT NULL,
    machine_verdict TEXT,
    human_verdict   TEXT    NOT NULL,
    labelled_by     TEXT    NOT NULL DEFAULT 'contributor',
    note            TEXT,
    submitted_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS user_stories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id     TEXT    UNIQUE NOT NULL,
    title        TEXT    NOT NULL,
    body         TEXT    NOT NULL,
    url          TEXT,
    destination  TEXT,
    district     TEXT,
    author       TEXT,
    submitted_at TEXT    NOT NULL,
    updated_at   TEXT,
    -- Proof of authorship for a system with no accounts. The token itself is
    -- returned once at creation and never stored; only this hash is kept, so
    -- a copy of the database does not let anybody edit or delete anyone's
    -- story. Without it, an open PATCH/DELETE would let any caller change any
    -- row, which is not a trade worth making for the convenience of a fix
    -- button.
    manage_token_hash TEXT
);

CREATE INDEX IF NOT EXISTS ix_user_segments_review_id ON user_segments(review_id);
CREATE INDEX IF NOT EXISTS ix_user_reviews_district ON user_reviews(district);
CREATE INDEX IF NOT EXISTS ix_user_reviews_destination ON user_reviews(destination);
CREATE INDEX IF NOT EXISTS ix_user_corrections_review_id ON user_corrections(review_id);
CREATE INDEX IF NOT EXISTS ix_user_stories_destination ON user_stories(destination);
"""

_SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS user_reviews (
    id           SERIAL PRIMARY KEY,
    review_id    TEXT    UNIQUE NOT NULL,
    destination  TEXT    NOT NULL,
    district     TEXT    NOT NULL,
    raw_text     TEXT    NOT NULL,
    source       TEXT    NOT NULL DEFAULT 'user_submission',
    submitted_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS user_segments (
    id              SERIAL PRIMARY KEY,
    review_id       TEXT    NOT NULL REFERENCES user_reviews(review_id),
    seg_index       INTEGER NOT NULL,
    segment_text    TEXT    NOT NULL,
    aspects         TEXT    NOT NULL,
    polarity        TEXT    NOT NULL,
    aspect_polarity TEXT,
    polarity_score  REAL    NOT NULL,
    triggered_words TEXT    NOT NULL
);

ALTER TABLE user_segments ADD COLUMN IF NOT EXISTS aspect_polarity TEXT;
ALTER TABLE user_reviews  ADD COLUMN IF NOT EXISTS withdrawn_at TEXT;
ALTER TABLE user_reviews  ADD COLUMN IF NOT EXISTS manage_token_hash TEXT;
ALTER TABLE user_stories  ADD COLUMN IF NOT EXISTS updated_at TEXT;
ALTER TABLE user_stories  ADD COLUMN IF NOT EXISTS manage_token_hash TEXT;

CREATE TABLE IF NOT EXISTS user_corrections (
    id              SERIAL  PRIMARY KEY,
    correction_id   TEXT    UNIQUE NOT NULL,
    review_id       TEXT    NOT NULL REFERENCES user_reviews(review_id),
    seg_index       INTEGER NOT NULL,
    segment_text    TEXT    NOT NULL,
    aspect          TEXT    NOT NULL,
    machine_verdict TEXT,
    human_verdict   TEXT    NOT NULL,
    labelled_by     TEXT    NOT NULL DEFAULT 'contributor',
    note            TEXT,
    submitted_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS user_stories (
    id           SERIAL  PRIMARY KEY,
    story_id     TEXT    UNIQUE NOT NULL,
    title        TEXT    NOT NULL,
    body         TEXT    NOT NULL,
    url          TEXT,
    destination  TEXT,
    district     TEXT,
    author       TEXT,
    submitted_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_user_segments_review_id ON user_segments(review_id);
CREATE INDEX IF NOT EXISTS ix_user_reviews_district ON user_reviews(district);
CREATE INDEX IF NOT EXISTS ix_user_reviews_destination ON user_reviews(destination);
CREATE INDEX IF NOT EXISTS ix_user_corrections_review_id ON user_corrections(review_id);
CREATE INDEX IF NOT EXISTS ix_user_stories_destination ON user_stories(destination);
"""

_backend_logged = False
_schema_ensured = False
_pg_pool = None   # psycopg2.pool.ThreadedConnectionPool, created once

# min/max pooled connections. Small on purpose: this is a review-analysis
# portal's submission store, not a high-traffic service, and Neon's own
# connection limit on a free-tier project is itself small.
POOL_MIN = 1
POOL_MAX = 5


def _migrate_sqlite(con) -> None:
    """Add columns that CREATE TABLE IF NOT EXISTS cannot.

    IF NOT EXISTS is a no-op on a table that already exists, so a schema
    change never reaches a database created before it. Postgres can say ADD
    COLUMN IF NOT EXISTS inline; SQLite cannot, so the column list is read
    and compared here. Both paths end with the same shape.
    """
    wanted = {
        "user_segments": [("aspect_polarity", "TEXT")],
        "user_reviews": [("withdrawn_at", "TEXT"),
                         ("manage_token_hash", "TEXT")],
        "user_stories": [("updated_at", "TEXT"),
                         ("manage_token_hash", "TEXT")],
    }
    changed = False
    for table, columns in wanted.items():
        have = {row[1] for row in con.execute(
            "PRAGMA table_info({})".format(table))}
        if not have:
            continue                      # table not created yet
        for name, sql_type in columns:
            if name not in have:
                con.execute("ALTER TABLE {} ADD COLUMN {} {}".format(
                    table, name, sql_type))
                changed = True
    if changed:
        con.commit()


def _get_pool(dsn: str):
    """The pool, created once per process and reused for the rest of its
    life. Opening a fresh psycopg2.connect(dsn) per request measured a
    consistent ~3 seconds -- checked across three back-to-back calls, so it
    was the real TCP+TLS handshake cost every time, not a one-off cold
    start. Every database-touching endpoint (including plain reads like
    /districts and /stats) paid that before this existed. Checking a
    connection out of a warm pool instead brings it down to the cost of the
    query itself."""
    global _pg_pool
    if _pg_pool is None:
        from psycopg2.pool import ThreadedConnectionPool
        # ThreadedConnectionPool, not SimpleConnectionPool: uvicorn's sync
        # `def` endpoints (every handler in api.py) run in a worker thread
        # pool, so more than one request can call get_connection()
        # concurrently. SimpleConnectionPool is documented as not
        # thread-safe for that.
        _pg_pool = ThreadedConnectionPool(POOL_MIN, POOL_MAX, dsn)
    return _pg_pool


def _checkout(pool, attempts: int = 3):
    """Borrow a connection from the pool that is known to still be alive.

    psycopg2's pool hands back whatever it is holding without checking it,
    and Neon closes connections when a free-tier project scales to zero
    after a few minutes idle. The pool does not know that happened, so the
    first request after a quiet period got a dead socket and returned a 500
    while an immediate retry succeeded -- observed against the running
    server, and the reason a liveness probe is worth one extra round trip on
    checkout.

    A connection that fails the probe is closed rather than returned, so the
    pool opens a fresh one in its place instead of handing the same corpse
    to the next caller.
    """
    last_exc = None
    for _ in range(attempts):
        raw = pool.getconn()
        try:
            raw.autocommit = True
            cur = raw.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
            return _PgConnection(raw, pool=pool)
        except Exception as exc:      # dead socket, or Neon still waking up
            last_exc = exc
            try:
                pool.putconn(raw, close=True)
            except Exception:
                pass
    raise RuntimeError(
        "could not obtain a live Postgres connection after {} attempts: "
        "{}".format(attempts, last_exc))


def active_backend() -> str:
    """'postgres' or 'sqlite', without opening a connection. Used by /health
    so a liveness probe does not itself pay for a Neon round trip."""
    return "postgres" if os.environ.get(ENV_VAR) else "sqlite"


def get_connection():
    """Return a connection: Postgres if SUBMISSIONS_DATABASE_URL is set and
    psycopg2 is installed, local SQLite otherwise. Logs which backend is
    active once per process -- the same pattern _get_polarity_method() uses
    for the polarity model, for the same reason: state a silent default
    change out loud in the log rather than let it pass unnoticed.
    """
    global _backend_logged, _schema_ensured
    dsn = os.environ.get(ENV_VAR)

    if dsn:
        if not _pg_driver_available():
            raise RuntimeError(
                f"{ENV_VAR} is set but psycopg2 is not installed. Run "
                "`pip install psycopg2-binary`, or unset {} to fall back "
                "to local SQLite.".format(ENV_VAR)
            )
        if not _backend_logged:
            # Never log the DSN itself -- it carries the password.
            print("  [db] user submissions: Postgres (Neon), pooled "
                 f"({POOL_MIN}-{POOL_MAX} connections)")
            _backend_logged = True
        con = _checkout(_get_pool(dsn))
        # DDL is idempotent (IF NOT EXISTS throughout) but still a Neon
        # round trip, so it only runs once per process rather than on every
        # request, unlike the SQLite path below, which mirrors what api.py
        # already did before this file existed.
        if not _schema_ensured:
            try:
                con.executescript(_SCHEMA_POSTGRES)
            except Exception:
                # Give the connection back before the exception leaves this
                # function, or the pool loses one for good.
                con.close()
                raise
            _schema_ensured = True
        return con

    if not _backend_logged:
        print(f"  [db] user submissions: local SQLite ({SUBMISSIONS_DB.name})")
        _backend_logged = True
    con = sqlite3.connect(str(SUBMISSIONS_DB))
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA_SQLITE)
    _migrate_sqlite(con)
    return con


@contextmanager
def connection():
    """A connection for the duration of a block, returned no matter what.

    Every caller in api.py used to open one with get_connection() and close
    it on the happy path -- inside the try in /analyse, after the query on
    the read endpoints. A query that raised skipped the close. Against
    SQLite that costs nothing anyone notices; against the pooled Postgres
    backend close() IS putconn(), so each failed request permanently removed
    a connection from a pool of five, and the fifth failure wedged the
    process until it was restarted.
    """
    con = get_connection()
    try:
        yield con
    finally:
        con.close()
