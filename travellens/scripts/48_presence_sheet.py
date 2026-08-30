"""Entry point. Run: python scripts/48_presence_sheet.py

Builds reports/LABEL_THESE_presence.{csv,xlsx} -- the same 420 pairs the
polarity sheet covered, asking a different question:

    is this sentence about that topic at all?   y / n

The polarity sheet offered no way to say "no", so it measured the verdict on
pairs whose tag was never checked. That matters most where extraction is
weakest: roads extraction precision is 0.588, so roughly two in five
roads-tagged segments are not about roads, and all 60 roads pairs were given a
verdict anyway.

This yields extraction PRECISION for all seven aspects -- of the pairs the
pipeline tags, how many really belong. Not recall: this sample contains only
pairs the pipeline already tagged, so it cannot see what the pipeline missed.

Your earlier verdict is deliberately not carried across; see
src/travellens/polarity_sheet.py for why.

Fill 'is_about', put 'human' in 'labelled_by', then re-run
scripts/44_accuracy_report.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.polarity_sheet import main_presence

if __name__ == "__main__":
    main_presence()
