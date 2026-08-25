"""Entry point for Stage 4. Run: python scripts/04_build_goldset.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.goldset import main

if __name__ == "__main__":
    main()
