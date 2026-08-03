"""
Purge Non-Safety Reports — SafeTravel LK Research Engine
IT22629180

Purges all non-safety records (is_scam = 0, scam_type = 'safe', or generic non-incident posts)
from safety_heatmap.db so the safety risk engine operates exclusively on genuine safety signals.
"""
import sqlite3
import os

def purge_non_safety():
    db_path = os.path.join(os.path.dirname(__file__), "safety_heatmap.db")
    print(f"[Purge] Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM reports")
    total_before = cur.fetchone()[0]
    print(f"[Purge] Total reports before purge: {total_before:,}")

    # Delete records with is_scam = 0 or scam_type = 'safe' or NULL scam_type with is_scam != 1
    cur.execute("""
        DELETE FROM reports
        WHERE is_scam = 0
           OR scam_type = 'safe'
           OR scam_type IS NULL
           OR TRIM(scam_type) = ''
           OR LOWER(scam_type) = 'none'
    """)
    deleted_count = cur.rowcount
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM reports")
    total_after = cur.fetchone()[0]
    print(f"[Purge] Deleted {deleted_count:,} non-safety / non-scam reports.")
    print(f"[Purge] Remaining verified safety incident reports: {total_after:,}")

    # Show breakdown of remaining safety reports
    cur.execute("SELECT scam_type, COUNT(*) FROM reports GROUP BY scam_type ORDER BY COUNT(*) DESC")
    print("\n[Purge] Breakdown of Active Safety Incidents:")
    for scam_type, count in cur.fetchall():
        print(f"  - {scam_type}: {count:,}")

    conn.close()

if __name__ == "__main__":
    purge_non_safety()
