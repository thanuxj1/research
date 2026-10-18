"""Figures and a written summary of the model comparison, for the thesis and slides.

  python scripts/59_model_comparison_report.py      (after 57 and 58)

Writes reports/model_comparison/
  fig1_topic_models.png        every topic model: CV / unseen test / human gold macro-F1
  fig2_verdict_models.png      every verdict model: CV / unseen test / human gold accuracy
  fig3_training_loss.png       training loss per epoch of the fine-tuned transformers
  fig4_topic_per_topic.png     final topic model vs the old rules, per topic (unseen test)
  fig5_verdict_confusion.png   confusion matrices, final verdict model vs the old chain
  fig6_learning_curve.png      final topic model: score as the training set grows
  MODEL_COMPARISON.md          tables + the selection justification
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from travellens import model_data as M  # noqa: E402

OUT = M.OUT
# validated categorical slots (dataviz reference palette, light): blue, orange, aqua
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, SURF = "#0F172A", "#475569", "#E2E8F0", "#FFFFFF"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": GRID,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": INK,
                     "figure.facecolor": SURF, "axes.facecolor": SURF})

T = json.loads((OUT / "topic_comparison.json").read_text())
V = json.loads((OUT / "verdict_comparison.json").read_text())
FINAL_T, FINAL_V = T["best_by_cv"], V["best_by_cv"]
OLD_T, OLD_V = "M0 Rule lexicon (deployed)", "V3 RoBERTa + correction rules (deployed)"


def short(name):
    return name.split(" ", 1)[1].replace(" (deployed)", " (old system)")


def grouped(ax, names, series, final, xlabel, ceiling=None):
    y = np.arange(len(names))
    h = 0.26
    for k, (label, vals, col) in enumerate(series):
        bars = ax.barh(y + (k - 1) * h, vals, height=h - 0.03, color=col, label=label, edgecolor=SURF, linewidth=1)
        for b, v in zip(bars, vals):
            ax.text(v + 0.006, b.get_y() + b.get_height() / 2, "%.2f" % v, va="center", fontsize=7.5, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([("★ " + short(n)) if n == final else short(n) for n in names])
    for lab, n in zip(ax.get_yticklabels(), names):
        if n == final:
            lab.set_fontweight("bold")
    ax.invert_yaxis()
    ax.set_xlim(0.3, 1.0)
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    if ceiling:
        ax.axvline(ceiling, color=MUTED, linestyle="--", linewidth=1)
        ax.text(ceiling + 0.006, 0, "two humans\nagree: %.2f" % ceiling, ha="left", va="center", fontsize=8.5, color=MUTED)
    ax.legend(loc="lower right", frameon=False, fontsize=9)


def fig1():
    names = T["ranking_by_cv"]
    r = T["models"]
    fig, ax = plt.subplots(figsize=(11, 10.5))
    grouped(ax, names, [("5-fold cross-validation (selection)", [r[n]["cv"]["macro_f1"] for n in names], C1),
                        ("800 unseen random sentences", [r[n]["test_random"]["macro_f1"] for n in names], C2),
                        ("Human gold set (2 readers, 4 topics)", [r[n]["gold_A_reader1"]["macro_f1"] for n in names], C3)],
            FINAL_T, "macro-F1 (higher is better)")
    ax.set_title("Topic detection: 18 models compared (sorted by cross-validation)", loc="left", fontsize=13, color=INK, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig1_topic_models.png", dpi=150)
    plt.close(fig)


def fig2():
    names = V["ranking_by_cv"]
    r = V["models"]
    fig, ax = plt.subplots(figsize=(11, 7))
    grouped(ax, names, [("5-fold cross-validation (selection)", [r[n]["cv"]["accuracy"] for n in names], C1),
                        ("Unseen random test pairs", [r[n]["test_random"]["accuracy"] for n in names], C2),
                        ("Human gold set (reader 1)", [r[n]["gold_A_reader1"]["accuracy"] for n in names], C3)],
            FINAL_V, "accuracy (higher is better)", ceiling=V["human_ceiling_gold_A"]["reader2_vs_reader1_accuracy"])
    ax.set_title("Verdict: 10 models compared (sorted by CV macro-F1)", loc="left", fontsize=13, color=INK, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig2_verdict_models.png", dpi=150)
    plt.close(fig)


def fig3():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, task in zip(axes, ("topic", "verdict")):
        for key, col, lab in (("roberta", C1, "RoBERTa-base (125M)"), ("bge", C2, "bge-small (33M)")):
            p = OUT / ("ft_%s_%s.json" % (task, key))
            if not p.exists():
                continue
            lg = json.loads(p.read_text())
            ep = np.arange(1, len(lg["final_fit_losses"]) + 1)
            cv = np.array(lg["cv"])
            ax.fill_between(ep, cv.min(0), cv.max(0), color=col, alpha=0.12, linewidth=0)
            ax.plot(ep, lg["final_fit_losses"], color=col, linewidth=2, marker="o", markersize=6, label=lab)
            ax.text(ep[-1] + 0.08, lg["final_fit_losses"][-1], "%.3f" % lg["final_fit_losses"][-1], va="center", fontsize=8.5, color=INK)
        ax.set_title("%s task" % ("Topic (multi-label BCE)" if task == "topic" else "Verdict (3-class cross-entropy)"),
                     loc="left", fontsize=11, color=INK)
        ax.set_xlabel("epoch")
        ax.set_xticks([1, 2, 3, 4])
        ax.set_xlim(0.8, 4.5)
        ax.grid(color=GRID, linewidth=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.legend(frameon=False, fontsize=9)
    axes[0].set_ylabel("training loss")
    fig.suptitle("Fine-tuning: training loss falls every epoch (band = range over the 5 CV folds)", x=0.01, ha="left",
                 fontsize=12, color=INK, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig3_training_loss.png", dpi=150)
    plt.close(fig)


def fig4():
    new, old = T["models"][FINAL_T]["test_random"]["per_topic"], T["models"][OLD_T]["test_random"]["per_topic"]
    topics = M.TOPICS
    y = np.arange(len(topics))
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True)
    for ax, metric in zip(axes, ("precision", "recall", "f1")):
        for k, (vals, col, lab) in enumerate(((old, C2, "old rules"), (new, C1, "final model"))):
            v = [vals[t][metric] for t in topics]
            bars = ax.barh(y + (k - 0.5) * 0.38, v, height=0.35, color=col, label=lab, edgecolor=SURF)
            for b, x in zip(bars, v):
                ax.text(x + 0.01, b.get_y() + b.get_height() / 2, "%.2f" % x, va="center", fontsize=7.5, color=INK)
        ax.set_title(metric.upper() if metric == "f1" else metric.capitalize(), loc="left", fontsize=11, color=INK)
        ax.set_xlim(0, 1.12)
        ax.grid(axis="x", color=GRID)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels([M.TOPIC_PHRASE[t] for t in topics])
    axes[0].invert_yaxis()
    h, l = axes[2].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, fontsize=9.5, loc="upper right", ncol=2)
    fig.suptitle("Topic detection on 800 unseen sentences: recall rises, precision holds", x=0.01, ha="left",
                 fontsize=12, color=INK, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig4_topic_per_topic.png", dpi=150)
    plt.close(fig)


def fig5():
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3))
    names = {"N": "complaint", "P": "praise", "X": "fact"}
    for ax, (name, title) in zip(axes, ((OLD_V, "Old system"), (FINAL_V, "Final model"))):
        cm = np.array(V["models"][name]["test_random"]["confusion_rows_true_cols_pred"])
        frac = cm / cm.sum(1, keepdims=True)
        ax.imshow(frac, cmap="Blues", vmin=0, vmax=1)
        for i in range(3):
            for j in range(3):
                ax.text(j, i, "%d\n%.0f%%" % (cm[i, j], 100 * frac[i, j]), ha="center", va="center", fontsize=9,
                        color="white" if frac[i, j] > 0.55 else INK)
        ax.set_xticks(range(3)); ax.set_yticks(range(3))
        ax.set_xticklabels([names[c] for c in M.LABELS]); ax.set_yticklabels([names[c] for c in M.LABELS])
        ax.set_xlabel("predicted"); ax.set_ylabel("true label")
        acc = V["models"][name]["test_random"]["accuracy"]
        ax.set_title("%s - accuracy %.1f%%" % (title, 100 * acc), loc="left", fontsize=11, color=INK)
    fig.suptitle("Verdict confusion matrices on unseen test pairs (rows sum to 100%)", x=0.01, ha="left",
                 fontsize=12, color=INK, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig5_verdict_confusion.png", dpi=150)
    plt.close(fig)


def learning_curve():
    """Final topic model (embeddings + RBF SVM OR lexicon) trained on growing slices."""
    from sklearn.model_selection import KFold
    from sklearn.svm import SVC
    from travellens import aspects as AS
    tr, te = M.load_train(), M.load_test()
    Ytr, Yte = M.presence(tr).values, M.presence(te).values
    Etr, Ete = np.load(OUT / "emb_train.npy"), np.load(OUT / "emb_test_random.npy")
    Lte = np.array([[t in set(AS.tag_segment(s)) for t in M.TOPICS] for s in te.segment]).astype(int)
    Ltr = np.array([[t in set(AS.tag_segment(s)) for t in M.TOPICS] for s in tr.segment]).astype(int)

    def f1(p, g):
        tp = (p & g).sum(); fp = (p & ~g).sum(); fn = (~p & g).sum()
        return 2 * tp / (2 * tp + fp + fn) if tp else 0.0

    rng = np.random.default_rng(42)
    sizes, scores = [], []
    for frac in (0.1, 0.2, 0.35, 0.5, 0.7, 0.85, 1.0):
        vals = []
        for rep in range(3 if frac < 1 else 1):
            idx = rng.permutation(len(tr))[:int(frac * len(tr))]
            fs = []
            for j in range(len(M.TOPICS)):
                y = Ytr[idx, j]
                if y.sum() < 3:
                    p = Lte[:, j].astype(bool)
                else:
                    # threshold from inner 3-fold out-of-fold scores, as in script 57
                    oof = np.zeros(len(idx))
                    for a, b in KFold(3, shuffle=True, random_state=rep).split(idx):
                        m = SVC(C=4, kernel="rbf", class_weight="balanced").fit(Etr[idx[a]], y[a])
                        oof[b] = m.decision_function(Etr[idx[b]])
                    s = np.where(Ltr[idx, j] > 0, np.inf, oof)
                    cands = np.unique(np.quantile(oof, np.linspace(0.5, 0.995, 60)))
                    th = cands[int(np.argmax([f1(s >= c, y.astype(bool)) for c in cands]))]
                    m = SVC(C=4, kernel="rbf", class_weight="balanced").fit(Etr[idx], y)
                    p = (m.decision_function(Ete) >= th) | Lte[:, j].astype(bool)
                fs.append(f1(p, Yte[:, j].astype(bool)))
            vals.append(np.mean(fs))
        sizes.append(int(frac * len(tr)))
        scores.append((float(np.mean(vals)), float(np.min(vals)), float(np.max(vals))))
        print("  learning curve n=%d macro-F1 %.3f" % (sizes[-1], scores[-1][0]), flush=True)
    lex = T["models"][OLD_T]["test_random"]["macro_f1"]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    m_ = [s[0] for s in scores]
    ax.fill_between(sizes, [s[1] for s in scores], [s[2] for s in scores], color=C1, alpha=0.15, linewidth=0)
    ax.plot(sizes, m_, color=C1, linewidth=2, marker="o", markersize=6, label="final topic model")
    ax.axhline(lex, color=C2, linewidth=2, linestyle="--", label="old rules (no training): %.2f" % lex)
    for x, v in zip(sizes, m_):
        ax.text(x, v + 0.012, "%.2f" % v, ha="center", fontsize=8, color=INK)
    ax.set_xlabel("training sentences"); ax.set_ylabel("macro-F1 on 800 unseen sentences")
    ax.grid(color=GRID); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_ylim(min(lex, min(m_)) - 0.02, max(m_) + 0.03)
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("Learning curve: more labelled data, better topic detection", loc="left", fontsize=12, color=INK, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig6_learning_curve.png", dpi=150)
    plt.close(fig)
    return {"sizes": sizes, "macro_f1": [round(v, 3) for v in m_]}


def pfmt(p):
    return "< 0.001" if p < 0.001 else "= %.3f" % p


def markdown(lc):
    t, v = T["models"], V["models"]
    ft, fv = t[FINAL_T], v[FINAL_V]
    rows_t = "\n".join("| %s%s | %s | %.3f ± %.3f | %.3f | %.3f | %.3f | %.3f | %.3f |" % (
        "**" if n == FINAL_T else "", short(n) + ("**" if n == FINAL_T else ""), t[n]["meta"]["family"],
        t[n]["cv"]["macro_f1"], t[n]["cv"]["fold_sd"], t[n]["test_random"]["macro_precision"],
        t[n]["test_random"]["macro_recall"], t[n]["test_random"]["macro_f1"], t[n]["test_random"]["micro_f1"],
        t[n]["gold_A_reader1"]["macro_f1"]) for n in T["ranking_by_cv"])
    rows_v = "\n".join("| %s%s | %s | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f |" % (
        "**" if n == FINAL_V else "", short(n) + ("**" if n == FINAL_V else ""), v[n]["meta"]["family"],
        v[n]["cv"]["macro_f1"], v[n]["test_random"]["accuracy"], v[n]["test_random"]["macro_f1"],
        v[n]["test_random"]["kappa"], v[n]["gold_A_reader1"]["accuracy"], v[n]["gold_A_readers_agree"]["accuracy"])
        for n in V["ranking_by_cv"])
    per_t = "\n".join("| %s | %.2f | %.2f | %.2f | %.2f |" % (
        M.TOPIC_PHRASE[k], t[OLD_T]["test_random"]["per_topic"][k]["f1"], ft["test_random"]["per_topic"][k]["precision"],
        ft["test_random"]["per_topic"][k]["recall"], ft["test_random"]["per_topic"][k]["f1"]) for k in M.TOPICS)
    mc = V["best_vs_deployed_mcnemar"]
    runner_t = T["ranking_by_cv"][1]
    md = f"""# Model comparison: training, testing and selection

