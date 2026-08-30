"""Retrain the SAFETY classifier on high-precision labels.

Why safety needed its own training run
--------------------------------------
The general aspect classifier was trained on the rule lexicon's output. For
most aspects that is fine, but the safety triggers include wildlife words
(monkeys, snakes, crocodile, deep) that fire on SIGHTINGS as well as hazards:

    "We saw hundreds of monkeys very close up"   -> labelled safety, isn't
    "They show you all kinds of snakes"          -> labelled safety, isn't

Measured on 25 lexicon-tagged segments, only 12 were genuinely about safety --
precision 0.48. A model trained on labels that are half wrong learns to flag
wildlife, which is exactly the false-positive pattern observed (precision 0.478,
F1 0.647).

The fix is a cleaner teacher, not a bigger model. Training labels here require
an explicit hazard assertion, a "not safe" phrasing, a death/rescue mention, or
a warning verb in physical context -- precision 0.867 instead of 0.667.

Run: python scripts/20_train_safety.py
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np, pandas as pd
from travellens import config as C
from travellens.aspects_trained import TrainedAspectTagger

HAZARD = (r"\b(danger(ous)?|unsafe|slipper(y|ing)|drown(ed|ing)?|hazard(ous)?|accidents?|"
          r"treacherous|fatal|risky|at your own risk|injur(y|ed)|rip tide|strong current)\b")
NOTSAFE = r"\bnot (very )?safe\b|\bsafety (precaution|measure|fence|rail)"
DEATH = r"\b(people )?(died|deaths?)\b|\brescue"
WARN_PHYS = (r"\b(be )?care ?ful\b(?=.{0,60}\b(walk|climb|step|water|swim|bath|rock|road|edge|"
             r"slip|current|wave|monkey|leech|snake|croc|bridge|bend|drive|deep)\b)|"
             r"\bwatch out for\b|\bbeware\b")
CLEAN_SAFETY = "(?:%s)|(?:%s)|(?:%s)|(?:%s)" % (HAZARD, NOTSAFE, DEATH, WARN_PHYS)

def main():
    print("\nLostinSriLanka -- retraining SAFETY on clean labels\n" + "="*60)
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_tagged.csv")
    seg = seg[~seg.too_short].copy()
    ev = set(pd.read_csv(C.REPORTS / "safety_eval_sample.csv").segment_id)
    ev |= set(pd.read_csv(C.REPORTS / "eval_sample.csv").segment_id)
    seg = seg[~seg.segment_id.isin(ev)]
    print("  held out {} evaluation segments".format(len(ev)))

    y = seg.segment.astype(str).str.contains(CLEAN_SAFETY, case=False, regex=True, na=False)
    print("  clean safety positives: {}  (lexicon had {})".format(
        int(y.sum()), int(seg.asp_safety.sum())))

    t = TrainedAspectTagger(aspects=["safety"])
    rep = t.fit(seg.segment.astype(str).tolist(), {"safety": y.values})
    t.save(C.ROOT / "models" / "safety_classifier.pkl")
    json.dump(rep, open(C.REPORTS / "safety_classifier_train.json","w",encoding="utf-8"), indent=2)
    print("\n  saved models/safety_classifier.pkl")

if __name__ == "__main__":
    main()
