"""
Build Master Primary Dataset — SafeTravel LK
IT22629180

Consolidates ALL raw and archived datasets into ONE unified, standard primary dataset CSV.
Unified Schema:
  - id: Unique record ID
  - dataset_source: Origin archive/file
  - data_category: news | review | report | weather | arrivals
  - date: ISO date string YYYY-MM-DD
  - location_name: Location or destination
  - city: City name
  - district: District / region
  - lat: Latitude coordinate
  - lon: Longitude coordinate
  - text_content: Original text / description / review
  - rating: User rating (1-5) if available
  - is_scam: Binary scam flag (1/0)
  - scam_type: Categorized scam type
  - sentiment: Normalized sentiment score (-1.0 to +1.0)
  - risk_level: Inferred risk level (1=Low, 2=Med, 3=High)
"""
import os
import sys
import csv
import re
import pandas as pd
import sqlite3

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH_DIR = os.path.dirname(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from training.generate_training_data import label_text

OUTPUT_PRIMARY_CSV = os.path.join(RESEARCH_DIR, "primary_master_dataset.csv")
OUTPUT_PRIMARY_BACKEND = os.path.join(BACKEND_DIR, "training", "dataset", "primary_master_dataset.csv")
DB_PATH = os.path.join(BACKEND_DIR, "safety_heatmap.db")

CITY_COORDS = {
    "colombo": (6.9271, 79.8612, "Colombo"),
    "kandy": (7.2906, 80.6337, "Central"),
    "galle": (6.0535, 80.2210, "Southern"),
    "sigiriya": (7.9570, 80.7603, "Central"),
    "ella": (6.8667, 81.0500, "Uva"),
    "nuwara eliya": (6.9497, 80.7891, "Central"),
    "anuradhapura": (8.3114, 80.4037, "North Central"),
    "mirissa": (5.9483, 80.4716, "Southern"),
    "hikkaduwa": (6.1395, 80.1067, "Southern"),
    "jaffna": (9.6615, 80.0255, "Northern"),
    "polonnaruwa": (7.9403, 81.0188, "North Central"),
    "habarana": (8.0500, 80.7500, "North Central"),
    "trincomalee": (8.5874, 81.2152, "Eastern"),
    "arugam bay": (6.8401, 81.8303, "Eastern"),
    "bentota": (6.4219, 80.0001, "Southern"),
    "negombo": (7.2081, 79.8358, "Western"),
    "unawatuna": (6.0108, 80.2491, "Southern"),
    "dambulla": (7.8742, 80.6511, "Central"),
    "matara": (5.9549, 80.5550, "Southern"),
    "weligama": (5.9747, 80.4297, "Southern"),
}


def geocode_text(text):
    text_lower = text.lower()
    for city_key, (lat, lon, prov) in CITY_COORDS.items():
        if city_key in text_lower:
            return city_key.title(), lat, lon
    return "", None, None


def process_reviews_csv():
    print("[1/6] Processing Reviews.csv...")
    p = os.path.join(RESEARCH_DIR, "Reviews.csv")
    if not os.path.exists(p):
        return []

    rows = []
    idx = 1
    with open(p, "r", encoding="latin-1", errors="ignore") as f:
        reader = csv.DictReader(f)
        for r in reader:
            city = (r.get("Located_City") or "").strip()
            loc_name = (r.get("Location_Name") or "").strip()
            title = (r.get("Title") or "").strip()
            text = (r.get("Text") or "").strip()
            rating_str = r.get("Rating", "3")
            try:
                rating = float(rating_str)
            except ValueError:
                rating = 3.0

            date_str = (r.get("Travel_Date") or r.get("Published_Date") or "").strip()[:10]
            full_text = f"{title} - {text}" if title else text
            if len(full_text) < 15:
                continue

            text_lower = full_text.lower()
            is_scam, scam_type, sentiment = label_text(text_lower)

            # Assign risk level
            if is_scam or rating <= 2:
                risk = 3 if (is_scam and rating <= 2) else 2
            else:
                risk = 1

            c_key = city.lower()
            coords = CITY_COORDS.get(c_key)
            lat = coords[0] if coords else None
            lon = coords[1] if coords else None

            rows.append({
                "id": f"REV_{idx:06d}",
                "dataset_source": "Reviews.csv",
                "data_category": "review",
                "date": date_str,
                "location_name": loc_name,
                "city": city,
                "district": "",
                "lat": lat,
                "lon": lon,
                "text_content": full_text[:1500].replace('"', "'"),
                "rating": rating,
                "is_scam": is_scam,
                "scam_type": scam_type,
                "sentiment": sentiment,
                "risk_level": risk,
            })
            idx += 1

    print(f"      -> Processed {len(rows):,} review records")
    return rows


def process_destination_reviews():
    print("[2/6] Processing Destination Reviews (final).csv...")
    p = os.path.join(RESEARCH_DIR, "archive (2)", "Destination Reviews (final).csv")
    if not os.path.exists(p):
        return []

    rows = []
    idx = 1
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for r in reader:
            dest = (r.get("Destination") or "").strip()
            district = (r.get("District") or "").strip()
            review = (r.get("Review") or "").strip()
            if len(review) < 15:
                continue

            text_lower = f"{dest} {district} {review}".lower()
            is_scam, scam_type, sentiment = label_text(text_lower)
            matched_city, lat, lon = geocode_text(text_lower)

            rows.append({
                "id": f"DEST_REV_{idx:06d}",
                "dataset_source": "archive (2)/Destination Reviews",
                "data_category": "review",
                "date": "",
                "location_name": dest,
                "city": matched_city or district.title(),
                "district": district.title(),
                "lat": lat,
                "lon": lon,
                "text_content": review[:1500].replace('"', "'"),
                "rating": None,
                "is_scam": is_scam,
                "scam_type": scam_type,
                "sentiment": sentiment,
                "risk_level": 2 if is_scam else 1,
            })
            idx += 1

    print(f"      -> Processed {len(rows):,} destination review records")
    return rows


def process_news_csv():
    print("[3/6] Processing archive (4)/news.csv...")
    p = os.path.join(RESEARCH_DIR, "archive (4)", "news.csv")
    if not os.path.exists(p):
        return []

    rows = []
    idx = 1
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for r in reader:
            heading = (r.get("heading") or "").strip()
            content = (r.get("content") or "").strip()
            pub_date = (r.get("published_date") or "").strip()[:10]
            source = (r.get("source") or "news").strip()

            full_text = f"{heading}. {content}"
            if len(full_text) < 20:
                continue

            text_lower = full_text.lower()
            is_scam, scam_type, sentiment = label_text(text_lower[:2000])
            matched_city, lat, lon = geocode_text(text_lower)

            rows.append({
                "id": f"NEWS_{idx:06d}",
                "dataset_source": f"archive (4)/news ({source})",
                "data_category": "news",
                "date": pub_date,
                "location_name": matched_city,
                "city": matched_city,
                "district": "",
                "lat": lat,
                "lon": lon,
                "text_content": full_text[:1500].replace('"', "'"),
                "rating": None,
                "is_scam": is_scam,
                "scam_type": scam_type,
                "sentiment": sentiment,
                "risk_level": 3 if is_scam else 1,
            })
            idx += 1

    print(f"      -> Processed {len(rows):,} news records")
    return rows


def process_derana_news():
    print("[4/6] Processing archive (5)/Derana_News.csv...")
    p = os.path.join(RESEARCH_DIR, "archive (5)", "Derana_News.csv")
    if not os.path.exists(p):
        return []

    rows = []
    idx = 1
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for r in reader:
            title = (r.get("Title") or "").strip()
            desc = (r.get("Description") or "").strip()
            pub_date = (r.get("Date") or "").strip()[:10]

            full_text = f"{title}. {desc}"
            if len(full_text) < 20:
                continue

            text_lower = full_text.lower()
            is_scam, scam_type, sentiment = label_text(text_lower[:1500])
            matched_city, lat, lon = geocode_text(text_lower)

            rows.append({
                "id": f"DERANA_{idx:06d}",
                "dataset_source": "archive (5)/Derana_News",
                "data_category": "news",
                "date": pub_date,
                "location_name": matched_city,
                "city": matched_city,
                "district": "",
                "lat": lat,
                "lon": lon,
                "text_content": full_text[:1500].replace('"', "'"),
                "rating": None,
                "is_scam": is_scam,
                "scam_type": scam_type,
                "sentiment": sentiment,
                "risk_level": 3 if is_scam else 1,
            })
            idx += 1

    print(f"      -> Processed {len(rows):,} Derana news records")
    return rows


def process_db_reports():
    print("[5/6] Processing DB safety reports...")
    if not os.path.exists(DB_PATH):
        return []

    rows = []
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            SELECT id, source, content, created_at, location_name, latitude, longitude,
                   is_scam, scam_type, sentiment_score, risk_level
            FROM reports
        """)
        for r in c.fetchall():
            rid, src, content, created, loc, lat, lon, is_scam, stype, sent, risk = r
            content = (content or "").strip()
            if not content:
                continue
            rows.append({
                "id": f"DB_REP_{rid}",
                "dataset_source": f"db_{src or 'report'}",
                "data_category": "report",
                "date": (str(created) if created else "")[:10],
                "location_name": loc or "",
                "city": loc or "",
                "district": "",
                "lat": lat,
                "lon": lon,
                "text_content": content[:1500].replace('"', "'"),
                "rating": None,
                "is_scam": int(is_scam or 0),
                "scam_type": stype or "",
                "sentiment": float(sent or 0.0),
                "risk_level": int(risk or 1),
            })
    except Exception as e:
        print(f"  [WARN] DB read error: {e}")
    finally:
        conn.close()

    print(f"      -> Processed {len(rows):,} DB safety reports")
    return rows


def main():
    print("=" * 65)
    print("  Building Unified Master Primary Dataset — SafeTravel LK")
    print("  IT22629180")
    print("=" * 65)

    all_rows = []
    all_rows.extend(process_reviews_csv())
    all_rows.extend(process_destination_reviews())
    all_rows.extend(process_news_csv())
    all_rows.extend(process_derana_news())
    all_rows.extend(process_db_reports())

    print(f"\n[6/6] Writing Master Primary Dataset ({len(all_rows):,} total records)...")

    fieldnames = [
        "id", "dataset_source", "data_category", "date", "location_name",
        "city", "district", "lat", "lon", "text_content", "rating",
        "is_scam", "scam_type", "sentiment", "risk_level"
    ]

    # Save to research root and backend folder
    for out_path in [OUTPUT_PRIMARY_CSV, OUTPUT_PRIMARY_BACKEND]:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

    # Calculate summary stats
    scams = sum(1 for r in all_rows if r["is_scam"] == 1)
    geocoded = sum(1 for r in all_rows if r["lat"] is not None)

    print("\n" + "=" * 65)
    print("  MASTER PRIMARY DATASET CREATED SUCCESSFULLY!")
    print(f"  Saved to: {OUTPUT_PRIMARY_CSV}")
    print(f"  Saved to: {OUTPUT_PRIMARY_BACKEND}")
    print(f"  Total Master Records: {len(all_rows):,}")
    print(f"  Scam/Incident Records: {scams:,} ({scams/len(all_rows):.1%})")
    print(f"  Geocoded Records:      {geocoded:,} ({geocoded/len(all_rows):.1%})")
    print("=" * 65)


if __name__ == "__main__":
    main()