Component: Dynamic Safety Heatmap and Complaint Analytics Engine (LostinSriLanka).
Generated by `scripts/59_model_comparison_report.py` from `topic_comparison.json` and `verdict_comparison.json`.

## The two tasks
1. **Topic detection** - multi-label: which of 7 topics a review sentence mentions (one binary classifier per topic).
2. **Verdict** - 3-class aspect-based sentiment: for a (topic, sentence) pair, complaint (N), praise (P) or fact (X).

## Data and protocol
| Set | Size | Labels | Role |
|---|---|---|---|
| Training | {T['data']['train_sentences']:,} sentences; {V['data']['train']['pairs']:,} verdict pairs | AI-annotated (Claude), calibrated against human readers; + 420 human verdict pairs | training, 5-fold CV, threshold choice, **model selection** |
| Unseen test | {T['data']['test_random_sentences']} random sentences; {V['data']['test_random']['pairs']} pairs | AI-annotated | scored once, after selection |
| Human gold | {T['data']['gold_A_sentences']} representative (+{T['data']['gold_B_sentences']} contested) sentences; {V['data']['gold_A']['pairs']} pairs | two independent human readers | independent check |

**Selection rule, fixed before any test score was seen:** the model with the highest 5-fold cross-validated
macro-F1 on the training set; within 0.01 of the best, the simpler/faster model is preferred.
Decision thresholds are chosen on out-of-fold training scores only, so the test sets never influence a choice.

