"""Entry point. Run: python scripts/13_build_focused_goldset.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.goldset_focused import main

if __name__ == "__main__":
    main()
