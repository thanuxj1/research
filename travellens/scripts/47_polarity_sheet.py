"""Entry point. Run: python scripts/47_polarity_sheet.py

Builds reports/LABEL_THESE_polarity.{csv,xlsx} -- a blank sheet sized to close
the polarity accuracy gaps: nothing at all exists for scenery, price_value and
crowd, roads_access sits at 0.421 on 19 pairs, and safety's interval spans half
the scale on 11.

One row per (sentence, topic). The reader puts N, P or X in one column. The
system's own verdict is deliberately not shown.

Fill it in, then re-run scripts/43_evaluate_polarity.py -- the evaluation picks
the sheet up automatically once 'labelled_by' says human.

See src/travellens/polarity_sheet.py for the sampling and why it is not
stratified by predicted verdict.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.polarity_sheet import main

if __name__ == "__main__":
    main()
