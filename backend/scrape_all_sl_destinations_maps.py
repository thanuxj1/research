"""
Google Maps ALL Reviews Scraper — Sri Lanka Full Coverage
IT22629180

DESIGN: Ingest ALL reviews (safe + unsafe) from Google Maps via Apify.
Every tourist destination must appear on the map regardless of whether
it has scam reports or not. Safe destinations are just as important —
they show tourists where it IS safe to go.

This script also retrieves data from previously completed Apify runs.
"""
import os
import sqlite3
import csv
from datetime import datetime, timezone
from apify_client import ApifyClient
from app.core.config import settings

# ── Comprehensive search queries covering ALL Sri Lanka tourist spots ────────
ALL_SL_QUERIES = [
    # Cultural Triangle (UNESCO)
    "Sigiriya rock fortress Sri Lanka",
    "Dambulla cave temple Sri Lanka",
    "Anuradhapura sacred city Sri Lanka",
    "Polonnaruwa ancient city Sri Lanka",
    "Ruwanwelisaya stupa Anuradhapura",
    "Jetavanaramaya Anuradhapura",
    "Abhayagiriya Anuradhapura",
    "Isurumuniya temple Anuradhapura",
    "Thuparamaya Anuradhapura",
    "Mihintale Sri Lanka",
    "Ritigala monastery Sri Lanka",
    "Medirigiriya vatadage Sri Lanka",

    # Kandy & Central Highlands
    "Temple of the Tooth Kandy Sri Lanka",
    "Kandy Lake Sri Lanka",
    "Peradeniya botanical garden Sri Lanka",
    "Ambuluwawa tower Gampola Sri Lanka",
    "Bahirawakanda Buddha Kandy",
    "Udawattakele forest Kandy",
    "Hanthana mountain Kandy",
    "Embekka Devalaya Kandy",
    "Gadaladeniya temple Kandy",
    "Lankatilaka temple Kandy",
    "Pinnawala elephant orphanage Sri Lanka",

    # Hill Country
    "Ella Sri Lanka tourist",
    "Nine Arch Bridge Ella Sri Lanka",
    "Little Adams Peak Ella",
    "Ravana waterfall Ella Sri Lanka",
    "Ravana cave Ella Sri Lanka",
    "Nuwara Eliya Sri Lanka",
    "Horton Plains world end Sri Lanka",
    "Haputale Lipton Seat Sri Lanka",
    "Adams Peak Sri Pada Sri Lanka",
    "Knuckles mountain range Sri Lanka",
    "Bambarakiri ella waterfall",
    "Diyaluma waterfall Sri Lanka",
    "Bomburu ella waterfall",
    "Kitulgala white water rafting",
    "Matale spice garden Sri Lanka",

    # Southern Coast
    "Galle Fort Sri Lanka",
    "Galle Dutch Fort lighthouse",
    "Unawatuna beach Sri Lanka",
    "Mirissa beach whale watching",
    "Hikkaduwa beach coral reef",
    "Weligama beach surfing Sri Lanka",
    "Tangalle beach Sri Lanka",
    "Bentota beach water sports",
    "Coconut Tree Hill Mirissa",
    "Mulkirigala temple Sri Lanka",
    "Dikwella temple Wewurukannala",

    # Wildlife & National Parks
    "Yala national park safari Sri Lanka",
    "Udawalawe national park elephant",
    "Wilpattu national park Sri Lanka",
    "Minneriya national park elephant gathering",
    "Bundala national park Sri Lanka",
    "Sinharaja rainforest Sri Lanka",
    "Kumana national park Sri Lanka",

    # Western Province
    "Colombo tourist attractions",
    "Gangaramaya temple Colombo",
    "Galle Face Green Colombo",
    "National Museum Colombo",
    "Pettah market Colombo",
    "Mount Lavinia beach Colombo",
    "Negombo beach fish market",
    "Kelaniya temple Sri Lanka",
    "Crow Island beach park",
    "Dehiwala zoo Colombo",
    "Viharamahadevi park Colombo",

    # Eastern Coast
    "Arugam Bay surfing Sri Lanka",
    "Trincomalee beach Nilaveli",
    "Pasikudah beach Sri Lanka",
    "Pigeon Island Trincomalee",
    "Koneswaram temple Trincomalee",

    # Northern Province
    "Jaffna tourist places Sri Lanka",
    "Nallur Kandaswamy temple Jaffna",
    "Jaffna Fort Sri Lanka",
    "Nagadeepa island temple",
    "Casuarina beach Jaffna",

    # Other Popular
    "Kalpitiya kitesurfing dolphins",
    "Tissamaharama lake stupa",
    "Kataragama temple Sri Lanka",
    "Buduruwagala statues Sri Lanka",
    "Ratnapura gem museum Sri Lanka",
    "Bopath waterfall Ratnapura",
]

SAFETY_KEYWORDS = [
    "scam", "fraud", "fake", "overcharge", "trap", "dangerous",
    "cheat", "rip off", "ripped off", "mafia", "assault", "harassment",
    "overpriced", "tricking", "pickpocket", "stolen", "theft", "robbed",
    "mugged", "harassed", "unsafe", "threatened", "attacked",
]


