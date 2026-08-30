"""Entry point. Run: python scripts/44_accuracy_report.py

Rebuilds reports/accuracy_all_aspects.json from the two evaluations that
actually produced its numbers -- reports/gold_evaluation.json (accuracy) and
reports/agreement.json (reliability) -- instead of it being maintained by hand.

Refuses to publish a figure for any aspect no human has labelled. See
src/travellens/accuracy.py for the three rows that refusal removed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.accuracy import main

if __name__ == "__main__":
    main()
