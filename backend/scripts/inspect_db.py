import sqlite3, os
db_path = os.path.join(os.path.dirname(__file__), '..', 'safety_heatmap.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print("Tables:", [t[0] for t in tables])
for (tbl,) in tables:
    cur.execute(f"SELECT COUNT(*) FROM [{tbl}]")
    count = cur.fetchone()[0]
    # Sample a few URLs
    cur.execute(f"SELECT url FROM [{tbl}] WHERE url IS NOT NULL LIMIT 3")
    sample_urls = cur.fetchall()
    print(f"  {tbl}: {count} rows | sample urls: {[u[0] for u in sample_urls]}")
conn.close()
