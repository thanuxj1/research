"""Entry point. Run: python scripts/17_aspects_model.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from travellens import config as C
from travellens.aspects_model import tag_corpus_model, ASPECT_PROMPTS

def main():
    print("\nLostinSriLanka -- model-based aspect extraction\n" + "="*60)
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_tagged.csv")
    seg = tag_corpus_model(seg)

    # Union: a segment belongs to an aspect if EITHER method says so.
    for k in ASPECT_PROMPTS:
        seg["uAsp_" + k] = seg["asp_" + k] | seg["mAsp_" + k]
    seg["u_n_aspects"] = seg[["uAsp_" + k for k in ASPECT_PROMPTS]].sum(axis=1)

    print("\n  segments with at least one aspect:")
    print("    rules only  : {}".format(int((seg.n_aspects>0).sum())))
    print("    model only  : {}".format(int((seg.m_n_aspects>0).sum())))
    print("    union       : {}".format(int((seg.u_n_aspects>0).sum())))
    out = C.DATA_PROCESSED / "segments_tagged_union.csv"
    seg.to_csv(out, index=False, encoding="utf-8")
    print("\nwrote {}".format(out))

if __name__ == "__main__":
    main()
