"""Entry point for Stage 9. Run: python scripts/11_finetune.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.finetune import main

if __name__ == "__main__":
    main()
