"""Entry point for the gold-set checker. Run: python scripts/05_check_goldset.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.gold_check import main

if __name__ == "__main__":
    main()