## Task 1 - topic detection (macro-F1 unless stated)
| Model | Family | CV macro-F1 ± sd | Test precision | Test recall | **Test macro-F1** | Test micro-F1 | Human gold |
|---|---|---|---|---|---|---|---|
{rows_t}

**Final model: {short(FINAL_T)}.** Highest cross-validated macro-F1 ({ft['cv']['macro_f1']:.3f}); runner-up
{short(runner_t)} ({t[runner_t]['cv']['macro_f1']:.3f}) is within 0.01 and is a 125M-parameter transformer, so the
simpler-model rule also favours the SVM hybrid. On the unseen test it scores **{ft['test_random']['macro_f1']:.3f}**
macro-F1 (95% CI {ft['test_random']['macro_f1_ci95'][0]:.2f}-{ft['test_random']['macro_f1_ci95'][1]:.2f}) against
{t[OLD_T]['test_random']['macro_f1']:.3f} for the old rules: recall {t[OLD_T]['test_random']['macro_recall']:.2f} ->
{ft['test_random']['macro_recall']:.2f} at precision {ft['test_random']['macro_precision']:.2f}. Learning curve (fig 6):
macro-F1 {lc['macro_f1'][0]:.2f} with {lc['sizes'][0]} sentences -> {lc['macro_f1'][-1]:.2f} with {lc['sizes'][-1]} (thresholds re-chosen by an
inner 3-fold CV at each size, so the last point differs slightly from the table).

