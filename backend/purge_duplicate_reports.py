"""
Database Duplicate Report Purge Script
SafeTravel LK — IT22629180

Removes duplicate report records from safety_heatmap.db where identical content/reviews were ingested multiple times.
"""
import os
import sqlite3

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BACKEND_DIR, "safety_heatmap.db")

def purge_duplicates():
    print("=" * 60)
    print(" Purging Duplicate Reports from safety_heatmap.db ...")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database file not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT count(*) as cnt FROM reports")
    total_before = c.fetchone()['cnt']

    # Delete duplicate reports, preserving the record with MIN(id)
    c.execute("""
        DELETE FROM reports
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM reports
            WHERE content IS NOT NULL AND content != ''
            GROUP BY LOWER(TRIM(content))
        ) AND content IS NOT NULL AND content != ''
    """)

    deleted_count = c.rowcount
    conn.commit()

    c.execute("SELECT count(*) as cnt FROM reports")
    total_after = c.fetchone()['cnt']

    print(f"Total reports BEFORE purge: {total_before:,}")
    print(f"Duplicate records DELETED:  {deleted_count:,}")
    print(f"Total reports AFTER purge:  {total_after:,}")

    # Run VACUUM to reclaim space and optimize DB
    print("Optimizing database structure (VACUUM)...")
    c.execute("VACUUM")
    conn.close()
    print("Database deduplication successfully completed.")

if __name__ == "__main__":
    purge_duplicates()
