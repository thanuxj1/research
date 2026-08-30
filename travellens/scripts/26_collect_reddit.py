"""Reddit collection via the official API. Run: python scripts/26_collect_reddit.py

Needs REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in travellens/.env.
See collect_reddit_oauth.py for the two-minute setup.
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.collect import Fetcher, load_env, write
from travellens.collect_reddit_oauth import collect, get_token

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--max-requests", type=int, default=40)
    args = ap.parse_args()

    print("\nLostinSriLanka -- Reddit (official API)\n" + "=" * 60)
    env = load_env()
    cid, sec = env.get("REDDIT_CLIENT_ID"), env.get("REDDIT_CLIENT_SECRET")
    print("  REDDIT_CLIENT_ID     : {}".format("present" if cid else "MISSING"))
    print("  REDDIT_CLIENT_SECRET : {}".format("present" if sec else "MISSING"))
    if not (cid and sec):
        print("\n  Not configured. Two-minute setup:")
        print("    1. https://www.reddit.com/prefs/apps -> create another app -> type: script")
        print("    2. redirect uri: http://localhost:8080")
        print("    3. add to travellens/.env:")
        print("         REDDIT_CLIENT_ID=<string under the app name>")
        print("         REDDIT_CLIENT_SECRET=<the secret field>")
        print("\n  This is Reddit's sanctioned route. Scraping their HTML instead")
        print("  would breach their terms, so this project does not do it.")
        return

    token = get_token(cid, sec)
    if not token:
        print("\n  Could not obtain a token -- check the two values.")
        return
    print("  authenticated\n")
    f = Fetcher(max_requests=args.max_requests)
    items = collect(f, token, limit=args.limit)
    write(items, "reddit")
    print("\n  requests made: {}".format(f.n))
    print("  next: python scripts/21_ingest_media.py data/incoming/reddit_*.json --kind reddit")

if __name__ == "__main__":
    main()
