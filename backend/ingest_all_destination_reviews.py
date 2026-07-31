"""
FULL Destination Reviews Ingestion — ALL Reviews, Not Just Scam-Flagged
IT22629180

CRITICAL FIX: Previously we only ingested reviews containing scam keywords.
This meant places like Ruwanwelisaya, Ambuluwawa, Ravana Falls etc. never
appeared on the map because their reviews were mostly positive.

NOW: We ingest EVERY review. Safe reviews get is_scam=0, risk_level=1.
Flagged reviews get properly classified. This ensures every destination
appears on the map with its actual safety status.
"""
import os
import csv
import sqlite3
from datetime import datetime, timezone

# ── Sri Lanka Location Coordinates ───────────────────────────────────────────
# District-level fallback coordinates
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
    "kurunagela":   (7.4863, 80.3647),  # alternate spelling in dataset
    "puttalam":     (8.0362, 79.8283),
    "anuradhapura": (8.3114, 80.4037),
    "polonnaruwa":  (7.9396, 81.0009),
    "badulla":      (6.9931, 81.0549),
    "monaragala":   (6.8731, 81.3507),
    "ratnapura":    (6.6828, 80.3992),
    "rathnapura":   (6.6828, 80.3992),  # alternate spelling in dataset
    "kegalle":      (7.2513, 80.3464),
    "hatton":       (6.8939, 80.5956),
    "kalmunai":     (7.4090, 81.8274),
}

# Destination-specific coordinates (higher precision than district)
DESTINATION_COORDS = {
    # Cultural Triangle
    "sigiriya":         (7.9573, 80.7600),
    "dambulla":         (7.8675, 80.6517),
    "anuradhapura":     (8.3114, 80.4037),
    "polonnaruwa":      (7.9396, 81.0009),
    "ruwanwelisaya":    (8.3480, 80.3964),
    "ruwanweli":        (8.3480, 80.3964),
    "thuparamaya":      (8.3533, 80.3963),
    "jetavanaramaya":   (8.3539, 80.4010),
    "abhayagiriya":     (8.3647, 80.3958),
    "isurumuniya":      (8.3360, 80.3910),
    "lovamahapaya":     (8.3478, 80.3970),
    "mihintale":        (8.3511, 80.5114),
    "medirigiriya":     (7.9975, 80.9747),
    "ritigala":         (8.1200, 80.6500),
    "arankele":         (7.6270, 80.5940),

    # Kandy & Central
    "kandy":            (7.2906, 80.6337),
    "temple of tooth":  (7.2936, 80.6413),
    "dalada maligawa":  (7.2936, 80.6413),
    "peradeniya":       (7.2680, 80.5958),
    "ambuluwawa":       (7.3544, 80.5353),
    "pinnawala":        (7.3014, 80.3844),
    "embekka":          (7.2145, 80.5720),
    "gadaladeniya":     (7.2275, 80.5432),
    "lankatilaka":      (7.2225, 80.5523),
    "bahirawakanda":    (7.2930, 80.6272),
    "hanthana":         (7.2587, 80.6178),
    "udawattakele":     (7.2950, 80.6400),

    # Hill Country
    "nuwara eliya":     (6.9497, 80.7891),
    "ella":             (6.8728, 81.0464),
    "nine arch bridge": (6.8770, 81.0590),
    "little adam":      (6.8650, 81.0475),
    "ravana":           (6.8400, 81.0480),
    "ravana waterfall": (6.8400, 81.0480),
    "ravana's cave":    (6.8414, 81.0475),
    "haputale":         (6.7667, 80.9667),
    "lipton":           (6.7960, 80.9900),
    "horton plains":    (6.8095, 80.8090),
    "world's end":      (6.7850, 80.7900),
    "baker's falls":    (6.8000, 80.8050),
    "adam's peak":      (6.8094, 80.4994),
    "sri pada":         (6.8094, 80.4994),
    "hatton":           (6.8939, 80.5956),
    "kitulgala":        (6.9897, 80.4164),
    "bambarakiri":      (6.7600, 80.8200),
    "diyaluma":         (6.7383, 81.0167),
    "bomburu ella":     (6.7947, 80.8822),

    # Southern Coast
    "galle fort":       (6.0283, 80.2170),
    "galle":            (6.0535, 80.2210),
    "unawatuna":        (5.9997, 80.2489),
    "mirissa":          (5.9483, 80.4716),
    "hikkaduwa":        (6.1395, 80.1061),
    "weligama":         (5.9748, 80.4282),
    "tangalle":         (6.0252, 80.7960),
    "bentota":          (6.4221, 80.0009),
    "matara":           (5.9549, 80.5550),
    "coconut tree hill": (5.9700, 80.4300),
    "mulkirigala":      (6.1167, 80.7333),
    "lighthouse - galle": (6.0283, 80.2160),

    # Western Province
    "colombo fort":     (6.9344, 79.8428),
    "colombo":          (6.9271, 79.8612),
    "pettah":           (6.9358, 79.8535),
    "galle face":       (6.9228, 79.8449),
    "mount lavinia":    (6.8297, 79.8661),
    "negombo":          (7.2083, 79.8358),
    "dehiwala":         (6.8505, 79.8650),
    "crow island":      (6.9550, 79.8450),
    "gangarama":        (6.9167, 79.8567),
    "bellagio":         (6.9200, 79.8500),
    "casino marina":    (6.9180, 79.8460),
    "viharamahadevi":   (6.9150, 79.8620),
    "kelaniya":         (6.9503, 79.9194),
    "barberyn":         (6.4433, 80.0567),

    # Eastern Coast
    "arugam bay":       (6.8399, 81.8325),
    "trincomalee":      (8.5874, 81.2152),
    "nilaveli":         (8.6700, 81.1953),
    "pasikudah":        (7.9311, 81.5567),
    "batticaloa":       (7.7170, 81.7000),

    # Northern
    "jaffna":           (9.6615, 80.0255),
    "nallur":           (9.6690, 80.0220),
    "nagadeepa":        (9.7472, 79.9597),

    # National Parks & Wildlife
    "yala":             (6.3667, 81.5167),
    "udawalawe":        (6.4544, 80.8856),
    "wilpattu":         (8.4500, 80.0500),
    "minneriya":        (8.0333, 80.9000),
    "bundala":          (6.1950, 81.2097),
    "kumana":           (6.5833, 81.7000),
    "sinharaja":        (6.4167, 80.5000),
    "knuckles":         (7.4000, 80.7667),

    # Other Popular
    "matale":           (7.4675, 80.6234),
    "kurunegala":       (7.4863, 80.3647),
    "ratnapura":        (6.6828, 80.3992),
    "kalpitiya":        (8.2333, 79.7667),
    "tissamaharama":    (6.2833, 81.2833),
    "kataragama":       (6.4100, 81.3300),
    "buduruwagala":     (6.7500, 81.0833),
    "bopath":           (6.7917, 80.4583),
}

