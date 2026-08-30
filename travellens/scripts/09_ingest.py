"""Entry point. Run: python scripts/09_ingest.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.ingest import main

if __name__ == "__main__":
    main()
