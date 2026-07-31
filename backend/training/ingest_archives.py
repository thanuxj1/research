"""
Ingest Archive Datasets for SafeTravel LK ML Pipeline
IT22629180

Processes archive datasets:
  1. archive (4)/news.csv: Filter 11,000+ safety, scam, crime & tourist incident news
  2. archive (2)/Destination Reviews (final).csv: 37,000+ Sri Lanka tourist location reviews
  3. Reviews.csv: 16,000+ location & safety reviews

Merges and auto-labels all data into expanded_training_data.csv and populates sample_data.csv.
"""
import os
import sys
import csv
import re
import sqlite3
import pandas as pd

# Add backend root to sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH_DIR = os.path.dirname(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from training.generate_training_data import label_text

# Paths
NEWS_CSV = os.path.join(RESEARCH_DIR, "archive (4)", "news.csv")
DEST_REVIEWS_CSV = os.path.join(RESEARCH_DIR, "archive (2)", "Destination Reviews (final).csv")
REVIEWS_CSV = os.path.join(RESEARCH_DIR, "Reviews.csv")
OUTPUT_CSV = os.path.join(BACKEND_DIR, "training", "dataset", "sample_data.csv")
EXPANDED_CSV = os.path.join(BACKEND_DIR, "training", "dataset", "expanded_training_data.csv")
DB_PATH = os.path.join(BACKEND_DIR, "safety_heatmap.db")

SAFETY_NEWS_KEYWORDS = [
    "tourist", "foreigner", "scam", "robbery", "attack", "accident",
    "drowned", "cheated", "stolen", "harassed", "travel advisory", "crime",
    "fraud", "theft", "bribe", "overcharged", "tuk tuk", "hotel scam", "beach",
    "drowning", "warning", "police", "arrested", "smuggling", "extortion"
]


def ingest_news():
    print("\n[1/4] Processing news.csv from archive (4)...")
    if not os.path.exists(NEWS_CSV):
        print(f"  [WARN] News CSV not found at {NEWS_CSV}")
        return []

    rows = []
    scam_cnt = 0
    safe_cnt = 0

    with open(NEWS_CSV, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for r in reader:
            heading = (r.get("heading") or "").strip()
            content = (r.get("content") or "").strip()
            full_text = f"{heading}. {content}"
            text_lower = full_text.lower()

            # Check if relevant to tourist safety/crime/scam/incidents
            if any(kw in text_lower for kw in SAFETY_NEWS_KEYWORDS):
                if len(full_text) < 30:
                    continue
                # Truncate to reasonable length for training
                clean_text = full_text[:1500].replace('"', "'")
                is_scam, scam_type, sentiment = label_text(text_lower[:2000])

                rows.append({
                    "text": clean_text,
                    "is_scam": is_scam,
                    "scam_type": scam_type,
                    "sentiment": sentiment,
                    "source": "news_archive",
                })
                if is_scam:
                    scam_cnt += 1
                else:
                    safe_cnt += 1

    print(f"      -> Extracted {len(rows)} safety-relevant news items (Scams: {scam_cnt}, Safe/General: {safe_cnt})")
    return rows


def ingest_destination_reviews():
    print("\n[2/4] Processing Destination Reviews (final).csv from archive (2)...")
    if not os.path.exists(DEST_REVIEWS_CSV):
        print(f"  [WARN] Destination Reviews CSV not found at {DEST_REVIEWS_CSV}")
        return []

    rows = []
    scam_cnt = 0
    safe_cnt = 0

    with open(DEST_REVIEWS_CSV, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for r in reader:
            dest = (r.get("Destination") or "").strip()
            district = (r.get("District") or "").strip()
            review = (r.get("Review") or "").strip()

            if len(review) < 15:
                continue

            full_text = f"[{dest}, {district}] {review}"
            clean_text = full_text[:1500].replace('"', "'")
            text_lower = full_text.lower()

            is_scam, scam_type, sentiment = label_text(text_lower)

            rows.append({
                "text": clean_text,
                "is_scam": is_scam,
                "scam_type": scam_type,
                "sentiment": sentiment,
                "source": "destination_reviews",
            })
            if is_scam:
                scam_cnt += 1
            else:
                safe_cnt += 1

    print(f"      -> Extracted {len(rows)} destination reviews (Scams: {scam_cnt}, Safe/General: {safe_cnt})")
    return rows


def ingest_reviews_csv():
    print("\n[3/4] Processing Reviews.csv...")
    if not os.path.exists(REVIEWS_CSV):
        print(f"  [WARN] Reviews.csv not found at {REVIEWS_CSV}")
        return []

    rows = []
    scam_cnt = 0
    safe_cnt = 0

    with open(REVIEWS_CSV, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for r in reader:
            location = (r.get("Location_Name") or "").strip()
            city = (r.get("Located_City") or "").strip()
            title = (r.get("Title") or "").strip()
            text = (r.get("Text") or "").strip()

            if len(text) < 15:
                continue

            full_text = f"[{location}, {city}] {title} - {text}"
            clean_text = full_text[:1500].replace('"', "'")
            text_lower = full_text.lower()

            is_scam, scam_type, sentiment = label_text(text_lower)

            rows.append({
                "text": clean_text,
                "is_scam": is_scam,
                "scam_type": scam_type,
                "sentiment": sentiment,
                "source": "reviews_csv",
            })
            if is_scam:
                scam_cnt += 1
            else:
                safe_cnt += 1

    print(f"      -> Extracted {len(rows)} reviews (Scams: {scam_cnt}, Safe/General: {safe_cnt})")
    return rows


def main():
    print("=" * 60)
    print("  Ingesting Archive Datasets into Training Pipeline")
    print("  SafeTravel LK / IT22629180")
    print("=" * 60)

    news_rows = ingest_news()
    dest_rows = ingest_destination_reviews()
    reviews_rows = ingest_reviews_csv()

    all_rows = news_rows + dest_rows + reviews_rows
    print(f"\n[4/4] Total merged samples collected: {len(all_rows)}")

    if not all_rows:
        print("[ERROR] No data collected.")
        return

    # Write to expanded_training_data.csv and sample_data.csv
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)

    fieldnames = ["text", "is_scam", "scam_type", "sentiment", "source"]

    with open(EXPANDED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    # For compatibility with sample_data.csv (strip source)
    sample_fieldnames = ["text", "is_scam", "scam_type", "sentiment"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sample_fieldnames)
        writer.writeheader()
        for r in all_rows:
            writer.writerow({
                "text": r["text"],
                "is_scam": r["is_scam"],
                "scam_type": r["scam_type"],
                "sentiment": r["sentiment"],
            })

    scam_total = sum(1 for r in all_rows if r["is_scam"] == 1)
    safe_total = len(all_rows) - scam_total

    print("\n" + "=" * 60)
    print("  INGESTION COMPLETE!")
    print(f"  Dataset saved to: {EXPANDED_CSV}")
    print(f"  Dataset saved to: {OUTPUT_CSV}")
    print(f"  Total records:    {len(all_rows):,}")
    print(f"  Scam reports (1): {scam_total:,} ({scam_total/len(all_rows):.1%})")
    print(f"  Safe reports (0): {safe_total:,} ({safe_total/len(all_rows):.1%})")
    print("=" * 60)


if __name__ == "__main__":
    main()
