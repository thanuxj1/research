"""Entry point for Stage 3. Run: python scripts/03_tag_aspects.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.aspects import main

if __name__ == "__main__":
    main()
