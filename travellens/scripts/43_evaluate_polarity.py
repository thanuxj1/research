"""Per-aspect POLARITY accuracy against the human gold set.

  python scripts/43_evaluate_polarity.py

38_evaluate_against_gold.py scores whether the right ASPECT was found. This
scores whether a correctly-found aspect got the right VERDICT, which is what
every complaint rate on the dashboard is made of.

Reports bootstrap intervals, accuracy against BOTH annotators, and the human
ceiling for each aspect -- two people reading these sentences agree 83-98% of
the time, so an accuracy quoted against an implicit 100% asks the pipeline to
beat the people who defined the task. See src/travellens/polarity_eval.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.polarity_eval import main

if __name__ == "__main__":
    main()
