"""
Populate safety_heatmap.db with geocoded records from primary_master_dataset_clean.csv
IT22629180
"""
import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
RESEARCH_DIR = os.path.dirname(BACKEND_DIR)

MASTER_CSV = os.path.join(RESEARCH_DIR, "primary_master_dataset_clean.csv")
DB_PATH = os.path.join(BACKEND_DIR, "safety_heatmap.db")


def populate():
    print("=" * 60)
    print(" Populating SQLite DB with Master Geocoded Safety Incidents")
    print("=" * 60)

    if not os.path.exists(MASTER_CSV):
        print(f"[ERROR] Master dataset not found at {MASTER_CSV}")
        return

    df = pd.read_csv(MASTER_CSV, encoding="utf-8", low_memory=False)
    # Filter only rows with valid latitude and longitude
    geo_df = df[df["lat"].notnull() & df["lon"].notnull()].copy()
    print(f"Loaded {len(geo_df):,} geocoded records from master dataset.")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get existing text_content or titles to prevent duplicate DB insertions
    c.execute("SELECT content FROM reports")
    existing_contents = set(row[0] for row in c.fetchall() if row[0])

    new_rows = []
    for _, r in geo_df.iterrows():
        text = str(r["text_content"] or "").strip()
        if not text or text in existing_contents:
            continue
        existing_contents.add(text)

        source = str(r.get("dataset_source") or "archive")
        title = text[:100] + "..." if len(text) > 100 else text
        is_scam = 1 if r.get("is_scam") == 1 else 0
        scam_type = str(r.get("scam_type") or "") if is_scam else None
        sentiment = float(r.get("sentiment") or 0.0)
        risk_level = int(r.get("risk_level") or 1)
        lat = float(r["lat"])
        lon = float(r["lon"])
        location_name = str(r.get("location_name") or r.get("city") or "Sri Lanka")
        date_str = str(r.get("date") or "")
        created_at = date_str if date_str and len(date_str) >= 10 else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        new_rows.append((
            source, None, title, text, sentiment, is_scam, scam_type,
            risk_level, lat, lon, location_name, "general", 0.5, created_at
        ))

    print(f"Prepared {len(new_rows):,} unique new geocoded records for DB insertion.")

    c.executemany("""
        INSERT INTO reports (
            source, url, title, content, sentiment_score, is_scam, scam_type,
            risk_level, latitude, longitude, location_name, demographic_target,
            source_weight, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, new_rows)

    conn.commit()

    c.execute("SELECT COUNT(*) FROM reports WHERE latitude IS NOT NULL")
    total_geo = c.fetchone()[0]
    conn.close()

    print("\n" + "=" * 60)
    print(f" SUCCESS! Database populated.")
    print(f" Total Geolocated Incidents in DB: {total_geo:,}")
    print("=" * 60)


if __name__ == "__main__":
    populate()