SAFETY_KEYWORDS = [
    "scam", "fraud", "fake", "overcharge", "trap", "dangerous",
    "cheat", "rip off", "ripped off", "mafia", "assault", "harassment",
    "overpriced", "tricking", "pickpocket", "stolen", "theft", "robbed",
    "mugged", "harassed", "unsafe", "threatened", "attacked", "groped",
    "stalked", "creep", "tourist price", "double price", "extortion",
]


def get_coords(dest_name: str, district_name: str):
    """Resolve coordinates: destination name first, then district fallback."""
    dest_lower = (dest_name or "").lower().strip()
    dist_lower = (district_name or "").lower().strip()

    # Try destination-specific match
    for key, coords in DESTINATION_COORDS.items():
        if key in dest_lower:
            return coords[0], coords[1]

    # Fallback to district
    if dist_lower in DISTRICT_COORDS:
        return DISTRICT_COORDS[dist_lower]

    return 6.9271, 79.8612  # Default: Colombo


def classify_review(text: str):
    """
    Lightweight classification without loading heavy NLP models.
    Returns (is_scam, scam_type, risk_level).
    """
    text_lower = (text or "").lower()

    # Check for safety keywords
    matched = [kw for kw in SAFETY_KEYWORDS if kw in text_lower]

    if not matched:
        return 0, "safe", 1  # Not a scam, safe, low risk

    # Determine scam category from matched keywords
    scam_map = {
        "overcharge": "Overcharging", "overpriced": "Overcharging",
        "tourist price": "Overcharging", "double price": "Overcharging",
        "extortion": "Overcharging", "rip off": "Overcharging",
        "ripped off": "Overcharging",
        "scam": "General Scam", "fraud": "General Scam",
        "fake": "Fake Guide", "tricking": "General Scam",
        "pickpocket": "Theft / Robbery", "stolen": "Theft / Robbery",
        "theft": "Theft / Robbery", "robbed": "Theft / Robbery",
        "mugged": "Theft / Robbery",
        "harassed": "Harassment", "harassment": "Harassment",
        "stalked": "Harassment", "creep": "Harassment",
        "groped": "Harassment",
        "assault": "Physical Assault", "attacked": "Physical Assault",
        "unsafe": "Unsafe Area", "dangerous": "Unsafe Area",
        "threatened": "Unsafe Area", "mafia": "Unsafe Area",
        "trap": "General Scam", "cheat": "General Scam",
    }

    scam_type = "General Scam"
    for kw in matched:
        if kw in scam_map:
            scam_type = scam_map[kw]
            break

    # Risk level based on severity
    high_risk = ["assault", "attacked", "robbed", "mugged", "groped", "mafia", "threatened"]
    if any(kw in matched for kw in high_risk):
        risk_level = 3
    elif len(matched) >= 2:
        risk_level = 2
    else:
        risk_level = 2

    return 1, scam_type, risk_level


