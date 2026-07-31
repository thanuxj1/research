"""
Ingestion & Analytics Engine — New Destination Reviews Datasets
IT22629180

Reads:
  - Destination Reviews (final).csv (35,435 rows)
  - Destination Reviews_(raw).csv (37,416 rows)

Processes:
  1. Deduplicates reviews across both files.
  2. Map destination & district names to Sri Lanka lat/long coordinates.
  3. Uses NLPPipeline to extract scam categories, risk levels, and sentiment.
  4. Ingests safety-relevant reviews into SQLite DB (safety_heatmap.db) with Tier 2b weight (0.60).
  5. Appends records to primary master dataset.
"""
import os
import csv
import sqlite3
from datetime import datetime, timezone
from app.ml.nlp_pipeline import NLPPipeline, SL_LOCATIONS, SCAM_TAXONOMY

KEYWORDS = [
    "scam", "fraud", "fake", "overcharge", "trap", "dangerous",
    "cheat", "rip off", "mafia", "assault", "harassment", "overpriced", "tricking"
]

# Expanded District & Destination coordinate mapping for Sri Lanka
DISTRICT_COORDS = {
    "colombo":      (6.9271, 79.8612),
    "gampaha":      (7.0840, 79.9925),
    "kalutara":     (6.5854, 79.9607),
    "kandy":        (7.2906, 80.6337),
    "matale":       (7.4675, 80.6234),
    "nuwara eliya": (6.9497, 80.7891),
    "galle":        (6.0535, 80.2210),
    "matara":       (5.9549, 80.5550),
    "hambantota":   (6.1247, 81.1185),
    "jaffna":       (9.6615, 80.0255),
    "kilinochchi":  (9.3803, 80.3770),
    "mannar":       (8.9810, 79.9044),
    "vavuniya":     (8.7514, 80.4971),
    "mullaitivu":   (9.2671, 80.8142),
    "batticaloa":   (7.7170, 81.7000),
    "ampara":       (7.2811, 81.6747),
    "trincomalee":  (8.5874, 81.2152),
    "kurunegala":   (7.4863, 80.3647),
    "puttalam":     (8.0362, 79.8283),
    "anuradhapura": (8.3114, 80.4037),
    "polonnaruwa":  (7.9396, 81.0009),
    "badulla":      (6.9931, 81.0549),
    "monaragala":   (6.8731, 81.3507),
    "ratnapura":    (6.6828, 80.3992),
    "kegalle":      (7.2513, 80.3464),
}


def get_coords_for_destination(dest_name: str, district_name: str):
    dest_clean = (dest_name or "").lower().strip()
    dist_clean = (district_name or "").lower().strip()

    # Check place in SL_LOCATIONS first
    for loc_key, coords in SL_LOCATIONS.items():
        if loc_key in dest_clean:
            return coords[0], coords[1]

    # Fallback to district coords
    if dist_clean in DISTRICT_COORDS:
        return DISTRICT_COORDS[dist_clean]

    # Default fallback to Colombo
    return 6.9271, 79.8612


def process_destination_datasets():
    nlp = NLPPipeline()
    base_dir = os.path.dirname(os.path.dirname(__file__))
    
    file_final = os.path.join(base_dir, "Destination Reviews (final).csv")
    file_raw = os.path.join(base_dir, "Destination Reviews_(raw).csv")

    collected_records = []
    seen_contents = set()

    files_to_process = [file_final, file_raw]

    print(f"=" * 70)
    print(f"  INGESTING NEW DESTINATION REVIEWS DATASETS")
    print(f"=" * 70)

    for filepath in files_to_process:
        if not os.path.exists(filepath):
            print(f"[Warning] File not found: {filepath}")
            continue

        print(f"\n[Reading] Processing {os.path.basename(filepath)}...")
        with open(filepath, mode="r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            count = 0
            flagged = 0

            for row in reader:
                count += 1
                dest = row.get("Destination", "").strip()
                district = row.get("District", "").strip()
                review_text = row.get("Review", "").strip()

                if not review_text or len(review_text) < 15:
                    continue

                # Deduplication check
                content_key = f"{dest.lower()}_{review_text[:60].lower()}"
                if content_key in seen_contents:
                    continue
                seen_contents.add(content_key)

                text_lower = review_text.lower()
                
                # Check for safety keyword matches OR negative tone / scam terms
                is_safety_flagged = any(kw in text_lower for kw in KEYWORDS)
                
                if is_safety_flagged:
                    flagged += 1
                    lat, lng = get_coords_for_destination(dest, district)
                    nlp_res = nlp.analyze_text(review_text)
                    
                    scam_cat = nlp_res.get("scam_type") or "general"
                    risk_lvl = nlp_res.get("risk_level", 2)
                    
                    collected_records.append({
                        "source": "destination_reviews",
                        "source_weight": 0.60,  # Tier 2b weight
                        "title": f"Review of {dest}",
                        "content": review_text,
                        "url": f"https://maps.google.com/?q={lat},{lng}",
                        "latitude": lat,
                        "longitude": lng,
                        "location_name": f"{dest}, {district.title()}",
                        "scam_type": scam_cat,
                        "risk_level": risk_lvl,
                        "is_scam": 1 if nlp_res.get("is_scam") else 0,
                        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    })

            print(f"  Processed {count} total rows -> Flagged {flagged} safety-relevant records.")

    print(f"\n[Extraction Total] Extracted {len(collected_records)} unique safety-relevant destination records.")
    
    if collected_records:
        save_and_update_all(collected_records)


def save_and_update_all(records: list):
    # 1. Insert into SQLite Database
    db_path = os.path.join(os.path.dirname(__file__), "safety_heatmap.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    inserted_count = 0
    for r in records:
        try:
            cursor.execute("""
                INSERT INTO reports (
                    source, source_weight, title, content, url, latitude, longitude,
                    location_name, scam_type, risk_level, is_scam, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["source"], r["source_weight"], r["title"], r["content"], r["url"],
                r["latitude"], r["longitude"], r["location_name"], r["scam_type"],
                r["risk_level"], r["is_scam"], r["created_at"]
            ))
            inserted_count += 1
        except Exception:
            continue

    conn.commit()
    conn.close()
    print(f"[Database] Successfully inserted {inserted_count} new records into SQLite DB ({db_path}).")

    # 2. Append to primary master dataset CSV
    csv_path = os.path.join(os.path.dirname(__file__), "training", "dataset", "primary_master_dataset.csv")
    if os.path.exists(csv_path) and records:
        keys = records[0].keys()
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writerows(records)
        print(f"[Master Dataset] Appended {len(records)} records to {csv_path}.")


if __name__ == "__main__":
    process_destination_datasets()
