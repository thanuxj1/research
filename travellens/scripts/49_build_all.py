"""Rebuild every artefact, in dependency order.

  python scripts/49_build_all.py                 everything
  python scripts/49_build_all.py --only 45       just the portal build

Calls the numbered scripts rather than reimplementing them, so there is still
exactly one implementation of each stage and any step can be re-run alone.
Stops at the first failure: later stages read what earlier ones write, so
continuing would build on a stale file.

Then:  python scripts/50_launch.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.launch import build

if __name__ == "__main__":
    args = sys.argv[1:]
    only = None
    if "--only" in args:
        i = args.index("--only")
        if i + 1 >= len(args):
            raise SystemExit("--only needs a value, e.g. --only 45")
        only = args[i + 1]
    raise SystemExit(build(only=only))
