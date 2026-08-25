"""
TravelLens LK -- load the outputs into SQLite.

Why a separate database file
----------------------------
The parent project already has `backend/safety_heatmap.db` with its own schema
(`reports`, `risk_zones`) and a live application reading it. Writing this
project's tables into that file would risk breaking something that works, for
no gain: nothing here needs to join against those tables.

So the default target is `travellens/travellens.db`. SQLite can attach two
files in one connection when a cross-database query is genuinely wanted:

    ATTACH DATABASE 'travellens.db' AS tl;
    SELECT * FROM tl.scorecards;

That gives the joins without the coupling.

What goes in, and what stays out
--------------------------------
IN -- the things something else would query: the corpus, the per-sentence
labels, the aggregated scorecards, coordinates and links.

SEPARATE -- storyboard media lands in its own table, `media`, and no view or
index joins it to the label tables. It is displayed beside a destination and
never counted; that rule is carried into the schema rather than left as a
convention. See media.py.

OUT -- the intermediate caches (`polarity_cache_*.csv`, `segments.csv`). They
exist to make re-runs fast, not to be queried, and they would triple the file
size for nothing.

Idempotent: each table is dropped and rebuilt from the CSVs, so running this
twice gives the same database as running it once.

Run with:  python scripts/29_load_db.py
"""
import sqlite3
from typing import Dict, List, Optional

import pandas as pd

from . import config as C

DB_PATH = C.ROOT / "travellens.db"

# (table, source file, index columns). Order matters only for readability.
TABLES = [
    ("reviews", C.DATA_PROCESSED / "reviews_clean.csv",
     ["destination", "district", "source", "recency"]),
    ("labels", None,                                   # built, not copied
     ["destination", "district", "aspect", "polarity"]),
    ("scorecards", C.DATA_PROCESSED / "scorecards.csv",
     ["destination", "district", "aspect"]),
    ("coordinates", C.DATA_PROCESSED / "destination_coordinates.csv",
     ["destination"]),
    ("media", C.DATA_PROCESSED / "media.csv",
     ["destination", "kind"]),
]

# Columns dropped on load: large free text that bloats the file without being
# queried. The corpus text stays -- that one IS queried.
DROP_COLUMNS = {"media": ["snippet"]}


def _write(con: sqlite3.Connection, name: str, df: pd.DataFrame,
           indexes: List[str], verbose: bool = True) -> int:
    for col in DROP_COLUMNS.get(name, []):
        if col in df.columns:
            df = df.drop(columns=[col])
    con.execute('DROP TABLE IF EXISTS "{}"'.format(name))
    df.to_sql(name, con, index=False)
    for col in indexes:
        if col in df.columns:
            con.execute('CREATE INDEX "ix_{0}_{1}" ON "{0}"("{1}")'.format(name, col))
    if verbose:
        print("  {:<14} {:>7,} rows  ({} indexes)".format(
            name, len(df), sum(1 for c in indexes if c in df.columns)))
    return len(df)


def build_labels(verbose: bool = True) -> pd.DataFrame:
    """One row per (sentence, aspect) with the label finally assigned.

    Reuses the release builder so the database and the released CSV cannot
    drift apart -- two code paths producing "the labels" is how a project ends
    up with two different answers to the same question.
    """
    from .release import build_enriched
    return build_enriched(verbose=verbose)


def load(db_path=None, verbose: bool = True) -> Dict[str, int]:
    db_path = db_path or DB_PATH
    con = sqlite3.connect(str(db_path))
    counts = {}
    try:
        for name, path, indexes in TABLES:
            if name == "labels":
                df = build_labels(verbose=False)
            elif path and path.exists():
                df = pd.read_csv(path)
            else:
                if verbose:
                    print("  {:<14} skipped -- {} not found".format(
                        name, path.name if path else "?"))
                continue
            counts[name] = _write(con, name, df, indexes, verbose)

        # Convenience view: the dashboard's headline numbers, one row per
        # destination-aspect, without needing to know which columns matter.
        con.execute("DROP VIEW IF EXISTS v_complaints")
        con.execute("""
            CREATE VIEW v_complaints AS
            SELECT district, destination, aspect,
                   n_negative   AS complaints,
                   n_positive   AS praise,
                   complaint_rate,
                   confidence
            FROM scorecards
            WHERE confidence != 'suppressed'
        """)
        con.commit()
    finally:
        con.close()
    return counts


def summary(db_path=None) -> str:
    db_path = db_path or DB_PATH
    con = sqlite3.connect(str(db_path))
    out = []
    try:
        rows = con.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table','view') ORDER BY type, name").fetchall()
        for name, kind in rows:
            try:
                n = con.execute('SELECT COUNT(*) FROM "{}"'.format(name)).fetchone()[0]
            except sqlite3.Error:
                n = "?"
            out.append("  {:<8} {:<14} {:>8,} rows".format(kind, name, n))
    finally:
        con.close()
    return "\n".join(out)


def main():
    print("\nTravelLens LK -- load to SQLite\n" + "=" * 60)
    print("  target: {}".format(DB_PATH))
    print("  (separate from backend/safety_heatmap.db -- see module docstring)\n")
    load()
    print("\n  contents:")
    print(summary())
    size = DB_PATH.stat().st_size / 1e6
    print("\n  {:.1f} MB".format(size))
    print("\n  query it:")
    print("    sqlite3 travellens.db \"SELECT * FROM v_complaints "
          "WHERE aspect='safety' ORDER BY complaint_rate DESC LIMIT 10;\"")


if __name__ == "__main__":
    main()
