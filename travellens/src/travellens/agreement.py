"""Inter-annotator agreement for the focused gold set.

What this is for
----------------
Open problem #1 of this project is that every evaluation label was produced by
the assistant that built the pipeline. The accuracy figures are therefore
"measured against one careful reader", not against ground truth. The fix is a
second, independent, HUMAN pass over the same segments, and Cohen's kappa
between the two.

Why this module refuses to be helpful
-------------------------------------
There is a specific way to get this wrong that looks exactly like getting it
right: label the second pass with an AI, compute kappa, and report the number.
It produces a healthy-looking statistic that means "two language models agree",
presented in a section headed "inter-annotator reliability". That is worse than
reporting nothing, because a reader takes it as independent validation.

That already happened once in this project -- reports/automated_second_pass.json
documents an AI second pass and says plainly it is NOT kappa -- and a later
reading of the filled CSV nearly reported it as human agreement anyway. So the
guard is in code, not in a comment: a labels file must carry an explicit
provenance declaration, and a machine provenance raises rather than returns.

Kappa alone is not enough either. A point estimate from a small sample carries
an interval wide enough to be worthless, so every figure here comes with a
bootstrap confidence interval, and the LOWER bound is what any claim must rest
on.

Run with:  python scripts/39_agreement.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from . import config as C

FOCUS_ASPECTS = ["roads_access", "cleanliness", "facilities", "safety"]

# A labels file must say who made it, in this column, on every row it claims.
PROVENANCE_COL = "labelled_by"
HUMAN_VALUES = {"human"}
MACHINE_VALUES = {"ai", "machine", "assistant", "model", "llm", "automated"}

BOOTSTRAP = 5000
SEED = 20260827


class MachineLabelsRefused(RuntimeError):
    """Raised when a labels file was not produced by a human."""


def _provenance(df: pd.DataFrame, path: Path) -> str:
    """Read and validate the provenance declaration on a labels file."""
    if PROVENANCE_COL not in df.columns:
        raise MachineLabelsRefused(
            f"{path.name} carries no '{PROVENANCE_COL}' column.\n"
            "Every labels file must declare who produced it. Add a "
            f"'{PROVENANCE_COL}' column containing 'human' on each labelled "
            "row. This is refused rather than assumed because an unmarked "
            "file is exactly how an AI pass gets reported as human agreement."
        )
    vals = {str(v).strip().lower() for v in df[PROVENANCE_COL].dropna().unique()}
    if not vals:
        raise MachineLabelsRefused(f"{path.name}: '{PROVENANCE_COL}' is empty.")
    machine = vals & MACHINE_VALUES
    if machine:
        raise MachineLabelsRefused(
            f"{path.name} declares provenance {sorted(machine)}.\n"
            "Cohen's kappa between a human and a machine, or between two "
            "machines, is not inter-annotator reliability and must not be "
            "reported as it. See reports/automated_second_pass.json."
        )
    unknown = vals - HUMAN_VALUES
    if unknown:
        raise MachineLabelsRefused(
            f"{path.name}: unrecognised provenance {sorted(unknown)}. "
            f"Expected one of {sorted(HUMAN_VALUES)}."
        )
    return "human"


def cohens_kappa(a: Sequence, b: Sequence) -> Optional[float]:
    """Cohen's kappa for two aligned label sequences."""
    a = np.asarray(a)
    b = np.asarray(b)
    n = len(a)
    if n == 0:
        return None
    labels = sorted(set(a.tolist()) | set(b.tolist()))
    if len(labels) < 2:
        return None                       # no variation: kappa undefined
    po = float((a == b).mean())
    pe = 0.0
    for lab in labels:
        pe += float((a == lab).mean()) * float((b == lab).mean())
    if pe >= 1.0:
        return None
    return (po - pe) / (1.0 - pe)


def bootstrap_ci(a: Sequence, b: Sequence, n_boot: int = BOOTSTRAP,
                 seed: int = SEED) -> Dict[str, Optional[float]]:
    """Percentile bootstrap interval for kappa.

    Resampling rows rather than assuming a normal error, because kappa is
    bounded and skewed at small n -- which is precisely the regime this
    project is in.
    """
    a = np.asarray(a)
    b = np.asarray(b)
    n = len(a)
    point = cohens_kappa(a, b)
    if point is None or n < 2:
        return {"kappa": point, "lo": None, "hi": None, "n": int(n)}
    rng = np.random.default_rng(seed)
    draws: List[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        k = cohens_kappa(a[idx], b[idx])
        if k is not None:
            draws.append(k)
    if not draws:
        return {"kappa": point, "lo": None, "hi": None, "n": int(n)}
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"kappa": round(float(point), 3), "lo": round(float(lo), 3),
            "hi": round(float(hi), 3), "n": int(n)}


def interpret(k: Optional[float]) -> str:
    """Landis & Koch bands. Applied to the LOWER bound, never the point."""
    if k is None:
        return "undefined"
    if k < 0.0:
        return "worse than chance"
    if k < 0.20:
        return "slight"
    if k < 0.40:
        return "fair"
    if k < 0.60:
        return "moderate"
    if k < 0.80:
        return "substantial"
    return "almost perfect"


