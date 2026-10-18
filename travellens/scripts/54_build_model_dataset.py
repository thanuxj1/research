"""Draw the sentences for the model-comparison dataset (labelling batches).

  python scripts/54_build_model_dataset.py

Writes reports/model_dataset/to_label_*.csv. Nothing here trains or scores; it only
decides WHICH sentences get labelled, so the split cannot be tuned after the fact.

Splits (fixed here, before any model sees a label)
  test_random   500 random sentences. Together with the existing 300-sentence
                hold-out (reports/ai_annotated/holdout_sample_claude.csv) this is the
                800-sentence TEST set. No model is trained or tuned on it.
  train_random  400 random sentences, joined to the existing 500-sentence random
                draw (reports/ai_annotated/random_sample_claude.csv) for training.
  train_dense   600 sentences found by MEANING, not by keyword: the nearest
                neighbours of a plain-English description of each rare topic in a
                sentence-embedding space (BAAI/bge-small-en-v1.5), 100 per topic,
                drawn at random from each topic's top 1,500 so they are not
                near-duplicates. This gives the rare topics (safety has 35 mentions
                in 800 random sentences) enough positives to learn from. It is
                never used for testing, because it is not a random sample.

Excluded from every draw: all previously labelled sentences (AI and human), so the
human gold set stays a clean, untouched test.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from travellens import config as C  # noqa: E402

OUT = ROOT / "reports" / "model_dataset"
SEED = 20261014
TOPICS = ["roads_access", "cleanliness", "facilities", "safety", "price_value", "crowd", "scenery"]
DESCRIPTIONS = {
    "safety": "danger, risk, accidents, drowning, slippery rocks, falling, wild animals attacking, theft, scams, warnings to be careful",
    "cleanliness": "litter, garbage, plastic waste, dirty, smelly, unclean, rubbish, well kept and clean",
    "price_value": "ticket price, entrance fee, expensive, overpriced, cheap, value for money, foreigners charged more",
    "crowd": "crowded, too many people, queues, noisy, busy, quiet and peaceful with few visitors",
    "roads_access": "road condition, parking, how to get there, bus or train, steep climb, long walk, hard to reach",
    "facilities": "toilets, restrooms, food stalls, shops, seating, shade, guides, signboards, ticket counter, maintenance",
}


def labelled_ids() -> set:
    ids = set()
    rep = ROOT / "reports"
    for f in list((rep / "ai_annotated").glob("*.csv")) + list(rep.glob("goldset*.csv")) + list(rep.glob("LABEL_THESE*.csv")):
        try:
            d = pd.read_csv(f, dtype=str, encoding="utf-8-sig")
        except Exception:
            continue
        if "segment_id" in d.columns:
            ids |= set(d.segment_id.dropna())
    return ids


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_scored.csv", usecols=["segment_id", "segment"])
    seg = seg.dropna()
    seg = seg[seg.segment.str.strip().str.len() > 0]
    seen = labelled_ids()
    pool = seg[~seg.segment_id.isin(seen)].drop_duplicates("segment")
    print("pool", len(pool), "excluded", len(seen))

    rng = np.random.default_rng(SEED)
    idx = rng.permutation(len(pool))
    test = pool.iloc[idx[:500]]
    train_r = pool.iloc[idx[500:900]]
    rest = pool.iloc[idx[900:]]

    # meaning-based enrichment over a 40k random slice of the remainder
    from sentence_transformers import SentenceTransformer
    cand = rest.iloc[:40000]
    m = SentenceTransformer("BAAI/bge-small-en-v1.5")
    E = m.encode(cand.segment.tolist(), batch_size=256, normalize_embeddings=True, show_progress_bar=False)
    taken = set()
    dense = []
    for t, desc in DESCRIPTIONS.items():
        q = m.encode([desc], normalize_embeddings=True)[0]
        top = np.argsort(-(E @ q))[:1500]
        top = [i for i in top if i not in taken]
        pick = rng.choice(top, size=100, replace=False)
        taken |= set(pick.tolist())
        dense.append(cand.iloc[pick].assign(drawn_for=t))
    dense = pd.concat(dense)

    for name, d in (("test_random", test), ("train_random", train_r), ("train_dense", dense)):
        d = d.sample(frac=1, random_state=SEED).reset_index(drop=True)
        d.insert(0, "id", ["%s_%04d" % (name, i + 1) for i in range(len(d))])
        d.to_csv(OUT / ("to_label_%s.csv" % name), index=False, encoding="utf-8")
        print(name, len(d))


if __name__ == "__main__":
    main()
