"""
ingest_reviews_csv.py
Ingest tourist safety incidents from e:\\research\\dataset\\Reviews.csv
(16,156 real TripAdvisor reviews with Title, Text, Location, Rating, etc.)

PIPELINE:
  1. Row must have title + text content
  2. Scam/safety type is re-classified from content (keyword-based, never trusted from CSV)
  3. Passes strict_filter (tourist context + negative signal)
  4. Coordinates resolved from city/location_name lookup table
  5. Original traceable TripAdvisor search URL generated for every record

Run from e:\\research\\backend:
    python ingest_reviews_csv.py
"""
import os
import sys
import csv
import sqlite3
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from data_pipeline.strict_filter import passes_strict_filter

CSV_PATH = r"e:\research\dataset\Reviews.csv"
DB_PATH  = os.path.join(os.path.dirname(__file__), "safety_heatmap.db")

# ── Coordinate lookup: city/location -> (lat, lon, district) ─────────────────
CITY_COORDS = {
    # Western Province
    "colombo":              (6.9271,  79.8612, "Colombo"),
    "mount lavinia":        (6.8389,  79.8653, "Colombo"),
    "negombo":              (7.2081,  79.8358, "Gampaha"),
    "gampaha":              (7.0840,  79.9925, "Gampaha"),
    "kalutara":             (6.5854,  79.9607, "Kalutara"),
    "beruwala":             (6.4771,  79.9843, "Kalutara"),
    "bentota":              (6.4244,  79.9966, "Galle"),
    "aluthgama":            (6.4335,  79.9966, "Kalutara"),
    # Southern Province
    "galle":                (6.0535,  80.2210, "Galle"),
    "unawatuna":            (6.0091,  80.2488, "Galle"),
    "hikkaduwa":            (6.1392,  80.1008, "Galle"),
    "ahangama":             (5.9766,  80.3570, "Galle"),
    "koggala":              (5.9985,  80.3279, "Galle"),
    "weligama":             (5.9742,  80.4291, "Matara"),
    "mirissa":              (5.9481,  80.4710, "Matara"),
    "matara":               (5.9549,  80.5550, "Matara"),
    "tangalle":             (6.0243,  80.7979, "Hambantota"),
    "hambantota":           (6.1247,  81.1185, "Hambantota"),
    "tissamaharama":        (6.2867,  81.2876, "Hambantota"),
    "kataragama":           (6.4143,  81.3304, "Monaragala"),
    # Central Province
    "kandy":                (7.2906,  80.6337, "Kandy"),
    "peradeniya":           (7.2680,  80.5958, "Kandy"),
    "pinnawala":            (7.3014,  80.3844, "Kegalle"),
    "nuwara eliya":         (6.9497,  80.7891, "Nuwara Eliya"),
    "haputale":             (6.7672,  80.9595, "Badulla"),
    "bandarawela":          (6.8311,  81.0014, "Badulla"),
    "ella":                 (6.8667,  81.0466, "Badulla"),
    "badulla":              (6.9931,  81.0549, "Badulla"),
    "hatton":               (6.8939,  80.5956, "Nuwara Eliya"),
    # North Central Province
    "anuradhapura":         (8.3114,  80.4037, "Anuradhapura"),
    "sigiriya":             (7.9573,  80.7600, "Matale"),
    "dambulla":             (7.8675,  80.6517, "Matale"),
    "habarana":             (8.0515,  80.7498, "Anuradhapura"),
    "polonnaruwa":          (7.9396,  81.0009, "Polonnaruwa"),
    "matale":               (7.4675,  80.6234, "Matale"),
    "saliyapura":           (8.3591,  80.4187, "Anuradhapura"),
    "mihintale":            (8.3511,  80.5114, "Anuradhapura"),
    "katukitula":           (7.9000,  80.7500, "Matale"),
    # Eastern Province
    "arugam bay":           (6.8401,  81.8303, "Ampara"),
    "ampara":               (7.2811,  81.6747, "Ampara"),
    "batticaloa":           (7.7170,  81.7000, "Batticaloa"),
    "trincomalee":          (8.5874,  81.2152, "Trincomalee"),
    "nilaveli":             (8.7000,  81.2000, "Trincomalee"),
    "pasikudah":            (7.9330,  81.5551, "Batticaloa"),
    # Northern Province
    "jaffna":               (9.6615,  80.0255, "Jaffna"),
    "mannar":               (8.9810,  79.9044, "Vanni (Mannar/Vavuniya/Mullaitivu)"),
    "vavuniya":             (8.7514,  80.4971, "Vanni (Mannar/Vavuniya/Mullaitivu)"),
    # North Western Province
    "kurunegala":           (7.4863,  80.3647, "Kurunegala"),
    "puttalam":             (8.0362,  79.8283, "Puttalam"),
    "kalpitiya":            (8.2300,  79.7700, "Puttalam"),
    # Sabaragamuwa Province
    "ratnapura":            (6.6828,  80.3992, "Ratnapura"),
    "kegalle":              (7.2513,  80.3464, "Kegalle"),
    "belihuloya":           (6.7250,  80.8250, "Ratnapura"),
    # Uva Province
    "monaragala":           (6.8731,  81.3507, "Monaragala"),
    "wellawaya":            (6.7333,  81.1000, "Monaragala"),
}

