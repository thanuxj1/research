import sqlite3

conn = sqlite3.connect(r'E:\research\backend\safety_heatmap.db')
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM reports")
print("Total reports in DB:", cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM reports WHERE source='tripadvisor_csv'")
print("tripadvisor_csv reports:", cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM reports WHERE location_name LIKE '%Arugam%'")
print("Arugam Bay reports:", cur.fetchone()[0])

cur.execute("""SELECT location_name, title, risk_level, helpful_votes 
               FROM reports WHERE location_name LIKE '%Arugam%' LIMIT 5""")
print("\nSample Arugam Bay rows:")
for r in cur.fetchall():
    print(f"  loc={r[0]} | {r[1][:60]} | risk={r[2]} | helpful={r[3]}")

cur.execute("SELECT source, COUNT(*) as cnt FROM reports GROUP BY source ORDER BY cnt DESC LIMIT 12")
print("\nAll sources:")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
