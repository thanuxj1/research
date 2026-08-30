"""Entry point. Run: python scripts/14_ingest_tripadvisor.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.tripadvisor import main

if __name__ == "__main__":
    main()
