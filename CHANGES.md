# CHANGES — District Risk Map Rebuild

This patch adds a district-level, confidence-aware, exposure-normalised risk
choropleth alongside the existing point-heatmap, and fixes the scoring logic
that was causing every zone to render as "High Risk." Full rationale for every
number/threshold below is in `docs/DISTRICT_RISK_METHODOLOGY.md`.

## New files
- `backend/app/data/sri_lanka_districts.geojson` — 22 district boundary polygons
- `backend/app/ml/exposure_baseline.py` — SLTDA footfall registry (honest about coverage gaps)
- `backend/app/core/district_engine.py` — the new scoring/aggregation engine
- `backend/app/api/endpoints/districts.py` — `/api/v1/districts/risk-map` and `/methodology`
- `docs/DISTRICT_RISK_METHODOLOGY.md` — full methodology write-up for your panel

## Modified files
- `backend/requirements.txt` — added `shapely>=2.0` (point-in-polygon lookups)
- `backend/app/main.py` — registered the new `districts` router
- `frontend/src/map.js` — added `renderDistrictChoropleth()`, `toggleDistrictChoropleth()`,
  and supporting tooltip/popup/legend methods on `SafetyMap`. Nothing existing was removed;
  the point heatmap/circle-marker code is untouched and still works standalone.
- `frontend/src/main.js` — fetches `/districts/risk-map` on load, renders it, wires the
  new toggle checkbox
- `frontend/index.html` — added a "District Risk Map (shaded)" toggle in the top-left panel
- `frontend/src/style.css` — added legend + tooltip styles for the new layer

## Nothing else was touched
The data pipeline (`data_pipeline/`), NLP classifier (`app/ml/nlp_pipeline.py`), the
point-level `app/core/scoring.py`/`clustering.py`, and all other endpoints are
unchanged. This patch is additive and can be reviewed/reverted independently of
the rest of the system.

## To run it
```
cd backend
pip install -r requirements.txt --break-system-packages   # picks up shapely
uvicorn app.main:app --reload
```
```
cd frontend
npm install
npm run dev
```
Then open the app — the shaded district layer loads automatically, on top of
(or instead of, via the new toggle) the existing point heatmap.

## What to check first
1. Toggle "District Risk Map (shaded)" on/off — the two layers are independent.
2. Hover a district — tooltip shows tier, confidence, report count, and whether
   SLTDA exposure data was available.
3. Click a district — full popup with score breakdown, top scam types, and
   linked recent reports.
4. `GET /api/v1/districts/methodology` — live JSON of every constant, for
   defending the numbers to a reviewer without relying only on this document.