def ingest_all_reviews():
    """Ingest ALL reviews from both destination review CSVs into the database."""
    base_dir = os.path.dirname(os.path.dirname(__file__))

    files = [
        os.path.join(base_dir, "Destination Reviews (final).csv"),
        os.path.join(base_dir, "Destination Reviews_(raw).csv"),
    ]

    all_records = []
    seen = set()  # Deduplication

    print("=" * 70)
    print("  FULL DESTINATION REVIEW INGESTION (ALL REVIEWS)")
    print("  Every destination will appear on the map.")
    print("=" * 70)

    for filepath in files:
        if not os.path.exists(filepath):
            print(f"[Warning] Not found: {filepath}")
            continue

        fname = os.path.basename(filepath)
        print(f"\n[Reading] {fname}...")

        with open(filepath, encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            file_total = 0
            file_safe = 0
            file_flagged = 0

            for row in reader:
                dest = row.get("Destination", "").strip()
                district = row.get("District", "").strip()
                review = row.get("Review", "").strip()

                if not review or len(review) < 10:
                    continue

                # Deduplicate
                key = f"{dest.lower()}|{review[:80].lower()}"
                if key in seen:
                    continue
                seen.add(key)

                file_total += 1
                lat, lng = get_coords(dest, district)
                is_scam, scam_type, risk_level = classify_review(review)

                if is_scam:
                    file_flagged += 1
                else:
                    file_safe += 1

                all_records.append({
                    "source": "destination_reviews",
                    "source_weight": 0.60,
                    "title": f"Review: {dest}",
                    "content": review,
                    "url": f"https://maps.google.com/?q={lat},{lng}",
                    "latitude": lat,
                    "longitude": lng,
                    "location_name": f"{dest}, {district.title()}" if district else dest,
                    "scam_type": scam_type,
                    "risk_level": risk_level,
                    "is_scam": is_scam,
                    "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                })

        print(f"  {fname}: {file_total} unique reviews ({file_safe} safe + {file_flagged} flagged)")

    print(f"\n[Total] {len(all_records)} unique reviews across both files")

    if all_records:
        save_to_db(all_records)


def save_to_db(records: list):
    """Insert records into SQLite, skipping exact duplicates."""
    db_path = os.path.join(os.path.dirname(__file__), "safety_heatmap.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # First, remove old destination_reviews entries to avoid duplication on re-runs
    cur.execute("DELETE FROM reports WHERE source = 'destination_reviews'")
    deleted = cur.rowcount
    print(f"[DB] Cleared {deleted} old 'destination_reviews' records.")

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
        except Exception as e:
            continue

    conn.commit()
    conn.close()

    print(f"[DB] Inserted {inserted} destination reviews into {db_path}")

    # Summary stats
    safe_count = sum(1 for r in records if r["is_scam"] == 0)
    scam_count = sum(1 for r in records if r["is_scam"] == 1)
    unique_locations = len(set(r["location_name"] for r in records))
    print(f"[Summary] {unique_locations} unique destinations on the map")
    print(f"[Summary] {safe_count} safe reviews + {scam_count} scam-flagged reviews")


if __name__ == "__main__":
    ingest_all_reviews()