| Topic | Old rules F1 | Final precision | Final recall | **Final F1** |
|---|---|---|---|---|
{per_t}

## Task 2 - verdict (complaint / praise / fact)
| Model | Family | CV macro-F1 | **Test accuracy** | Test macro-F1 | Test kappa | Human gold accuracy | Where both humans agree |
|---|---|---|---|---|---|---|---|
{rows_v}

Human ceiling: the two readers agree on {100 * V['human_ceiling_gold_A']['reader2_vs_reader1_accuracy']:.1f}% of gold pairs (kappa {V['human_ceiling_gold_A']['kappa']:.2f}).

**Final model: {short(FINAL_V)}.** Highest cross-validated macro-F1 ({fv['cv']['macro_f1']:.3f}), and on the unseen test
**{100 * fv['test_random']['accuracy']:.1f}% accuracy** (95% CI {100 * fv['test_random']['accuracy_ci95'][0]:.1f}-{100 * fv['test_random']['accuracy_ci95'][1]:.1f}%),
macro-F1 {fv['test_random']['macro_f1']:.3f}, against {100 * v[OLD_V]['test_random']['accuracy']:.1f}% for the old system.
McNemar test against the old system: unseen test {mc['test_random']['only_first_right']} vs {mc['test_random']['only_second_right']}
discordant pairs (p {pfmt(mc['test_random']['p_value'])}); human gold {mc['gold_A']['only_first_right']} vs {mc['gold_A']['only_second_right']} (p {pfmt(mc['gold_A']['p_value'])}).
Fine-tuning: AdamW, lr 2e-5, 4 epochs, batch 16, max length 96, linear warm-up/decay, seed 42; loss per epoch in fig 3.

