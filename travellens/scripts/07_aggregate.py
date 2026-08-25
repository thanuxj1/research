"""Entry point for Stage 6. Run: python scripts/07_aggregate.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.aggregate import main

if __name__ == "__main__":
    main()
