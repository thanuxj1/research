"""
Facebook Collector — Tourism Safety & Scam Analytics Engine
IT22629180

Uses:
  - Apify API (apify-client) for high-performance, reliable Facebook scraping.
  - Targets public groups/pages for authentic tourist safety reports.
"""
from apify_client import ApifyClient
from app.core.config import settings
from typing import List, Dict
import time


class FacebookCollector:
    def __init__(self):
        self.api_token = settings.APIFY_API_TOKEN
        if self.api_token:
            self.client = ApifyClient(self.api_token)
        else:
            self.client = None
            print("Warning: APIFY_API_TOKEN not configured in .env")

    def collect_from_groups(self, group_urls: List[str], limit: int = 20) -> List[Dict]:
        """
        Uses apify/facebook-groups-scraper to pull posts from specific groups.
        """
        if not self.client:
            return []

        results = []
        actor_id = "apify/facebook-groups-scraper"
        
        # Prepare the input for the Apify Actor
        run_input = {
            "startUrls": [{"url": url} for url in group_urls],
            "resultsLimit": limit,
            "maxPosts": limit,
            "viewOption": "CHRONOLOGICAL",
        }

        try:
            print(f"  [Apify] Starting Facebook Groups Scraper for {len(group_urls)} groups...")
            # Run the actor and wait for it to finish
            run = self.client.actor(actor_id).call(run_input=run_input)
            
            # Fetch results from the run's dataset
            print(f"  [Apify] Fetching results from dataset: {run['defaultDatasetId']}")
            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                text = item.get("text") or item.get("message") or ""
                if text and len(text) > 30:
                    results.append({
                        "source": "facebook",
                        "title": f"Facebook Post - {item.get('username', 'Unknown User')}",
                        "content": text,
                        "url": item.get("url") or f"https://facebook.com/{item.get('id')}",
                    })
            
            print(f"  [Apify] Collected {len(results)} items from Facebook Groups.")
        except Exception as e:
            print(f"  [Apify] Error running Facebook Groups scraper: {e}")
            
        return results

    def collect_all(self, limit_per_source: int = 15) -> List[Dict]:
        """
        Main entry point for Facebook collection via Apify.
        """
        if not self.client:
            return []

        # High-value public groups for Sri Lanka tourism safety/scams
        target_groups = [
            "https://www.facebook.com/groups/srilankaexpats/",
            "https://www.facebook.com/groups/SriLankaTravelandTourism/",
            "https://www.facebook.com/groups/srilankatraveladvice/",
            "https://www.facebook.com/groups/431102553744654/", # Sri Lanka Travel Support
            "https://www.facebook.com/groups/srilankatravellers/",
            "https://www.facebook.com/groups/backpackingsrilanka/",
            "https://www.facebook.com/groups/1423408284594539/", # Sri Lanka Taxi/Driver reviews
            "https://www.facebook.com/groups/srilankatourism/",
            "https://www.facebook.com/groups/visit.srilanka.community/",
            "https://www.facebook.com/groups/expatsinsrilanka/",
        ]
        
        all_results = self.collect_from_groups(target_groups, limit=limit_per_source)
        
        return all_results


if __name__ == "__main__":
    # Test run
    collector = FacebookCollector()
    items = collector.collect_all(limit_per_source=5)
    for i in items:
        # Use safe print for Windows console
        safe_title = i['title'].encode('ascii', errors='replace').decode('ascii')
        safe_content = i['content'][:100].encode('ascii', errors='replace').decode('ascii')
        print(f"--- {safe_title} ---")
        print(safe_content + "...")