def agreement(a1: pd.DataFrame, a2: pd.DataFrame,
              aspects: Sequence[str] = FOCUS_ASPECTS) -> Dict:
    """Presence and polarity agreement between two human passes."""
    key = "segment_id" if "segment_id" in a1.columns else "row"
    m = a1.merge(a2, on=key, suffixes=("_1", "_2"))

    out: Dict = {"n_rows_in_both": int(len(m)), "join_key": key,
                 "presence": {}, "polarity": {}}

    for asp in aspects:
        c1, c2 = f"{asp}_1", f"{asp}_2"
        if c1 not in m.columns or c2 not in m.columns:
            continue
        # PRESENCE: a blank means "not about this aspect", which is a judgement,
        # not a missing value.
        p1 = m[c1].notna().astype(int).to_numpy()
        p2 = m[c2].notna().astype(int).to_numpy()
        ci = bootstrap_ci(p1, p2)
        ci["percent_agreement"] = round(100.0 * float((p1 == p2).mean()), 1)
        ci["interpretation_of_lower_bound"] = interpret(ci["lo"])
        ci["supports_substantial_claim"] = bool(
            ci["lo"] is not None and ci["lo"] > 0.60)
        out["presence"][asp] = ci

        # POLARITY: only where BOTH judged the aspect present.
        both = m[m[c1].notna() & m[c2].notna()]
        if len(both) >= 2:
            pc = bootstrap_ci(both[c1].to_numpy(), both[c2].to_numpy())
            pc["percent_agreement"] = round(
                100.0 * float((both[c1].to_numpy() == both[c2].to_numpy()).mean()), 1)
            pc["interpretation_of_lower_bound"] = interpret(pc["lo"])
            out["polarity"][asp] = pc
        else:
            out["polarity"][asp] = {"n": int(len(both)),
                                    "note": "too few rows judged present by both"}
    return out


def load_labels(path: Path) -> pd.DataFrame:
    """Read a labels file, refusing it unless a human made it."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist.\n"
            "The second human pass is outstanding. Generate the blank sheet "
            "with:  python scripts/37_annotation_workbook.py --annotator 2"
        )
    df = pd.read_csv(path)
    _provenance(df, path)
    return df


def declare(which: int, who: str) -> None:
    """Stamp an existing labels file with its provenance.

    Deliberately a separate, explicit command rather than something inferred.
    Nobody should be able to make a file count as human by accident, and the
    person running this is asserting something they can be held to.
    """
    who = who.strip().lower()
    if who not in HUMAN_VALUES | MACHINE_VALUES:
        raise SystemExit(
            f"unknown provenance {who!r}; use one of "
            f"{sorted(HUMAN_VALUES | MACHINE_VALUES)}")
    path = C.REPORTS / f"goldset_focused_annotator{which}.csv"
    if not path.exists():
        raise SystemExit(f"{path} does not exist")
    df = pd.read_csv(path)
    labelled = df[FOCUS_ASPECTS].notna().any(axis=1) if all(
        a in df.columns for a in FOCUS_ASPECTS) else pd.Series(True, index=df.index)
    df[PROVENANCE_COL] = ""
    df.loc[labelled, PROVENANCE_COL] = who
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"{path.name}: {int(labelled.sum())} labelled rows declared {who!r}")
    if who in MACHINE_VALUES:
        print("NOTE: agreement.py will now refuse this file, which is correct.")


def main() -> None:
    import sys as _sys
    argv = _sys.argv[1:]
    if argv and argv[0] == "--declare":
        if len(argv) != 3:
            raise SystemExit("usage: --declare <1|2> <human|ai>")
        return declare(int(argv[1]), argv[2])

    print("\nLostinSriLanka -- inter-annotator agreement\n" + "=" * 60)
    p1 = C.REPORTS / "goldset_focused_annotator1.csv"
    p2 = C.REPORTS / "goldset_focused_annotator2.csv"

    try:
        a1 = load_labels(p1)
        a2 = load_labels(p2)
    except (MachineLabelsRefused, FileNotFoundError) as exc:
        print("\nREFUSED\n-------")
        print(exc)
        print("\nNo agreement figure written. This is the correct outcome "
              "when the second pass is not human -- see the module docstring.")
        raise SystemExit(1)

    result = agreement(a1, a2)
    result["caveat"] = (
        "Cohen's kappa between two independent human readers. Claims must "
        "rest on the LOWER bound of the interval, not the point estimate."
    )

    print(f"\nrows labelled by both: {result['n_rows_in_both']}\n")
    print(f"{'aspect':<14} {'n':>4} {'agree%':>7} {'kappa':>7} {'95% CI':>16}  claim")
    print("-" * 70)
    for asp, r in result["presence"].items():
        ci = f"[{r['lo']}, {r['hi']}]" if r["lo"] is not None else "-"
        claim = "substantial" if r["supports_substantial_claim"] else "NOT supported"
        print(f"{asp:<14} {r['n']:>4} {r['percent_agreement']:>6}% "
              f"{r['kappa']:>7} {ci:>16}  {claim}")

    dest = C.REPORTS / "agreement.json"
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
