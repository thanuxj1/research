"""Entry point. Run: python scripts/22_build_provenance.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.provenance import main

if __name__ == "__main__":
    main()
