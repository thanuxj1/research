"""Entry point. Run: python scripts/21_ingest_media.py <file.json> --kind youtube|reddit|news"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.media import main

if __name__ == "__main__":
    main()
