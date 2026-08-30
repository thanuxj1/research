"""Reddit via public RSS feeds. No credentials needed.
Run: python scripts/27_collect_reddit_rss.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.collect import write
from travellens.collect_reddit_rss import collect

def main():
    print("\nLostinSriLanka -- Reddit via public RSS\n" + "=" * 60)
    print("  No key needed. The plain subreddit feed is the only unauthenticated")
    print("  route Reddit still serves: search.json is 403, search.rss is 429.")
    print("  Consequence: recent posts only, no historical search.\n")
    items = collect()
    write(items, "reddit")
    print("\n  next: python scripts/21_ingest_media.py data/incoming/reddit_*.json --kind reddit")

if __name__ == "__main__":
    main()
