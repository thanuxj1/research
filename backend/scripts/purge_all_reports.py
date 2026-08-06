"""
purge_all_reports.py
Wipes ALL rows from the `reports` and `risk_zones` tables and resets
auto-increment counters so the next scraping run starts clean.

Run from e:\research\backend:
    python scripts/purge_all_reports.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "safety_heatmap.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Count before
    cur.execute("SELECT COUNT(*) FROM reports")
    before_reports = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM risk_zones")
    before_zones = cur.fetchone()[0]
    print(f"Before — reports: {before_reports:,}  |  risk_zones: {before_zones:,}")

    # Disable FK temporarily, delete all rows, reset sequences
    cur.execute("PRAGMA foreign_keys = OFF")
    cur.execute("DELETE FROM risk_zones")
    cur.execute("DELETE FROM reports")
    # Reset SQLite auto-increment counters (only if table exists)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
    if cur.fetchone():
        cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('reports', 'risk_zones')")
    cur.execute("PRAGMA foreign_keys = ON")

    # Reclaim disk space
    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    print("All rows deleted and database compacted successfully.")
    print("risk_zones table: 0 rows")
    print("reports table: 0 rows")
    print("\nThe database is ready for a fresh scraping run.")


if __name__ == "__main__":
    main()
