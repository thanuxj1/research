"""Entry point for Stage 2. Run: python scripts/02_segment.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.segment import main

if __name__ == "__main__":
    main()
