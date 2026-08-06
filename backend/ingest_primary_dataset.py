"""
ingest_primary_dataset.py
Ingest rows from primary_master_dataset_clean.csv into safety_heatmap.db.

STRICT PIPELINE:
  1. Row must have geographic coordinates (lat/lon)
  2. Row must pass the strict_filter (tourist context + negative signal + no exclusions)
  3. Scam type is RE-CLASSIFIED from content using keyword matching — never trusted from CSV
  4. is_scam is set TRUE only when content contains a real scam/safety signal
  5. Natural disaster / flood / political news is EXCLUDED
  6. Every record gets a traceable Google search URL

Run from e:\\research\\backend:
    python ingest_primary_dataset.py
"""
import os
import sys
import csv
import sqlite3
import urllib.parse
from datetime import datetime, timezone

# Add backend root so we can import strict_filter
sys.path.insert(0, os.path.dirname(__file__))
from data_pipeline.strict_filter import passes_strict_filter

CSV_PATH = os.path.join(os.path.dirname(__file__), "training", "dataset", "primary_master_dataset_clean.csv")
DB_PATH  = os.path.join(os.path.dirname(__file__), "safety_heatmap.db")

# ── Hard exclusion patterns specific to ingestion (supplement strict_filter) ──
# These catch non-tourist content that the CSV wrongly labels as safety incidents.
INGEST_EXCLUSIONS = [
    # Natural disasters / weather — NOT tourist scams
    "flooded street", "flood warning", "flooding in", "ferried across",
    "flood water", "water level", "river level", "landslide warning",
    "heavy rain", "heavy showers", "incessant rain", "met department",
    "meteorological", "nbro", "disaster management", "evacuation",
    "sluice gate", "dam release", "cyclone", "tsunami warning",
    "low pressure", "weather forecast", "showers expected",
    # Political / govt news
    "parliament session", "cabinet meeting", "prime minister",
    "president signed", "passed in parliament",
    # Crime news (NOT tourist-facing)
    "arrested", "remanded", "police investigation", "cid",
    "court ordered", "bail denied", "sentenced to",
    # General news (not traveller experiences)
    "news1st", "ada derana reported", "daily mirror reported",
    "colombo gazette", "government says", "ministry announced",
]

# ── Scam type re-classifier (overrides CSV label — never trust CSV scam_type) ──
SCAM_CLASSIFIERS = [
    # Highest specificity first
    ("Gem Scam",           ["gem scam", "gem shop", "sapphire", "ruby", "precious stone", "fake gem", "gem dealer", "jewel"]),
    ("Tuk-Tuk Scam",       ["tuk-tuk", "tuk tuk", "tuktuk", "three-wheeler", "three wheeler", "trishaw"]),
    ("Fake Guide",         ["fake guide", "unofficial guide", "unlicensed guide", "fake monk", "fake ticket", "fake entry"]),
    ("Overcharging",       ["overcharge", "overcharged", "overpriced", "tourist price", "tourist menu",
                             "double price", "rip off", "ripped off", "extortion", "inflated price",
                             "charged extra", "extra charge", "inflated bill", "wrong price"]),
    ("Transport Fraud",    ["taxi scam", "taxi overcharge", "airport taxi", "meter covered", "meter broken",
                             "refused meter", "metered taxi", "refused to use meter", "transport scam"]),
    ("Theft / Robbery",    ["pickpocket", "pickpocketing", "bag snatched", "bag snatch", "stolen", "theft",
                             "robbed", "robbery", "mugged", "mugging", "purse snatched"]),
    ("Accommodation Scam", ["accommodation scam", "hotel scam", "guesthouse scam", "different property",
                             "misrepresented photos", "booking fraud", "double booked", "bait and switch"]),
    ("Harassment",         ["harassed", "harassment", "stalked", "following me", "groped", "catcalled",
                             "unwanted touching", "aggressive tout", "persistent tout", "street harassment"]),
    ("Physical Assault",   ["assault", "attacked", "physical attack", "punched", "threatened with",
                             "knife", "weapon"]),
    ("Unsafe Area",        ["unsafe", "dangerous area", "avoid this area", "crime hotspot", "not safe",
                             "reported crime", "high crime"]),
    ("Food / Restaurant Scam", ["food scam", "restaurant scam", "no menu price", "tourist menu",
                                 "inflated food", "bill shock", "hidden charge", "service charge"]),
    ("General Scam",       ["scam", "scammed", "fraud", "fraudulent", "cheated", "con", "conned",
                             "deceived", "swindled", "tricked", "trick"]),
]

def classify_scam(content: str):
    """
    Re-classify scam type from raw content.
    Returns (is_scam: bool, scam_type: str | None, risk_level: int)
    """
    text = content.lower()

    # Check for disaster/non-scam exclusions first
    for excl in INGEST_EXCLUSIONS:
        if excl in text:
            return False, None, 1

    # Try to match a specific scam type
    for label, keywords in SCAM_CLASSIFIERS:
        if any(kw in text for kw in keywords):
            # Determine risk level
            high_risk_keywords = ["assault", "attacked", "robbed", "mugged", "groped",
                                  "knife", "weapon", "threatened", "gang", "dangerous"]
            if any(kw in text for kw in high_risk_keywords):
                risk = 3
            elif label in ("Gem Scam", "Transport Fraud", "Fake Guide", "Theft / Robbery"):
                risk = 2
            else:
                risk = 2
            return True, label, risk

    # No specific scam match — not a scam
    return False, None, 1


