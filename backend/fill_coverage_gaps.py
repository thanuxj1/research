"""
Targeted Gap Filler — Scrapes Google Maps for ONLY the missing destinations.
IT22629180

Uses the coverage_gap_analysis output to fill exactly the 9 missing destinations.
Also adds synthetic ground-truth records for destinations that may have very few
reviews on Google Maps (remote areas like Keerimalai, Baobab Tree, etc.)
"""
import os
import sqlite3
from datetime import datetime, timezone
from apify_client import ApifyClient
from app.core.config import settings

# The 9 gap destinations with their precise coordinates
GAP_DESTINATIONS = [
    {
        "query": "Nine Arch Bridge Ella Demodara Sri Lanka",
        "name": "Nine Arch Bridge",
        "lat": 6.8770, "lng": 81.0590,
        "province": "Uva", "category": "Adventure/Scenic", "priority": "High",
    },
    {
        "query": "Pidurangala Rock Sigiriya Sri Lanka",
        "name": "Pidurangala Rock",
        "lat": 7.9690, "lng": 80.7530,
        "province": "North Central", "category": "Adventure/Scenic", "priority": "High",
    },
    {
        "query": "Lipton's Seat Haputale Sri Lanka viewpoint",
        "name": "Lipton's Seat",
        "lat": 6.7960, "lng": 80.9900,
        "province": "Uva", "category": "Scenic", "priority": "Medium",
    },
    {
        "query": "Delft Island Neduntheevu Jaffna Sri Lanka",
        "name": "Delft Island",
        "lat": 9.5167, "lng": 79.6833,
        "province": "Northern", "category": "Heritage/Nature", "priority": "Medium",
    },
    {
        "query": "Kosgoda Turtle Hatchery Sri Lanka",
        "name": "Kosgoda Turtle Hatchery",
        "lat": 6.3306, "lng": 80.0306,
        "province": "Southern", "category": "Wildlife", "priority": "Low",
    },
    {
        "query": "Keerimalai Springs Jaffna Sri Lanka",
        "name": "Keerimalai Springs",
        "lat": 9.8167, "lng": 80.0333,
        "province": "Northern", "category": "Religious/Nature", "priority": "Low",
    },
    {
        "query": "Baobab Tree Mannar Sri Lanka",
        "name": "Baobab Tree Mannar",
        "lat": 9.0028, "lng": 79.8528,
        "province": "Northern", "category": "Nature", "priority": "Low",
    },
    {
        "query": "Chilaw town beach temple Sri Lanka",
        "name": "Chilaw",
        "lat": 7.5758, "lng": 79.7953,
        "province": "North Western", "category": "Coastal", "priority": "Low",
    },
    {
        "query": "Handunugoda Tea Estate Virgin White Tea Galle Sri Lanka",
        "name": "Handunugoda Tea Estate",
        "lat": 5.9833, "lng": 80.3333,
        "province": "Southern", "category": "Cultural", "priority": "Low",
    },
]


def safe_int(val, default=0):
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


SAFETY_KEYWORDS = [
    "scam", "fraud", "fake", "overcharge", "trap", "dangerous",
    "cheat", "rip off", "ripped off", "mafia", "assault", "harassment",
    "overpriced", "tricking", "pickpocket", "stolen", "theft", "robbed",
    "mugged", "harassed", "unsafe", "threatened", "attacked",
]


def classify_review(text, rating):
    text_lower = (text or "").lower()
    matched = [kw for kw in SAFETY_KEYWORDS if kw in text_lower]
    if not matched and rating > 2:
        return 0, "safe", 1
    if matched or (rating > 0 and rating <= 2):
        return 1, "General Scam", 2
    return 0, "safe", 1


def fill_gaps():
    token = settings.APIFY_API_TOKEN
    if not token:
        print("[Error] APIFY_API_TOKEN missing")
        return

    client = ApifyClient(token)
    queries = [g["query"] for g in GAP_DESTINATIONS]

    print("=" * 70)
    print(f"  TARGETED GAP FILLER — {len(queries)} missing destinations")
    print("=" * 70)

    # Run Apify for gap queries
    actor_id = "compass/crawler-google-places"
    run_input = {
        "searchStringsArray": queries,
        "maxCrawledPlacesPerSearch": 3,
        "maxReviews": 20,
        "language": "en",
        "reviewsSort": "newest",
    }

    print(f"\n[Apify] Launching targeted scrape for {len(queries)} gap queries...")
    run = client.actor(actor_id).call(run_input=run_input)
    dataset_id = run.get("defaultDatasetId")
    print(f"[Apify] Done! Dataset: {dataset_id}")

    records = []
    places_found = 0

    for item in client.dataset(dataset_id).iterate_items():
        places_found += 1
        place_name = item.get("title") or item.get("name") or "Unknown"
        reviews = item.get("reviews", [])
        lat = safe_float(item.get("location", {}).get("lat") or item.get("lat"))
        lng = safe_float(item.get("location", {}).get("lng") or item.get("lng"))
        place_url = item.get("url", "")
        address = item.get("address", "") or place_name

        if not lat or not lng:
            # Try to match against our known gap coordinates
            for gap in GAP_DESTINATIONS:
                if gap["name"].lower() in place_name.lower():
                    lat, lng = gap["lat"], gap["lng"]
                    break

        for rev in reviews:
            text = rev.get("text") or rev.get("textTranslated") or ""
            rating = safe_int(rev.get("stars") or rev.get("rating"), 0)
            if not text or len(text) < 5:
                continue
            is_scam, scam_type, risk_level = classify_review(text, rating)
            records.append({
                "source": "google_maps",
                "source_weight": 0.62,
                "title": f"Google Maps: {place_name}",
                "content": text,
                "url": place_url,
                "latitude": lat, "longitude": lng,
                "location_name": address[:120],
                "scam_type": scam_type,
                "risk_level": risk_level,
                "is_scam": is_scam,
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            })

        if not reviews:
            records.append({
                "source": "google_maps",
                "source_weight": 0.62,
                "title": f"Google Maps: {place_name}",
                "content": f"{place_name} - Tourist destination in Sri Lanka.",
                "url": place_url,
                "latitude": lat, "longitude": lng,
                "location_name": address[:120],
                "scam_type": "safe", "risk_level": 1, "is_scam": 0,
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            })

    print(f"[Results] {places_found} places found, {len(records)} reviews extracted")

    # Also add ground-truth baseline records for each gap destination
    # (ensures they appear on the map even if Apify returns nothing for them)
    for gap in GAP_DESTINATIONS:
        records.append({
            "source": "canonical_registry",
            "source_weight": 0.55,
            "title": f"Canonical: {gap['name']}",
            "content": f"{gap['name']} is a {gap['category']} destination in {gap['province']} Province, Sri Lanka. Listed in canonical destination registry.",
            "url": f"https://maps.google.com/?q={gap['lat']},{gap['lng']}",
            "latitude": gap["lat"], "longitude": gap["lng"],
            "location_name": f"{gap['name']}, {gap['province']}",
            "scam_type": "safe", "risk_level": 1, "is_scam": 0,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        })

    # Save to DB
    db_path = os.path.join(os.path.dirname(__file__), "safety_heatmap.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
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
    print(f"[DB] Inserted {inserted} records for gap destinations")


if __name__ == "__main__":
    fill_gaps()
