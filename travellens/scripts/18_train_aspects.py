"""Train the aspect classifier on rule-derived labels. Run: python scripts/18_train_aspects.py"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pandas as pd
from travellens import config as C
from travellens.aspects_trained import TrainedAspectTagger

def main():
    print("\nLostinSriLanka -- training the aspect classifier\n" + "="*60)
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_tagged.csv")
    seg = seg[~seg.too_short].copy()

    # Hold out the evaluation segments so the test set stays clean.
    ev = pd.read_csv(C.REPORTS / "eval_sample.csv")
    before = len(seg)
    seg = seg[~seg.segment_id.isin(set(ev.segment_id))]
    print("  excluded {} evaluation segments from training".format(before - len(seg)))

    texts = seg.segment.astype(str).tolist()
    labels = {a: seg["asp_" + a].values for a in C.ASPECTS}
    print("  training on {} segments labelled by the rule lexicon\n".format(len(texts)))

    t = TrainedAspectTagger()
    rep = t.fit(texts, labels)
    t.save()
    with open(C.REPORTS / "aspect_classifier_train.json", "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2)
    print("\n  saved {}".format(t.MODEL_PATH if hasattr(t,'MODEL_PATH') else 'models/aspect_classifier.pkl'))

if __name__ == "__main__":
    main()