def build_search_url(title: str, location: str, source_label: str) -> str:
    """Build a traceable Google search URL for the record."""
    if "tripadvisor" in source_label.lower():
        query = f'site:tripadvisor.com "{title[:60]}"'
    elif "reddit" in source_label.lower():
        query = f'site:reddit.com "{title[:60]}" Sri Lanka'
    elif "adaderana" in source_label.lower():
        query = f'site:adaderana.lk {title[:60]}'
    elif "google_maps" in source_label.lower():
        query = f'"{title[:60]}" {location} site:google.com/maps'
    else:
        query = f'"{title[:60]}" {location} Sri Lanka tourist safety'
    return f"https://www.google.com/search?q={urllib.parse.quote(query)}&btnI=1"

SOURCE_MAP = {
    "Reviews.csv": "tripadvisor_csv",
    "tripadvisor_csv": "tripadvisor_csv",
    "tripadvisor": "tripadvisor_csv",
    "reddit": "reddit",
    "youtube": "youtube",
    "google_news": "google_news",
    "google_maps": "google_maps",
    "adaderana": "adaderana",
    "tourist_police_lk": "tourist_police_lk",
}

def normalise_source(raw: str) -> str:
    for key, val in SOURCE_MAP.items():
        if key.lower() in raw.lower():
            return val
    return "dataset_csv"


def main():
    if not os.path.exists(CSV_PATH):
        print(f"[ERROR] CSV not found: {CSV_PATH}")
        return

    print("=" * 70)
    print("  INGESTING primary_master_dataset_clean.csv -> safety_heatmap.db")
    print("  STRICT FILTER + SCAM RE-CLASSIFICATION ACTIVE")
    print("=" * 70)

    total = 0
    skip_coords = 0
    skip_filter = 0
    skip_not_scam = 0
    skip_disaster = 0
    records = []
    seen = set()

    with open(CSV_PATH, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1

            # 1. Must have coordinates
            try:
                lat = float(row.get("lat") or "")
                lon = float(row.get("lon") or "")
                if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                    raise ValueError
            except (ValueError, TypeError):
                skip_coords += 1
                continue

            content = (row.get("text_content") or "").strip()
            if len(content) < 30:
                continue

            title_raw = content[:120].replace("\n", " ").strip()
            location_name = (row.get("location_name") or row.get("city") or "Sri Lanka").strip()
            district      = (row.get("district") or "").strip()
            source_raw    = (row.get("dataset_source") or "dataset_csv").strip()
            source        = normalise_source(source_raw)
            date_str      = (row.get("date") or "").strip()

            # 2. Re-classify scam from content (ignore CSV label)
            is_scam, scam_type, risk_lvl = classify_scam(content)

            if not is_scam:
                skip_not_scam += 1
                continue

            # 3. Run strict tourist relevance filter
            if not passes_strict_filter(title_raw, content):
                skip_filter += 1
                continue

            # 4. Parse date
            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
                try:
                    dt = datetime.strptime(date_str[:10], fmt)
                    created_at = dt.strftime("%Y-%m-%d %H:%M:%S")
                    break
                except Exception:
                    pass

            full_location = f"{location_name}, {district.title()}" if district else location_name
            url = build_search_url(title_raw, full_location, source)

            # 5. Dedup
            fingerprint = f"{lat:.4f}|{lon:.4f}|{content[:80].lower()}"
            if fingerprint in seen:
                continue
            seen.add(fingerprint)

            records.append({
                "source":        source,
                "source_weight": 0.75 if "tripadvisor" in source else 0.55,
                "title":         title_raw,
                "content":       content,
                "url":           url,
                "latitude":      lat,
                "longitude":     lon,
                "location_name": full_location,
                "scam_type":     scam_type,
                "risk_level":    risk_lvl,
                "is_scam":       1,
                "created_at":    created_at,
            })

    print(f"[CSV] Total rows read           : {total:,}")
    print(f"[CSV] Skipped (no coords)       : {skip_coords:,}")
    print(f"[CSV] Skipped (not scam content): {skip_not_scam:,}")
    print(f"[CSV] Skipped (strict filter)   : {skip_filter:,}")
    print(f"[CSV] Clean safety incidents    : {len(records):,}")

    if not records:
        print("[WARN] No records passed all filters.")
        return

    # ── Write to DB ──────────────────────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cur.execute("DELETE FROM reports WHERE source IN ('tripadvisor_csv', 'dataset_csv')")
    deleted = cur.rowcount
    print(f"[DB]  Cleared {deleted:,} old dataset records")

    inserted = 0
    for r in records:
        try:
            cur.execute("""
                INSERT INTO reports (
                    source, source_weight, title, content, url,
                    latitude, longitude, location_name,
                    scam_type, risk_level, is_scam, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["source"], r["source_weight"], r["title"], r["content"], r["url"],
                r["latitude"], r["longitude"], r["location_name"],
                r["scam_type"], r["risk_level"], r["is_scam"], r["created_at"],
            ))
            inserted += 1
        except Exception:
            continue

    conn.commit()
    conn.close()

    # Summary
    type_counts = {}
    for r in records:
        k = r["scam_type"] or "Unknown"
        type_counts[k] = type_counts.get(k, 0) + 1

    print(f"[DB]  Inserted {inserted:,} verified safety records")
    print()
    print("[Scam type breakdown]:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:30s}: {c}")
    print()
    print("Done. The backend will serve updated data immediately (--reload active).")


if __name__ == "__main__":
    main()
