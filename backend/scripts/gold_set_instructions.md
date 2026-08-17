# Gold Set Annotation Protocol — SafeTravel LK
IT22629180

> **Purpose**: Establish a 388-record hand-labelled evaluation corpus to replace the
> circular self-evaluation currently in `show_model_accuracy.py`. This corpus is the
> only honest measure of the system's precision/recall.

---

## What is the Gold Set?

A **gold set** is a collection of records where the ground-truth labels are known
independently of the model under evaluation. It is used to compute:

- **Precision** — fraction of model-flagged records that are genuinely scam/safety incidents
- **Recall** — fraction of genuine incidents that the model successfully detected
- **F1-score** — harmonic mean of precision and recall
- **Geocoding accuracy** — fraction of records correctly assigned to their true district

---

## Corpus

| Corpus | Size | Location |
|---|---|---|
| Safety DB records | 188 | `backend/safety.db` — `reports` table |
| TripAdvisor/Google reviews | ~200 | `backend/training/dataset/*.csv` |

Label **both corpora separately** and report metrics per corpus. The two corpora have
different base rates (reviews are noisier; news articles are more reliable) so pooling
them hides that difference.

---

## Label Schema

Each record should receive:

| Field | Values |
|---|---|
| `gold_is_scam` | `1` = confirmed safety incident, `0` = not a safety incident |
| `gold_scam_type` | canonical key from `scam_taxonomy.py`, or `"not_scam"` |
| `gold_location` | correct district name, or `"national"` if no specific district |
| `gold_confidence` | `"high"` (annotator certain) / `"low"` (annotator uncertain) |
| `notes` | free text |

---

## Annotation Procedure

### Step 1 — Export records to CSV

```bash
cd backend
python -c "
from app.db.database import SessionLocal
from app.db.models import Report
import csv, datetime

db = SessionLocal()
records = db.query(Report).all()
with open('scripts/gold_set_export.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['id','source','title','content','is_scam_model','scam_type_model',
                'location_name_model','geocode_confidence','published_at',
                'gold_is_scam','gold_scam_type','gold_location','gold_confidence','notes'])
    for r in records:
        w.writerow([r.id, r.source, r.title, r.content[:300], r.is_scam, r.scam_type,
                    r.location_name, r.geocode_confidence, r.published_at,
                    '', '', '', '', ''])
db.close()
print(f'Exported {len(records)} records')
"
```

### Step 2 — Annotate in Excel / Google Sheets

1. Open `scripts/gold_set_export.csv`
2. Read title + first 300 chars of content
3. Fill in `gold_is_scam`, `gold_scam_type`, `gold_location`, `gold_confidence`
4. Mark `gold_confidence = "low"` if the record is ambiguous — exclude `"low"` from the final metrics

**Decision rules**:
- A record is `gold_is_scam=1` if it describes a specific incident (however minor) where a tourist was deceived, harassed, overcharged, or placed at risk.
- A record is `gold_is_scam=0` if it is a general travel tip, review of a hotel/restaurant with no safety incident, or opinion piece.
- For `gold_location`: if the article mentions multiple districts in passing but the incident clearly happened in one, assign that one. If it is national-scope (no specific district), assign `"national"`.

### Step 3 — Inter-annotator agreement (required for thesis)

Have a second person independently label a random 10% sample (~40 records).
Compute Cohen's κ on `gold_is_scam`. Target κ ≥ 0.70.

```python
from sklearn.metrics import cohen_kappa_score
kappa = cohen_kappa_score(annotator_1_labels, annotator_2_labels)
print(f"Inter-annotator κ = {kappa:.3f}")
```

Report this κ value in the methodology chapter.

### Step 4 — Compute evaluation metrics

```bash
cd backend
python scripts/evaluate_gold_set.py --gold scripts/gold_set_annotated.csv
```

(See `evaluate_gold_set.py` — to be implemented after annotation.)

---

## What to Report in the Thesis

For each corpus (safety DB, review CSV):

| Metric | Value |
|---|---|
| Precision (scam detection) | X.XX |
| Recall (scam detection) | X.XX |
| F1-score (scam detection) | X.XX |
| Geocoding accuracy | X.XX |
| `body_mention` exclusion rate | X.XX (should reduce Colombo over-attribution) |
| Records with `gold_confidence=low` (excluded) | N |
| Inter-annotator κ | X.XX |

Do NOT pool the two corpora in a single accuracy figure without reporting the per-corpus breakdown.

---

## Timeline

| Phase | Target |
|---|---|
| Export + first annotator labels | 2 weeks |
| Second-annotator agreement sample | +1 week |
| `evaluate_gold_set.py` implementation and run | +1 week |
| Thesis integration | +1 week |
