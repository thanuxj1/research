"""Entry point for Stage 1. Run: python scripts/01_clean.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.clean import main

if __name__ == "__main__":
    main()
