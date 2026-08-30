"""Apply the trained aspect classifier across the corpus.
Adds tAsp_<aspect> columns. Run: python scripts/19_apply_trained_aspects.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pandas as pd
from travellens import config as C
from travellens.aspects_trained import TrainedAspectTagger

def main():
    print("\nLostinSriLanka -- applying the trained aspect classifier\n" + "="*60)
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_tagged_union.csv")
    t = TrainedAspectTagger.load()
    usable = ~seg.too_short
    tags = t.tag(seg.loc[usable, "segment"].astype(str).tolist(), verbose=True)
    for a in C.ASPECTS:
        seg["tAsp_" + a] = False
    for pos, aspects in zip(seg.index[usable], tags):
        for a in aspects:
            if "tAsp_" + a in seg.columns:
                seg.at[pos, "tAsp_" + a] = True
    seg["t_n_aspects"] = seg[["tAsp_" + a for a in C.ASPECTS]].sum(axis=1)
    print("\n  {:<20} {:>9} {:>9} {:>9}".format("aspect","rules","union","trained"))
    for a in C.ASPECTS:
        print("  {:<20} {:>9} {:>9} {:>9}".format(C.ASPECTS[a].label,
              int(seg["asp_"+a].sum()), int(seg.get("uAsp_"+a, seg["asp_"+a]).sum()),
              int(seg["tAsp_"+a].sum())))
    out = C.DATA_PROCESSED / "segments_tagged_union.csv"
    seg.to_csv(out, index=False, encoding="utf-8")
    print("\nwrote {}".format(out))

if __name__ == "__main__":
    main()

# --- dedicated safety classifier (threshold 0.70; see aspects_model.ASPECT_EXTRACTOR)
def apply_safety():
    import pandas as pd
    from travellens import config as C
    from travellens.aspects_trained import TrainedAspectTagger
    path = C.ROOT / "models" / "safety_classifier.pkl"
    if not path.exists():
        print("  no dedicated safety model -- run scripts/20_train_safety.py")
        return
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_tagged_union.csv")
    m = TrainedAspectTagger.load(path)
    usable = ~seg.too_short
    probs = m.probabilities(seg.loc[usable, "segment"].astype(str).tolist())["safety"].values
    seg["sAsp_safety"] = False
    seg.loc[usable, "sAsp_safety"] = probs >= 0.70
    seg.to_csv(C.DATA_PROCESSED / "segments_tagged_union.csv", index=False, encoding="utf-8")
    print("  dedicated safety model tagged {} segments (threshold 0.70)".format(
        int(seg.sAsp_safety.sum())))