# ── Scam type re-classifier ───────────────────────────────────────────────────
SCAM_CLASSIFIERS = [
    ("Gem Scam",               ["gem scam","gem shop","sapphire","ruby","precious stone","fake gem","gem dealer","jewellery shop forced"]),
    ("Tuk-Tuk Scam",           ["tuk-tuk","tuk tuk","tuktuk","three-wheeler","three wheeler","trishaw"]),
    ("Fake Guide",             ["fake guide","unofficial guide","unlicensed guide","fake monk","fake ticket","fake entry","not a real guide"]),
    ("Overcharging",           ["overcharge","overcharged","overpriced","tourist price","tourist menu","double price",
                                "rip off","ripped off","extortion","inflated price","charged extra","extra charge",
                                "inflated bill","wrong price","too expensive for what","way overpriced"]),
    ("Transport Fraud",        ["taxi scam","taxi overcharge","airport taxi","meter covered","meter broken",
                                "refused meter","refused to use meter","transport scam","driver scam"]),
    ("Theft / Robbery",        ["pickpocket","pickpocketing","bag snatched","bag snatch","stolen","theft",
                                "robbed","robbery","mugged","mugging","purse snatched","phone stolen"]),
    ("Accommodation Scam",     ["accommodation scam","hotel scam","guesthouse scam","different property",
                                "misrepresented","booking fraud","double booked","bait and switch","not as advertised"]),
    ("Harassment",             ["harassed","harassment","stalked","following me","groped","catcalled",
                                "unwanted touching","aggressive tout","persistent tout","street harassment",
                                "uncomfortable with men","felt unsafe as a woman","male attention"]),
    ("Physical Assault",       ["assault","attacked","physical attack","punched","threatened with","knife","weapon","violence"]),
    ("Unsafe Area",            ["unsafe","dangerous area","avoid this area","crime hotspot","not safe at night",
                                "reported crime","high crime","do not go alone"]),
    ("Food / Restaurant Scam", ["no menu price","tourist menu","inflated food","bill shock","hidden charge",
                                "service charge","no prices shown","different price on bill"]),
    ("General Scam",           ["scam","scammed","fraud","fraudulent","cheated","con","conned",
                                "deceived","swindled","tricked","trick","avoid this"]),
]

HARD_EXCLUDE_CONTENT = [
    "flooded street","flood warning","flooding in","disaster management",
    "heavy rain","heavy showers","landslide warning","met department",
    "nbro","evacuation","sluice gate","dam release","tsunami","cyclone",
    "weather forecast","arrested","remanded","cid","court ordered","sentenced",
    "news1st","ada derana reported","government says","ministry announced",
]


def classify_scam(title: str, text: str):
    combined = (title + " " + text).lower()
    for excl in HARD_EXCLUDE_CONTENT:
        if excl in combined:
            return False, None, 1
    for label, keywords in SCAM_CLASSIFIERS:
        if any(kw in combined for kw in keywords):
            high_risk = ["assault","attacked","robbed","mugged","groped","knife","weapon","threatened","dangerous"]
            risk = 3 if any(kw in combined for kw in high_risk) else 2
            return True, label, risk
    return False, None, 1


def resolve_coords(location_name: str, city: str):
    """Try to resolve lat/lon/district from location or city."""
    for key in [location_name.lower(), city.lower()]:
        for lookup_key, val in CITY_COORDS.items():
            if lookup_key in key or key in lookup_key:
                return val[0], val[1], val[2]
    return None, None, None


def build_tripadvisor_url(title: str, location_name: str) -> str:
    query = f'site:tripadvisor.com "{title[:70]}"'
    return f"https://www.google.com/search?q={urllib.parse.quote(query)}&btnI=1"


