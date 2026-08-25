"""Entry point. Run: python scripts/12_weak_labels.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.weak_labels import main

if __name__ == "__main__":
    main()
