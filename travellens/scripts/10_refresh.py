"""Entry point. Run: python scripts/10_refresh.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.pipeline import run

if __name__ == "__main__":
    run()
