"""Entry point. Run: python scripts/46_reliability.py

Split-half reliability of the published complaint rates -> reports/reliability.json.

A complaint rate has no ground truth to be checked against, so it is validated
by reproducibility: split each destination-aspect cell's opinions in half at
random, score each half on its own, and measure how well the two halves agree.
Includes a permutation null, so a reader can see what the same procedure
returns when there is nothing there to find.

See src/travellens/reliability.py for why each figure is in the report.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.reliability import main

if __name__ == "__main__":
    main()