def safe_int(val, default=0):
    """Safely convert a value to int (Apify sometimes returns strings)."""
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def safe_float(val, default=0.0):
    """Safely convert a value to float."""
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def classify_review_text(text, rating):
    """Lightweight classification without heavy NLP models."""
    text_lower = (text or "").lower()
    matched = [kw for kw in SAFETY_KEYWORDS if kw in text_lower]

    if not matched and rating > 2:
        return 0, "safe", 1  # Safe review

    if matched or (rating > 0 and rating <= 2):
        scam_map = {
            "overcharge": "Overcharging", "overpriced": "Overcharging",
            "rip off": "Overcharging", "ripped off": "Overcharging",
            "scam": "General Scam", "fraud": "General Scam",
            "fake": "Fake Guide", "cheat": "General Scam",
            "pickpocket": "Theft", "stolen": "Theft",
            "theft": "Theft", "robbed": "Theft", "mugged": "Theft",
            "harassed": "Harassment", "harassment": "Harassment",
            "assault": "Physical Assault", "attacked": "Physical Assault",
            "unsafe": "Unsafe Area", "dangerous": "Unsafe Area",
            "threatened": "Unsafe Area", "mafia": "Unsafe Area",
            "trap": "General Scam",
        }
        scam_type = "General Scam"
        for kw in matched:
            if kw in scam_map:
                scam_type = scam_map[kw]
                break
        return 1, scam_type, 2 if len(matched) < 2 else 3

    return 0, "safe", 1


def scrape_and_ingest(max_places: int = 3, max_reviews: int = 15, dataset_id: str = None):
    """
    Main function: scrape Google Maps via Apify OR process an existing dataset.
    Ingests ALL reviews (safe + unsafe) into the database.
    """
    token = settings.APIFY_API_TOKEN
    if not token:
        print("[Error] APIFY_API_TOKEN missing in .env")
        return

    client = ApifyClient(token)

    print("=" * 70)
    print("  GOOGLE MAPS FULL COVERAGE SCRAPER (ALL REVIEWS)")
    print(f"  Queries: {len(ALL_SL_QUERIES)} | Max places/query: {max_places}")
    print("=" * 70)

    # Either use existing dataset or run a new scrape
    if dataset_id:
        print(f"\n[Apify] Using existing dataset: {dataset_id}")
    else:
        actor_id = "compass/crawler-google-places"
        run_input = {
            "searchStringsArray": ALL_SL_QUERIES,
            "maxCrawledPlacesPerSearch": max_places,
            "maxReviews": max_reviews,
            "language": "en",
            "reviewsSort": "newest",
        }
        print(f"\n[Apify] Launching scraper for {len(ALL_SL_QUERIES)} search queries...")
        run = client.actor(actor_id).call(run_input=run_input)
        dataset_id = run.get("defaultDatasetId")
        print(f"[Apify] Scrape complete! Dataset: {dataset_id}")

    # Process the dataset — ingest ALL reviews
    records = []
    places_count = 0

    for item in client.dataset(dataset_id).iterate_items():
        places_count += 1
        place_name = item.get("title") or item.get("name") or "Unknown Place"
        reviews = item.get("reviews", [])
        lat = safe_float(item.get("location", {}).get("lat") or item.get("lat"))
        lng = safe_float(item.get("location", {}).get("lng") or item.get("lng"))
        place_url = item.get("url", "")
        address = item.get("address", "") or place_name
        total_score = safe_float(item.get("totalScore"))

        if not lat or not lng:
            continue  # Skip places without coordinates

        # If place has no reviews, still add it as a known destination
        if not reviews:
            records.append({
                "source": "google_maps",
                "source_weight": 0.62,
                "title": f"Google Maps: {place_name}",
                "content": f"{place_name} - Tourist destination. Overall rating: {total_score}/5.",
                "url": place_url,
                "latitude": lat,
                "longitude": lng,
                "location_name": address[:120],
                "scam_type": "safe",
                "risk_level": 1,
                "is_scam": 0,
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            })
            continue

        # Process ALL reviews for this place
        for rev in reviews:
            text = rev.get("text") or rev.get("textTranslated") or ""
            rating = safe_int(rev.get("stars") or rev.get("rating"), 0)

            if not text or len(text) < 5:
                continue

            is_scam, scam_type, risk_level = classify_review_text(text, rating)

            records.append({
                "source": "google_maps",
                "source_weight": 0.62,
                "title": f"Google Maps: {place_name}",
                "content": text,
                "url": place_url,
                "latitude": lat,
                "longitude": lng,
                "location_name": address[:120],
                "scam_type": scam_type,
                "risk_level": risk_level,
                "is_scam": is_scam,
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            })

    print(f"\n[Results] {places_count} places scraped")
    print(f"[Results] {len(records)} total reviews extracted (safe + flagged)")

    if records:
        save_to_db(records)


def save_to_db(records):
    db_path = os.path.join(os.path.dirname(__file__), "safety_heatmap.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Clear old google_maps records to avoid duplication on re-runs
    cur.execute("DELETE FROM reports WHERE source = 'google_maps'")
    deleted = cur.rowcount
    print(f"[DB] Cleared {deleted} old google_maps records.")

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

    safe_count = sum(1 for r in records if r["is_scam"] == 0)
    scam_count = sum(1 for r in records if r["is_scam"] == 1)
    unique_places = len(set(r["location_name"] for r in records))
    print(f"[DB] Inserted {inserted} Google Maps reviews")
    print(f"[DB] {unique_places} unique locations | {safe_count} safe + {scam_count} flagged")


if __name__ == "__main__":
    import sys
    # Usage: python script.py                     -> new scrape
    #        python script.py C9KXhe2oGn4bvgaip   -> reuse existing dataset
    existing = sys.argv[1] if len(sys.argv) > 1 else None
    scrape_and_ingest(max_places=3, max_reviews=15, dataset_id=existing)
