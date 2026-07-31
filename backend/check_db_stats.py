
import sqlite3
import os

db_path = 'safety_heatmap.db'
if not os.path.exists(db_path):
    print(f"Error: {db_path} not found.")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Get tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cur.fetchall()
print(f"Tables: {tables}")

for table_name_tuple in tables:
    table_name = table_name_tuple[0]
    cur.execute(f"SELECT count(*) FROM {table_name};")
    count = cur.fetchone()[0]
    print(f"  {table_name}: {count} records")
    
    if table_name == 'reports':
        cur.execute(f"SELECT max(id) FROM {table_name};")
        max_id = cur.fetchone()[0]
        print(f"    Max ID: {max_id}")
        
        cur.execute(f"SELECT source, count(*) FROM {table_name} GROUP BY source;")
        sources = cur.fetchall()
        print(f"    Sources: {sources}")

        cur.execute(f"SELECT latitude, longitude FROM {table_name} WHERE latitude IS NOT NULL LIMIT 5;")
        coords = cur.fetchall()
        print(f"    Sample Coords: {coords}")

    if table_name == 'risk_zones':
        cur.execute(f"SELECT cluster_id, risk_score, report_count FROM {table_name};")
        rows = cur.fetchall()
        print(f"    Zones (ID, Score, Count): {rows}")

# Check if there are other tables or maybe deleted data?
# SQLite doesn't show deleted data easily, but the file size 1.4MB is big for 17 records.
# Maybe there was a massive table that was dropped?
conn.close()
