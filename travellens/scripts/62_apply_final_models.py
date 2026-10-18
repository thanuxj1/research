"""Run the two deployed models over the whole corpus (after 61; before 07_aggregate).

  python scripts/62_apply_final_models.py

Adds to data/processed/segments_scored.csv
  fAsp_<topic>   topic present per the final topic model (lexicon OR embedding-SVM)
  f_n_aspects    how many topics
Writes data/processed/verdict_final.csv
  one row per (segment, topic) the final topic model found: the fine-tuned RoBERTa
  verdict (pol_fm = N / X / P) and its confidence.

Short segments are skipped exactly as aspects.tag_corpus skips them. Verdicts are cached
by (text, topic) in verdict_final_cache.csv, because reviewers repeat sentences and a
rerun after a corpus refresh then only scores what is new.
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from travellens import config as C  # noqa: E402
from travellens import final_models as FM  # noqa: E402

SCORED = C.DATA_PROCESSED / "segments_scored.csv"
CACHE = C.DATA_PROCESSED / "verdict_final_cache.csv"


def main():
    if not FM.available():
        raise SystemExit("final models missing -- run scripts/61_train_final_models.py first")
    t0 = time.time()
    seg = pd.read_csv(SCORED, low_memory=False)
    usable = ~seg["too_short"].astype(bool) & seg["segment"].notna()
    texts = seg.loc[usable, "segment"].astype(str)
    uniq = pd.unique(texts)
    print("segments %d, usable %d, unique texts %d" % (len(seg), usable.sum(), len(uniq)), flush=True)

    E = FM.embed(uniq, batch_size=256)
    print("embedded in %.0f s" % (time.time() - t0), flush=True)
    P = np.zeros((len(uniq), 7), dtype=bool)
    for i in range(0, len(uniq), 5000):
        P[i:i + 5000] = FM.topics_from_embeddings(uniq[i:i + 5000], E[i:i + 5000])
    topics = FM._load_topic()[0]["topics"]
    row_of = {t: i for i, t in enumerate(uniq)}
    idx = texts.map(row_of).values
    for j, k in enumerate(topics):
        col = np.zeros(len(seg), dtype=bool)
        col[np.where(usable)[0]] = P[idx, j]
        seg["fAsp_" + k] = col
    seg["f_n_aspects"] = seg[["fAsp_" + k for k in topics]].sum(axis=1)
    print("topics tagged in %.0f s: %d segments with >= 1 topic (lexicon alone: %d)" % (
        time.time() - t0, (seg["f_n_aspects"] > 0).sum(), (seg["n_aspects"] > 0).sum()), flush=True)

    # verdicts for every (segment, topic) pair
    long = []
    for k in topics:
        sub = seg.loc[seg["fAsp_" + k], ["segment_id", "segment"]]
        long.append(pd.DataFrame({"segment_id": sub.segment_id, "aspect": k, "text": sub.segment.astype(str)}))
    long = pd.concat(long, ignore_index=True)
    cache = {}
    if CACHE.exists():
        c = pd.read_csv(CACHE)
        cache = {(t, a): (l, p) for t, a, l, p in zip(c.text, c.aspect, c.label, c.conf)}
    todo = sorted({(t, a) for t, a in zip(long.text, long.aspect)} - set(cache))
    print("pairs %d, cached %d, to score %d" % (len(long), len(long) - len(todo), len(todo)), flush=True)
    for i in range(0, len(todo), 20000):
        chunk = todo[i:i + 20000]
        for (t, a), v in zip(chunk, FM.predict_verdicts(chunk, verbose=True)):
            cache[(t, a)] = v
        pd.DataFrame([{"text": t, "aspect": a, "label": l, "conf": round(p, 4)} for (t, a), (l, p) in cache.items()]
                     ).to_csv(CACHE, index=False, encoding="utf-8")
        print("  checkpoint %d / %d pairs (%.0f s)" % (min(i + 20000, len(todo)), len(todo), time.time() - t0), flush=True)
    long["pol_fm"] = [cache[(t, a)][0] for t, a in zip(long.text, long.aspect)]
    long["pol_fm_conf"] = [cache[(t, a)][1] for t, a in zip(long.text, long.aspect)]
    long[["segment_id", "aspect", "pol_fm", "pol_fm_conf"]].to_csv(FM.VERDICT_CSV, index=False, encoding="utf-8")
    seg.to_csv(SCORED, index=False, encoding="utf-8")
    print("done in %.0f s: %s and %d verdicts" % (time.time() - t0, SCORED.name, len(long)))


if __name__ == "__main__":
    main()
