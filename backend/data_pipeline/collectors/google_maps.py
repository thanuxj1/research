"""
Google Maps Collector — Tourism Safety & Scam Analytics Engine
IT22629180

Supports Dual Data Ingestion:
  1. Official Google Places API (Text Search + Place Details with Reviews)
     — Free up to $200/month recurring credit (~10,000 requests/month).
  2. Apify Scraper (compass/crawler-google-places)
     — Fallback / complementary collector using Apify $5/month free credit.
"""
import requests
import time
from typing import List, Dict, Optional
from apify_client import ApifyClient
from app.core.config import settings

KEYWORDS = [
    "scam", "fraud", "fake", "overcharge", "trap", "dangerous",
    "cheat", "rip off", "mafia", "assault", "harassment", "overpriced", "tricking"
]

SEARCH_QUERIES = [
    "gem shop Colombo Kandy Galle",
    "jewelry store Sri Lanka tourist",
    "tuk tuk scam Colombo Kandy Ella",
    "tourist attraction scam Sri Lanka",
    "Ella Rock guide scam",
    "Nine Arch Bridge scam",
    "Sigiriya guide scam overcharge",
    "Mirissa whale watching scam",
    "Hikkaduwa beach boy harassment",
    "Pettah market pickpocket",
    "Kandy Temple of the Tooth scam",
    "Galle Fort overcharging restaurant",
    "Negombo beach scam",
    "Arugam Bay drug safety",
    "Trincomalee tourist fraud",
    "Nuwara Eliya tea factory scam",
    "Yala safari jeep overcharge",
    "Dambulla cave temple fake guide",
    "Pinnawala elephant orphanage scam",
    "Mount Lavinia beach harassment"
]