## Honest limits
* Training and random-test labels are AI annotations (validated against two human readers: presence kappa 0.70-0.98,
  versus 0.69-0.93 between the humans); the human gold set is the independent check and covers four topics.
* Trade-off seen in the confusion matrix (fig 5): the final verdict model finds far more complaints (recall
  {100 * fv['test_random']['per_class']['N']['recall']:.0f}% vs {100 * v[OLD_V]['test_random']['per_class']['N']['recall']:.0f}%) but labels fewer plain facts as facts
  ({100 * fv['test_random']['per_class']['X']['recall']:.0f}% vs {100 * v[OLD_V]['test_random']['per_class']['X']['recall']:.0f}%). Complaint rates count N against P, so the gain on N matters more.
* The human gold set was drawn from sentences the old rules had tagged, which favours the rules on that set; the
  random test set is the fair comparison for recall.
"""
    (OUT / "MODEL_COMPARISON.md").write_text(md, encoding="utf8")


def main():
    fig1(); fig2(); fig3(); fig4(); fig5()
    lc = learning_curve()
    (OUT / "learning_curve.json").write_text(json.dumps(lc), encoding="utf8")
    markdown(lc)
    print("final topic:", FINAL_T, "| final verdict:", FINAL_V)


if __name__ == "__main__":
    main()
