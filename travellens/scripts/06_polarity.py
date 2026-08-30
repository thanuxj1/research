"""Entry point for Stage 5. Run: python scripts/06_polarity.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.polarity import main

if __name__ == "__main__":
    main()