def main():
    if not os.path.exists(CSV_PATH):
        print(f"[ERROR] CSV not found: {CSV_PATH}")
        return

    print("=" * 70)
    print("  INGESTING Reviews.csv (TripAdvisor) -> safety_heatmap.db")
    print("  STRICT FILTER + SCAM RE-CLASSIFICATION ACTIVE")
    print("=" * 70)

    total = 0
    skip_no_content = 0
    skip_no_coords = 0
    skip_not_scam = 0
    skip_filter = 0
    records = []
    seen = set()

    with open(CSV_PATH, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1

            title   = (row.get("Title") or "").strip()
            text    = (row.get("Text") or "").strip()
            if len(text) < 30:
                skip_no_content += 1
                continue

            loc_name = (row.get("Location_Name") or "").strip()
            city     = (row.get("Located_City") or "").strip()
            location = (row.get("Location") or "").strip()   # e.g. "Arugam Bay, Eastern Province"

            # Resolve coordinates
            lat, lon, district = resolve_coords(loc_name, city)
            if lat is None:
                # Try parsing the Location field city part
                city_fallback = location.split(",")[0].strip() if "," in location else city
                lat, lon, district = resolve_coords(city_fallback, city_fallback)
            if lat is None:
                skip_no_coords += 1
                continue

            # Re-classify scam type from content
            is_scam, scam_type, risk_lvl = classify_scam(title, text)
            if not is_scam:
                skip_not_scam += 1
                continue

            # Run strict tourist context filter
            if not passes_strict_filter(title, text):
                skip_filter += 1
                continue

            # Parse travel date
            travel_date = (row.get("Travel_Date") or row.get("Published_Date") or "").strip()
            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
                try:
                    created_at = datetime.strptime(travel_date[:10], fmt).strftime("%Y-%m-%d %H:%M:%S")
                    break
                except Exception:
                    pass

            # Helpful votes as peer credibility signal
            try:
                helpful = int(float(row.get("Helpful_Votes") or "0"))
            except Exception:
                helpful = 0

            full_location = f"{loc_name}, {district}" if district else loc_name
            url = build_tripadvisor_url(title, loc_name)

            fingerprint = f"{lat:.4f}|{lon:.4f}|{text[:80].lower()}"
            if fingerprint in seen:
                continue
            seen.add(fingerprint)

            records.append({
                "source":        "tripadvisor_csv",
                "source_weight": 0.75,
                "title":         title[:200],
                "content":       text,
                "url":           url,
                "latitude":      lat,
                "longitude":     lon,
                "location_name": full_location,
                "scam_type":     scam_type,
                "risk_level":    risk_lvl,
                "is_scam":       1,
                "helpful_votes": helpful,
                "created_at":    created_at,
            })

    print(f"[CSV] Total rows read           : {total:,}")
    print(f"[CSV] Skipped (no content)      : {skip_no_content:,}")
    print(f"[CSV] Skipped (no coordinates)  : {skip_no_coords:,}")
    print(f"[CSV] Skipped (not scam)        : {skip_not_scam:,}")
    print(f"[CSV] Skipped (strict filter)   : {skip_filter:,}")
    print(f"[CSV] Clean safety incidents    : {len(records):,}")

    if not records:
        print("[WARN] No records passed all filters.")
        return

    # ── Write to DB ──────────────────────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Check if helpful_votes column exists
    cur.execute("PRAGMA table_info(reports)")
    cols = [c[1] for c in cur.fetchall()]
    has_helpful = "helpful_votes" in cols

    # Clear old tripadvisor_csv records
    cur.execute("DELETE FROM reports WHERE source = 'tripadvisor_csv'")
    deleted = cur.rowcount
    print(f"[DB]  Cleared {deleted:,} old tripadvisor_csv records")

    inserted = 0
    for r in records:
        try:
            if has_helpful:
                cur.execute("""
                    INSERT INTO reports (
                        source, source_weight, title, content, url,
                        latitude, longitude, location_name,
                        scam_type, risk_level, is_scam, helpful_votes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r["source"], r["source_weight"], r["title"], r["content"], r["url"],
                    r["latitude"], r["longitude"], r["location_name"],
                    r["scam_type"], r["risk_level"], r["is_scam"], r["helpful_votes"], r["created_at"],
                ))
            else:
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

    # Summary breakdown
    type_counts = {}
    city_counts = {}
    for r in records:
        k = r["scam_type"] or "Unknown"
        type_counts[k] = type_counts.get(k, 0) + 1
        loc = r["location_name"].split(",")[0]
        city_counts[loc] = city_counts.get(loc, 0) + 1

    print(f"[DB]  Inserted {inserted:,} verified TripAdvisor safety records")
    print()
    print("[Scam type breakdown]:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:30s}: {c}")
    print()
    print("[Top locations]:")
    for loc, c in sorted(city_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {loc:30s}: {c}")
    print()
    print("Done. Backend will serve updated data immediately (--reload active).")


if __name__ == "__main__":
    main()