class GoogleMapsCollector:
    def __init__(self):
        self.google_api_key = settings.GOOGLE_MAPS_API_KEY
        self.apify_token = settings.APIFY_API_TOKEN
        
        if self.apify_token:
            self.apify_client = ApifyClient(self.apify_token)
        else:
            self.apify_client = None

    def collect_via_official_api(self, search_queries: List[str] = SEARCH_QUERIES, limit_per_query: int = 2) -> List[Dict]:
        """
        Collects place reviews using the Official Google Places API (Text Search + Place Details).
        Uses Google's $200/month free recurring credit.
        """
        if not self.google_api_key:
            print("  [Google Places API] No GOOGLE_MAPS_API_KEY configured in .env")
            return []

        results = []
        print(f"  [Google Places API] Querying Official API for {len(search_queries)} search terms...")

        for query in search_queries:
            try:
                # Step 1: Text Search to find matching tourist locations
                search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
                params = {
                    "query": query,
                    "key": self.google_api_key,
                    "language": "en"
                }
                res = requests.get(search_url, params=params, timeout=10)
                data = res.json()

                if data.get("status") != "OK":
                    status = data.get("status")
                    if status == "REQUEST_DENIED":
                        print(f"  [Google Places API] Request denied: {data.get('error_message')}")
                        break
                    continue

                places = data.get("results", [])[:limit_per_query]

                for place in places:
                    place_id = place.get("place_id")
                    place_name = place.get("name", "Unknown Place")
                    location = place.get("geometry", {}).get("location", {})
                    lat = location.get("lat")
                    lng = location.get("lng")

                    # Step 2: Place Details to retrieve user reviews
                    details_url = "https://maps.googleapis.com/maps/api/place/details/json"
                    details_params = {
                        "place_id": place_id,
                        "fields": "name,rating,reviews,url,geometry",
                        "key": self.google_api_key,
                        "language": "en"
                    }
                    d_res = requests.get(details_url, params=details_params, timeout=10)
                    d_data = d_res.json()

                    if d_data.get("status") == "OK":
                        result_item = d_data.get("result", {})
                        reviews = result_item.get("reviews", [])
                        place_url = result_item.get("url", f"https://www.google.com/maps/place/?q=place_id:{place_id}")

                        for rev in reviews:
                            text = rev.get("text", "")
                            rating = rev.get("rating", 0)

                            if (text and any(kw in text.lower() for kw in KEYWORDS)) or (rating and rating <= 2):
                                results.append({
                                    "source": "google_maps",
                                    "title": f"Google Maps Review of {place_name}",
                                    "content": text if text else f"Low rating review ({rating} stars) for {place_name}",
                                    "url": place_url,
                                    "latitude": lat,
                                    "longitude": lng,
                                    "metadata": {
                                        "rating": rating,
                                        "place_id": place_id,
                                        "author": rev.get("author_name"),
                                        "time": rev.get("time"),
                                        "collection_method": "official_places_api"
                                    }
                                })
                time.sleep(0.2)  # Avoid rate limiting
            except Exception as e:
                print(f"  [Google Places API] Error fetching '{query}': {e}")

        print(f"  [Google Places API] Collected {len(results)} safety-related reviews via Official API.")
        return results

    def collect_via_apify(self, search_queries: List[str] = SEARCH_QUERIES, limit_per_query: int = 2) -> List[Dict]:
        """
        Fallback / Secondary collection using Apify Google Maps actor.
        Uses Apify's $5/month free monthly credit.
        """
        if not self.apify_client:
            print("  [Apify] APIFY_API_TOKEN not configured in .env")
            return []

        results = []
        actor_id = "compass/crawler-google-places"
        run_input = {
            "searchStringsArray": search_queries,
            "maxCrawledPlacesPerSearch": limit_per_query,
            "maxReviews": 10,
            "language": "en",
            "reviewsSort": "newest",
        }

        try:
            print(f"  [Apify] Starting Google Maps Scraper ({actor_id})...")
            run = self.apify_client.actor(actor_id).call(run_input=run_input)
            
            for item in self.apify_client.dataset(run["defaultDatasetId"]).iterate_items():
                place_name = item.get("title", "Unknown Place")
                reviews = item.get("reviews", [])
                lat = item.get("location", {}).get("lat") or item.get("lat")
                lng = item.get("location", {}).get("lng") or item.get("lng")
                url = item.get("url")

                for review in reviews:
                    text = review.get("text") or ""
                    rating = review.get("stars", 0) or review.get("rating", 0)

                    if (text and any(kw in text.lower() for kw in KEYWORDS)) or (rating and rating <= 2):
                        results.append({
                            "source": "google_maps",
                            "title": f"Review of {place_name}",
                            "content": text if text else f"Low rating review: {rating} stars",
                            "url": url,
                            "latitude": lat,
                            "longitude": lng,
                            "metadata": {
                                "rating": rating,
                                "place_id": item.get("id"),
                                "collection_method": "apify_free_tier"
                            }
                        })

            print(f"  [Apify] Collected {len(results)} safety-related reviews from Google Maps.")
        except Exception as e:
            print(f"  [Apify] Error running Google Maps scraper: {e}")

        return results

    def collect_all(self, limit_per_query: int = 2) -> List[Dict]:
        """
        Attempts collection via Official Google Places API first.
        Falls back to or supplements with Apify scraper if needed.
        """
        results = []
        
        # 1. Try Official Google Places API if key exists
        if self.google_api_key:
            official_results = self.collect_via_official_api(limit_per_query=limit_per_query)
            results.extend(official_results)

        # 2. Fallback to Apify if official API is unconfigured or returns few results
        if not results and self.apify_client:
            apify_results = self.collect_via_apify(limit_per_query=limit_per_query)
            results.extend(apify_results)

        return results


if __name__ == "__main__":
    collector = GoogleMapsCollector()
    items = collector.collect_all(limit_per_query=1)
    print(f"\nTotal Google Maps items collected: {len(items)}")
    for i in items[:3]:
        safe_title = i['title'].encode('ascii', errors='replace').decode('ascii')
        print(f"--- {safe_title} ({i['latitude']}, {i['longitude']}) ---")
