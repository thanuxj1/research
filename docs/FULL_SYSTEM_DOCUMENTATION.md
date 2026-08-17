# SafeTravel LK — Full System Documentation
### IT22629180 | PhD Research: Tourist Safety Intelligence for Sri Lanka

---

## TABLE OF CONTENTS
1. [System Overview](#1-system-overview)
2. [Data Collection Pipeline](#2-data-collection-pipeline)
3. [Datasets](#3-datasets)
4. [Database Architecture](#4-database-architecture)
5. [NLP & ML Models](#5-nlp--ml-models)
6. [Training Pipelines](#6-training-pipelines)
7. [Backend API Architecture](#7-backend-api-architecture)
8. [Core Intelligence Engine](#8-core-intelligence-engine)
9. [Frontend — Page 1: District Safety Map](#9-frontend--page-1-district-safety-map)
10. [Frontend — Page 2: Research Analytics Dashboard](#10-frontend--page-2-research-analytics-dashboard)
11. [AI Chat Advisor](#11-ai-chat-advisor)
12. [Admin & Maintenance Tools](#12-admin--maintenance-tools)
13. [Source Credibility System](#13-source-credibility-system)
14. [Scoring Methodology](#14-scoring-methodology)

---

## 1. SYSTEM OVERVIEW

**SafeTravel LK** is a PhD-level tourist safety intelligence system for Sri Lanka. It aggregates 16,000+ cross-referenced incident reports from news media, social platforms, government advisories, and traveler reviews, then computes **real-time safety verdicts** for any GPS coordinate or district using **Inverse Distance Weighted (IDW) spatial interpolation** with temporal decay and multi-tier source credibility weighting.

### Architecture at a Glance

```
Raw Sources (News / Reddit / YouTube / TripAdvisor / Gov Advisories)
        │
        ▼
Data Pipeline (scraper + strict relevance filter)
        │
        ▼
SQLite Database  ◄──────  NLP Pipeline (TF-IDF + RandomForest + HuggingFace)
        │
        ▼
FastAPI Backend (10 routers)
        │
        ├─► Safety Intelligence Engine  (IDW Scoring + Verdict)
        ├─► District Risk Engine        (Choropleth Map)
        ├─► AI Chat (Gemini 1.5-flash)
        └─► Analytics Engine
        │
        ▼
React/Vite Frontend
        ├─► Page 1: SVG District Risk Map + Incident Panel
        └─► Page 2: Research Analytics Dashboard
```

### Technology Stack

| Layer | Technology |
|---|---|
| Backend Framework | FastAPI (Python 3.11) |
| Database | SQLite (dev) / PostgreSQL+PostGIS (prod) |
| ORM | SQLAlchemy 2.0 |
| ML / NLP | scikit-learn, HuggingFace Transformers, joblib |
| LLM (Chat) | Google Gemini 1.5-flash |
| Spatial Analysis | Shapely 2.0, GeoAlchemy2 |
| Task Scheduler | APScheduler (CronTrigger) |
| Frontend | React 19 + Vite 4, Recharts, Leaflet |
| Styling | Vanilla CSS (no Tailwind) |

---

## 2. DATA COLLECTION PIPELINE

All scrapers live under `backend/data_pipeline/`. The system uses a **3-tier collection strategy**:

### 2.1 Automated Startup Collection

On every API startup (`app/main.py`), two automated systems are launched:

```python
# Daily deep scraper — 2:00 AM every day
scheduler.add_job(run_daily_collection, CronTrigger(hour=2, minute=0))

# Continuous high-frequency scraper — always running
subprocess.Popen([sys.executable, "data_pipeline/continuous_runner.py"])
```

### 2.2 News Scraper v3 (`data_pipeline/scrape_sl_news_v3.py`)

The primary news ingestion engine. Runs **80+ targeted queries** across 4 groups:

| Query Group | Count | Examples |
|---|---|---|
| Core Safety Queries | 8 | "tourist scam Sri Lanka", "tourist robbed Sri Lanka" |
| SLTDA / Tourist Police | 10 | "SLTDA tourist complaint", "travel warning Sri Lanka" |
| Scam-Type Specific | 14 | "gem scam tourist", "fake guide Sri Lanka", "drink spiked" |
| District Gap Queries | 17 | "tourist safety Batticaloa", "Wilpattu safari scam" |
| Headline Patterns | 12 | "tourist cheated Sri Lanka", "backpacker scam" |

**News Sources Scraped (11 Sri Lankan outlets):**

| Outlet | Domain | Source Weight |
|---|---|---|
| Daily Mirror | dailymirror.lk | 0.72 |
| Sunday Times | sundaytimes.lk | 0.75 |
| Ada Derana | adaderana.lk | 0.70 |
| NewsFirst / Sirasa | newsfirst.lk | 0.65 |
| Hiru News | hirunews.lk | 0.60 |
| Newswire.lk | newswire.lk | 0.63 |
| Ceylon Today | ceylontoday.lk | 0.63 |
| EconomyNext | economynext.com | 0.65 |
| Financial Times LK | ft.lk | 0.65 |
| Daily News | dailynews.lk | 0.65 |
| The Island | island.lk | 0.68 |

**Government Advisory Sources (Tier-0, weight = 1.00):**
- UK FCDO (`gov.uk`) — highest credibility
- Australia Smartraveller (`smartraveller.gov.au`)
- US State Dept (`travel.state.gov`)

**Ingestion flow:**
```
Google News RSS → Filter by relevance → Fetch article body → NLP classify → SQLite insert
```

**Deduplication:**
- URL exact match
- Title similarity (first 60 chars, case-insensitive ILIKE match)

### 2.3 Social & Community Collectors (`data_pipeline/collectors/`)

| Collector | File | Target |
|---|---|---|
| Reddit | `reddit.py` | r/srilanka, r/travel — safety-tagged posts |
| YouTube | `youtube.py` | Travel vlog transcripts with safety keywords |
| Google Maps | `google_maps.py` | Location reviews (geocoded) |
| Social Media | `social.py` | Multi-platform social posts |
| Travel Forums | `travel_forums.py` | TripAdvisor forums, Lonely Planet Thorn Tree |
| Web Scraper | `web.py` | General safety article scraping |

### 2.4 TripAdvisor Reviews Ingestion (`backend/ingest_reviews_csv.py`)

Ingests the 16,156-record TripAdvisor `Destination Reviews (final).csv`:
- Geocodes each review to lat/lon via `SL_LOCATIONS` dictionary (25+ destinations)
- Applies NLP pipeline to classify sentiment, scam type, risk level
- Assigns `source_weight = 0.60` (Tier: Review)

### 2.5 Strict Relevance Filter (`data_pipeline/strict_filter.py`)

Every article passes a dual-gate filter before DB insertion:

**Gate 1 — Tourism keyword gate:** Must contain at least one strong tourism word (tourist, traveler, tuk tuk, guide, safari, hotel, backpacker) OR two general tourism words.

**Gate 2 — Hard Exclusion List:** Articles matching these patterns are rejected:
- Foreign nationals arrested for cybercrime
- Domestic political/electoral news
- Labor disputes, migrant worker issues
- Military/police internal affairs
- Weather/disaster management (non-safety)
- International crime not involving tourists

**Gate 3 — AI Scope Verification (when HuggingFace available):**
Zero-shot classification confirms the article is "Tourist Safety Incident" vs. "General News / Political News / Crime by Foreigners" — minimum 60% confidence required.

---

## 3. DATASETS

### 3.1 Primary Datasets

| Dataset | File | Size | Description |
|---|---|---|---|
| Derana News Archive | `dataset/Derana_News.csv` | 509 MB | Full Ada Derana news archive (2010–2024) |
| Destination Reviews (final) | `dataset/Destination Reviews (final).csv` | 3.7 MB | 16,156 TripAdvisor reviews, cleaned & labeled |
| Destination Reviews (raw) | `dataset/Destination Reviews_(raw).csv` | 5.6 MB | Raw TripAdvisor before cleaning |
| All Reviews | `dataset/Reviews.csv` | 9.2 MB | Combined review dataset for ML training |
| Sri Lanka Weather V1 | `dataset/SriLanka_Weather_Dataset_V1.csv` | 20 MB | Historical weather data |
| Sri Lanka Weather V2 | `dataset/SriLanka_Weather_Dataset.csv` | 23 MB | Updated weather dataset |
| News Archive | `dataset/news.csv` | 89 MB | General SL news archive |
| Tourism Arrivals | `dataset/sl_tourism_arrivals_clean.csv` | 1.7 KB | Annual visitor counts by year |
| Country-wise Arrivals | `dataset/sl_tourism_country_wise_final.csv` | 471 KB | Tourist arrivals by source country |

### 3.2 Database Records

The live SQLite database (`safety_heatmap.db`, ~422 KB) stores all processed incident reports in the `reports` table with full NLP annotations and geospatial coordinates.

### 3.3 Canonical Destinations

`backend/canonical_destinations.csv` — 25 Sri Lanka tourist destinations with standardized names, coordinates, district mapping, and expected visitor volumes used for geocoding normalization.

---

## 4. DATABASE ARCHITECTURE

### 4.1 Engine

**Development:** SQLite (`backend/safety_heatmap.db`)  
**Production:** PostgreSQL with PostGIS extension  
**ORM:** SQLAlchemy 2.0 with automatic fallback:

```python
# session.py — tries PostgreSQL first, silently falls back to SQLite
try:
    engine = create_engine(pg_uri, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("[DB] Connected to PostgreSQL")
except:
    sqlite_uri = f"sqlite:///{db_path}"
    engine = create_engine(sqlite_uri, connect_args={"check_same_thread": False})
```

### 4.2 Schema

#### Table: `reports` (primary table)

| Column | Type | Description |
|---|---|---|
| `id` | Integer PK | Auto-increment primary key |
| `source` | String | Source identifier: "reddit", "adaderana", "tripadvisor", "youtube", etc. |
| `url` | String | Original source URL (used for deduplication) |
| `title` | String | Article/post/review title |
| `content` | Text | Full text content (up to 3000 chars) |
| `sentiment_score` | Float | −1.0 (very negative) to +1.0 (very positive) |
| `is_scam` | Boolean | True if classified as a scam/safety incident |
| `scam_type` | String | e.g. "tuk_tuk_scam", "gem_scam", "harassment", "theft" |
| `risk_level` | Integer | 1=Low, 2=Moderate, 3=High |
| `latitude` | Float | Geocoded latitude (nullable) |
| `longitude` | Float | Geocoded longitude (nullable) |
| `location_point` | Geometry | PostGIS POINT (or WKT text in SQLite) |
| `location_name` | String | Human-readable location: "Colombo", "Kandy", etc. |
| `demographic_target` | String | "solo_female", "family", "backpacker", "Tourists" |
| `source_weight` | Float | 0.0–1.0 credibility score (from source_weights.py) |
| `helpful_votes` | Integer | Peer upvotes / TripAdvisor helpful count |
| `created_at` | DateTime | Ingestion timestamp (UTC) |

#### Table: `risk_zones` (generated by DBSCAN clustering)

| Column | Type | Description |
|---|---|---|
| `id` | Integer PK | Auto-increment primary key |
| `cluster_id` | Integer | Unique cluster identifier |
| `zone_polygon` | Geometry | PostGIS POLYGON bounding the cluster |
| `center_point` | Geometry | Centroid POINT |
| `risk_score` | Float | Composite risk score 0.0–1.0 |
| `primary_scam_type` | String | Most common scam type in this zone |
| `report_count` | Integer | Number of reports in cluster |
| `last_updated` | DateTime | Last reclustering timestamp |

---

## 5. NLP & ML MODELS

### 5.1 NLP Pipeline (`app/ml/nlp_pipeline.py`)

A **hybrid two-tier classifier** with graceful degradation:

#### Tier 1 — Fast sklearn TF-IDF + RandomForest
- Loaded from `app/ml/models/scam_classifier.joblib` (11.9 MB)
- Provides sub-millisecond classification
- Falls back to rule-based keyword matching if model file absent

#### Tier 2 — HuggingFace Transformers (optional)
- **Sentiment:** `cardiffnlp/twitter-roberta-base-sentiment-latest`
- **Zero-shot classification:** `typeform/distilbert-base-uncased-mnli`
- Loaded only if `transformers` package is available (graceful degradation)

#### Processing Pipeline (7 steps)

```
Input Text
    │
    ├─ Step 1: Tourism relevance gate (strong keyword OR 2+ general keywords)
    ├─ Step 2: Scam type detection (keyword taxonomy → 12 categories)
    ├─ Step 3: Is-scam classification (sklearn model → rule fallback)
    ├─ Step 4: Sentiment analysis (HuggingFace → TextBlob → keyword)
    ├─ Step 5: Risk level computation (1=Low, 2=Moderate, 3=High)
    ├─ Step 6: AI scope check (zero-shot if no scam type found)
    └─ Step 7: Location extraction (25+ SL location dictionary)
```

#### Scam Taxonomy (12 categories)

| Category | Key Signals |
|---|---|
| Gem Scam | "fake gem", "gem shop scam", "sapphire scam", "overpriced gem" |
| Commission Shop | "commission shop", "driver commission", "spice garden scam" |
| Tuk Tuk Scam | "tuk tuk overcharged", "tuk tuk driver lied", "tuk tuk rip off" |
| Overcharging | "overcharged", "double price", "tourist price", "inflated price" |
| Fake Guide | "fake guide", "unauthorized guide", "demanded money", "fake monk" |
| Transport Fraud | "taxi scam", "refused meter", "tampered meter", "airport taxi" |
| Accommodation Scam | "hotel scam", "bait switch", "fake booking", "different room" |
| Food/Menu Scam | "fake menu", "tourist menu", "overcharged food" |
| Theft / Robbery | "pickpocket", "bag snatched", "phone stolen", "mugged" |
| Physical Assault | "attack", "assault", "beaten", "physical altercation" |
| Harassment | "followed", "groped", "catcalling", "stalked", "beach boy" |
| Accident / Hazard | "crash", "injured", "hospital", "dangerous road" |

#### Sentiment Scoring

- **Primary:** HuggingFace RoBERTa → score mapped to −1.0/+1.0
- **Fallback:** TextBlob polarity
- **Last resort:** Keyword ratio (negative/positive word count)

### 5.2 Trained Model Files (`app/ml/models/`)

| File | Size | Description |
|---|---|---|
| `scam_classifier.joblib` | 11.9 MB | TF-IDF + RandomForest, trained on all ingested reports |
| `enhanced_predictor.joblib` | 6.7 MB | Gradient Boosting + RandomForest ensemble (risk predictor) |
| `enhanced_meta.joblib` | 2.2 KB | Encoder metadata for the enhanced predictor |
| `pattern_rf.joblib` | 1.4 MB | Pattern RandomForest (legacy pattern predictor) |
| `pattern_meta.joblib` | 3.8 KB | Pattern metadata |
| `pattern_insights.json` | 43 KB | Seasonal risk, city profiles, location-type risk (36 cities) |

### 5.3 Pattern Insights JSON Structure

The `pattern_insights.json` file is generated by training and used directly by the frontend:

```json
{
  "patterns": [...],          // top 50 scam patterns from Reviews.csv
  "seasonal_risk": {          // month → risk boost factors
    "1": 0.15, "7": 0.20, ...
  },
  "location_type_risk": {     // venue type → base risk
    "Beaches": 0.3175,
    "Historic Sites": 0.2589,
    "Zoological Gardens": 0.3662,
    "Religious Sites": 0.2360
  },
  "city_profiles": {          // 36 Sri Lankan cities with full stats
    "Colombo": {
      "total_reviews": 412,
      "negative_reviews": 38,
      "scam_mentions": 22,
      "avg_rating": 3.89,
      "risk_score": 0.3814,
      "peak_complaint_months": [1, 3, 7, 11]
    }
    // ... 35 more cities
  }
}
```

---

## 6. TRAINING PIPELINES

### 6.1 Enhanced Model Training (`training/train_enhanced_model.py`)

Triggered automatically on startup if `enhanced_predictor.joblib` does not exist. Also runnable manually.

**Training Data Sources:**
1. `Reviews.csv` — processed by `ReviewAnalyzer` class
2. `safety_heatmap.db` — all geolocated reports

**Feature Matrix (10 features):**

| Feature | Source | Description |
|---|---|---|
| `lat_bin` | GPS | Latitude rounded to 2 decimal places |
| `lon_bin` | GPS | Longitude rounded to 2 decimal places |
| `month` | Review date | Month of year (1–12) |
| `loc_type_risk` | Pattern insights | Location venue type risk baseline |
| `month_boost` | Pattern insights | Seasonal risk multiplier for that month |
| `is_scam_flag` | NLP output | Binary scam classification |
| `neg_score` | Review analysis | Number of negative sentiment signals (0–5) |
| `is_experienced` | Reviewer metadata | TripAdvisor contribution count > 100 |
| `scam_type_enc` | Label encoder | Encoded scam taxonomy category |
| `source_enc` | Label encoder | Encoded data source identifier |

**Target Variable:** `risk_level` (1=Low, 2=Moderate, 3=High), clamped to [1, 3]

**Model Architecture — Soft Voting Ensemble:**

```python
GradientBoostingClassifier(
    n_estimators=200, max_depth=5,
    learning_rate=0.08, min_samples_leaf=3
)
+
RandomForestClassifier(
    n_estimators=200, max_depth=8,
    class_weight="balanced", n_jobs=-1
)

VotingClassifier(voting="soft", weights=[0.55, 0.45])
```

**Training Split:** 80/20 train/test, stratified by risk_level  
**Evaluation:** 5-fold cross-validation + classification report + confusion matrix

**Output Artifacts:**
- `enhanced_predictor.joblib` — trained ensemble
- `enhanced_meta.joblib` — encoders + accuracy + feature importance
- `pattern_insights.json` — city profiles + seasonal calendar

### 6.2 Scam Classifier Training (`training/train_classifier.py`)

Trains the binary TF-IDF + RandomForest classifier on all reports in the DB:
- Features: TF-IDF vectorized text (title + content)
- Labels: `is_scam` boolean
- Output: `scam_classifier.joblib`

### 6.3 Primary Dataset Builder (`training/build_primary_dataset.py`)

Assembles the master training dataset from all sources:
- Merges DB reports with CSV reviews
- Applies NLP labels
- Exports clean labeled dataset for offline analysis

---

## 7. BACKEND API ARCHITECTURE

### 7.1 Entry Point (`app/main.py`)

FastAPI app with CORS enabled for all origins. On startup:
1. Schedules daily deep scraper (2:00 AM CronTrigger)
2. Launches continuous real-time scraper subprocess
3. Triggers enhanced model training if model missing (background thread)

### 7.2 API Routers (10 endpoints)

All routes prefixed with `/api/v1/`:

| Router | Prefix | Key Endpoints |
|---|---|---|
| `reports` | `/reports` | CRUD for incident reports |
| `safety` | `/safety` | `/assess`, `/heatmap`, `/location-search`, `/safe-zones` |
| `districts` | `/districts` | `/risk-map` (GeoJSON), `/{name}/reports` |
| `admin` | `/admin` | DB stats, purge tools, data quality management |
| `pipeline` | `/pipeline` | Trigger scraping runs manually |
| `ml` | `/ml` | Model predictions, feature importance |
| `advisor` | `/advisor` | Personalized safety advice by profile |
| `authority` | `/authority` | Police/SLTDA contact dispatching |
| `analytics` | `/analytics` | `/dashboard` — live research analytics |
| `chat` | `/advisor/chat` | AI conversational endpoint (Gemini) |

### 7.3 Key Safety Endpoints

#### `GET /api/v1/safety/assess`
**The core safety intelligence endpoint.**

Parameters:
- `lat` (float) — latitude of query point
- `lng` (float) — longitude
- `radius_km` (float, default 15.0) — search radius
- `sort_by` (string) — "credibility" | "nearest" | "risk"

Returns:
```json
{
  "verdict": "MODERATE RISK",
  "verdict_color": "orange",
  "composite_score": 0.412,
  "confidence": "High",
  "scam_types": {"Tuk-Tuk Overcharging": 5, "Gem Scam": 3},
  "safety_tips": ["Always agree on price before entering tuk-tuk.", ...],
  "incidents": [
    {
      "title": "Gem shop fraud near Pettah",
      "scam_type": "gem_scam",
      "scam_type_display": "Gem & Jewelry Scam",
      "risk_level": 3,
      "source_display": "Ada Derana News",
      "credibility_label": "🏛️ Tier 1 Verified News",
      "credibility_score": 0.95,
      "distance_km": 1.2,
      "url": "https://www.google.com/search?...",
      "content_snippet": "...",
      "helpful_votes": 12
    }
  ],
  "source_breakdown": [...]
}
```

#### `GET /api/v1/districts/risk-map`
Returns GeoJSON FeatureCollection — 25 Sri Lanka districts with risk scores:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Polygon", "coordinates": [[...]] },
      "properties": {
        "district": "Colombo",
        "risk_tier": "severe",
        "risk_score_0_1": 0.724,
        "report_count": 847,
        "scam_report_count": 312,
        "confidence": "established",
        "incident_rate_per_100k_visitors": 7.43,
        "top_scam_types": [...]
      }
    }
  ]
}
```

#### `GET /api/v1/safety/location-search?q=Kandy`
Searches DB by location name, returns structured safety summary with up to 10 de-duplicated incidents.

#### `GET /api/v1/analytics/dashboard`
Live research analytics: yearly trends by district and scam type, demographic breakdown, source credibility table, cross-district pattern detection.

---

## 8. CORE INTELLIGENCE ENGINE

### 8.1 Safety Intelligence Engine (`app/core/safety_intelligence.py`)

The **PhD-level differentiator**. Computes safety for ANY GPS point using IDW spatial interpolation.

**Algorithm:**

```
For each report within radius_km:
    spatial_weight  = 1 / distance_km²        (IDW: closer = more influence)
    source_weight   = report.source_weight     (credibility tier)
    temporal_weight = e^(-λ × days_ago)        (λ = log(2)/180, half-life 180 days)
    combined        = spatial_weight × source_weight × temporal_weight

composite_score = (
    0.30 × scam_ratio        +   (weighted scam reports / all reports)
    0.25 × severity_index    +   (weighted risk level 1–3 → 0–1)
    0.20 × diversity_penalty +   (unique scam types / 5, capped at 1.0)
    0.15 × credibility_factor+   (Tier 1 source count / 3, capped at 1.0)
    0.10 × recency_factor        (scams in last 90 days / 5, capped at 1.0)
)
```

**Verdict Thresholds:**
- `composite ≥ 0.60` → **HIGH RISK** (red) — requires ≥ 3 reports
- `composite ≥ 0.35` → **MODERATE RISK** (orange)
- `composite ≥ 0.15` → **LOW RISK** (yellow)
- `composite < 0.15` → **SAFE** (green)

**Confidence Levels:**
- `< 3 reports` → "Low (Preliminary Data)"
- `3–9 reports` → "Medium"
- `≥ 10 reports` → "High"

### 8.2 District Risk Engine (`app/core/district_engine.py`)

Aggregates reports to the **administrative district level** using Shapely polygon containment:

**Why district-level vs. grid cells?**
The old grid-cell approach (0.02° cells) had N=1–3 reports per cell, causing scam_ratio ≥ 0.33–1.0 everywhere ("everything is red"). Districts raise N to dozens–hundreds, making the ratio statistically meaningful.

**Key innovations:**
1. **Wilson score lower bound** — prevents a single report from inflating scam ratio (n=1 → 0.21, not 1.0)
2. **Bayesian shrinkage** — pulls small-N districts toward global prior (0.30), preventing outlier gaming
3. **Quantile-relative tiers** — "High risk" means top quartile of TODAY's data, not a fixed threshold
4. **Exposure normalization** — incident rate per 100,000 SLTDA visitors (using Jan–Oct 2024 telecom data)
5. **`insufficient_data` tier** — visually distinct from "low risk" — avoids misleading users about uncovered districts

**Scoring formula:**
```python
severity  = weighted_incidents / scam_count        # severity-weighted, 0–1
scam_ratio = weighted_incidents / weighted_evidence # w/ temporal decay
base_risk  = 0.70 × severity + 0.30 × scam_ratio

# Quantile tiers (data-relative, computed fresh per request):
if base_risk <= q25: tier = "low"
elif base_risk <= q50: tier = "moderate"
elif base_risk <= q75: tier = "high"
else: tier = "severe"
```

### 8.3 Non-Tourism Noise Filter

Applied at every query — reports matching these patterns are excluded from scoring:
- Electoral/political news (ballot paper, elections, parliament, cabinet)
- Migrant labor stories (housemaid, SLBFE, foreign employment)
- Domestic crime unrelated to tourists (drug trafficking, murder charge, underworld)
- Legal proceedings (remanded, magistrate court, bail application)
- Military/police internal affairs (army lieutenant, navy officer)
- Animal welfare stories (elephant bath, captive elephant)
- Weather/disaster management (sluice gates, DMC, meteorology)

**Tourism override:** If any noise-flagged article also contains "tourist", "traveler", "tuk tuk", "gem scam" → it is NOT excluded (genuinely relevant).

---

## 9. FRONTEND — PAGE 1: DISTRICT SAFETY MAP

### 9.1 Technology Stack

| Library | Version | Role |
|---|---|---|
| React | 19.2.8 | UI framework |
| Vite | 4.4.5 | Dev server + bundler |
| Recharts | 3.10.1 | Charts (analytics page) |
| Leaflet | 1.9.4 | Interactive map layer |
| leaflet.heat | 0.2.0 | Heatmap tile layer |

### 9.2 Page 1 Components (src/SafeTravelLK_Page1.jsx, 2153 lines)

The main dashboard. Displays a custom SVG bubble map of all 25 Sri Lanka districts.

#### Screen 1 — Onboarding

Collects traveler profile before showing the map. Fields: Name, Traveler Type (7 options).
Traveler types: Solo Female, Solo Male, Couple, Family, Group Tour, Backpacker, Senior.
Each type has a riskMult multiplier and concerns array (scam types surfaced first).

#### Screen 2 — District Risk Map

- SVG map of Sri Lanka with 25 district bubble markers colored by risk tier
- Color scheme: insufficient_data=dark grey | low=dark green | moderate=amber | high=orange | severe=red
- Bubble radius proportional to tourist footfall (SLTDA data)
- Hover tooltip shows district name + report count + risk grade
- Click opens district detail panel
- Uber-style search bar with autocomplete (25 districts + 36 cities)
- Stats bar shows tier distribution + total source count

#### District Detail Panel — Tab 1: Overview

- Risk grade badge (A/B/C/D or N/A), composite score (0-100)
- Confidence level (established / preliminary / insufficient data)
- Report count, scam count, exposure-normalized rate (incidents per 100k visitors)
- Top scam types (colored pills), peak complaint months
- SLTDA footfall figure
- Cities in the district with individual risk scores
- Location-type risk breakdown (beach, historic site, etc.)
- AI Safety Briefing button (triggers Gemini API call)

#### District Detail Panel — Tab 2: Incidents

- Live incident feed: merges seed incidents + live DB reports
- Each card: title, scam type emoji, risk level dots, source tier badge, distance/date,
  helpful votes, source link (direct URL or Google Search fallback),
  YouTube embed if source is YouTube, full review modal on click
- Filter bar: All / Active Scams / Verified News Only / Traveler Reviews
- Sort: by credibility (default) / nearest / highest risk

#### District Detail Panel — Tab 3: AI Briefing

- Calls POST /api/v1/advisor/chat with structured district + traveler profile prompt
- Returns 3-sentence safety briefing tailored to the traveler profile

### 9.3 Frontend Scoring Engine (Local Computation)

`
DECAY_LAMBDA = log(2) / 180        (half-life 180 days)
BAYESIAN_ALPHA = 0.05              (shrinkage strength)
GLOBAL_PRIOR = 0.30                (conservative mean)

Per-incident weight:
  w = decay(days_ago) x min(source_weight + helpful_vote_bonus, 0.97)

District score:
  adjustedScamRatio = wilsonLower(scamN, n)
  severity = weightedSeveritySum / max(scamN, 1)
  baseRisk = 0.70 x severity + 0.30 x adjustedScamRatio
  shrunkScore = (n x baseRisk + alpha x prior) / (n + alpha)

Tier assignment (quantile-relative across all districts):
  q25, q50, q75 = computeQuantiles(allScores)
  tier: <=q25=low | <=q50=moderate | <=q75=high | else=severe
`

### 9.4 Source Credibility Weights (Frontend Constants)

| Source | Weight | Tier |
|---|---|---|
| UK FCDO / US State Dept / Australia DFAT | 1.00 | Gov |
| SLTDA Official / Tourist Police | 0.97 | Gov |
| Ada Derana | 0.88 | News |
| Newsfirst | 0.86 | News |
| Daily Mirror / Sunday Times | 0.85 | News |
| YouTube | 0.72 | Video |
| WikiVoyage | 0.70 | Wiki |
| TripAdvisor Forum | 0.68 | Forum |
| Google News | 0.65 | Aggregator |
| TripAdvisor / Google Maps | 0.60-0.62 | Review |
| Reddit | 0.42 | UGC |

### 9.5 SLTDA Footfall Data (Jan-Oct 2024)

| District | Visitors |
|---|---|
| Colombo | 4,193,342 |
| Galle | 2,671,580 |
| Gampaha | 2,100,780 |
| Kandy | 1,722,666 |
| Matale | 1,249,150 |
| Kalutara | 1,181,326 |
| Matara | 1,170,772 |
| Badulla | 818,133 |
| Nuwara Eliya | 752,301 |
| Anuradhapura | 735,481 |

### 9.6 City Risk Profiles (36 Cities from pattern_insights.json)

Highest risk: Colombo (0.38), Sigiriya (0.31), Kandy (0.32), Pinnawala (0.35)
Lowest risk: Embilipitiya (0.04), Deniyaya (0.05), Ampara (0.06)

Each city profile includes: total_reviews, negative_reviews, avg_rating,
scam_mentions, peak_complaint_months, top_location_types, risk_score.

---

## 10. FRONTEND — PAGE 2: RESEARCH ANALYTICS DASHBOARD

### 10.1 File: src/SafeTravelLK_Analytics.jsx (657 lines)

Dark-mode research intelligence dashboard. Fetches from GET /api/v1/analytics/dashboard.

Color palette: Background #0A0F1E (deep navy) | Accent #22D3EE (cyan) | Danger #EF4444 | Safe #10B981

### 10.2 Four Analysis Panels

**Panel 01 — Temporal Trend Analysis**
- Line chart: report volume over years, by district (toggle to by scam type)
- Trend direction badges per district: Rising / Falling / Stable
  (comparing last 2 years vs prior 2 years; rising = +30%, falling = -30%)
- District summary cards with latest report count + trend badge

**Panel 02 — Demographic Targeting Classifier**
- Radar chart: estimated risk by 6 demographic profiles
- Pie chart: current live demographic_target field distribution from DB
- Classifier gap warning: current DB has 2 demographic classes; proposes 6-class taxonomy
- 6 expandable demographic cards with risk score, top scam, hot districts, evidence basis:
  Solo Female (risk 71%), Backpacker (63%), Vlogger (58%), Couple (45%), Senior (42%), Family (38%)

**Panel 03 — Source Credibility Wiring**
- Two score cards: Colombo unweighted risk (0.697) vs weighted (0.623) — delta shows effect of weighting
- Toggle bar chart: Current Pipeline vs With Source Weighting — risk contribution per source
- Live source weight tier table: 10 sources with tier, weight, live DB report count

**Panel 04 — Cross-District Pattern Linking**
- Same scam type appearing in multiple districts in same calendar week (ISO week grouping)
- Left panel: weeks listed with urgency badge (CRITICAL >= 10 reports + 4 districts / ELEVATED >= 5 / WATCH)
- Right panel: clicking a week shows all detected patterns with district bubbles + interpretation text
- Multi-district synchrony: flagged as cascade pattern (systemic/media-driven event)
- Two-district co-occurrence: flagged as route-based scam or shared media coverage

---

## 11. AI CHAT ADVISOR

### 11.1 Endpoint: POST /api/v1/advisor/chat

Model: Google Gemini 1.5-flash (free tier)
Fallback: Rule-based keyword response system

Request body:
  { message, history: [{role, content}], profile, city, month }

### 11.2 DB Context Injection (every request)

Before each Gemini call, live DB data is prepended to the user message:
- LIVE THREAT DATA: top scam types for the city with counts and avg risk
- RECENT VERIFIED INCIDENTS: last 6 high-risk reports with title and source
- CITY STATS: total reports + negative count + negative rate %
- PROFILE RISKS: hardcoded risk summary per traveler profile
- SEASONAL NOTE: monsoon/dry season context based on month parameter

### 11.3 Fallback Knowledge Base

Keyword-matched rule responses when Gemini unavailable:
- gem -> Gem Scam explanation + avoidance tips
- tuk -> Tuk-tuk scam tactics + PickMe app recommendation
- safe -> City-by-city safety overview (Colombo / Kandy / Galle)
- hello -> Welcome message with capability overview
- Generic -> DB context summary + redirect

---

## 12. ADMIN & MAINTENANCE TOOLS

### 12.1 Data Quality Scripts (backend root)

| Script | Purpose |
|---|---|
| clean_and_relabel_db.py | Re-run NLP on all DB records, fix misclassifications |
| purge_duplicate_reports.py | Fingerprint-based deduplication |
| purge_non_safety_reports.py | Remove records with no safety relevance |
| purge_non_news.py | Remove non-news records from news source slots |
| strict_purge.py | Hard-delete records failing strict relevance filter |
| fix_data_quality.py | Fix NULL coordinates, normalize source names |
| coverage_gap_analysis.py | Identify districts with <5 reports |
| fill_coverage_gaps.py | Run targeted scrapers for under-covered districts |
| export_clean_dataset.py | Export cleaned, labeled dataset as CSV |
| export_pipeline_dataset.py | Full pipeline export (DB + CSV merged) |
| recover_old_data.py | Recover records from backup DB files |
| show_model_accuracy.py | Print cross-validation accuracy + confusion matrix |

### 12.2 Admin API Endpoints

- GET /api/v1/admin/stats — DB record counts, source distribution, risk breakdown
- POST /api/v1/admin/purge-duplicates — trigger deduplication
- POST /api/v1/admin/recluster — trigger DBSCAN re-clustering of risk zones
- GET /api/v1/admin/model-status — model training status + accuracy

---

## 13. SOURCE CREDIBILITY SYSTEM

### 13.1 Credibility Tier Hierarchy

Tier 0 — Government Advisories (weight 1.00)
  UK FCDO | US State Dept | Australia Smartraveller | SLTDA Official | Tourist Police LK

Tier 1 — Verified Sri Lankan News (weight 0.80-0.95)
  Ada Derana | Newsfirst | Daily Mirror | Sunday Times | The Morning
  The Island | Ceylon Today | Hiru News | Newswire | Colombo Gazette

Tier 2 — Video & Aggregated (weight 0.65-0.72)
  YouTube Travel Vlogs | Google News | WikiVoyage

Tier 3 — Review Platforms (weight 0.60-0.68)
  TripAdvisor | Google Maps Reviews | TripAdvisor Forum

Tier 4 — User-Generated Content (weight 0.35-0.42)
  Reddit | Travel Forums | Quora

### 13.2 Dynamic Source URL Resolution

For reports without a direct URL, the system builds a targeted Google Search:
  site:adaderana.lk headline  → Google I'm Feeling Lucky link
  General fallback: Google search for headline + location + Sri Lanka

This ensures every incident card has a clickable, verifiable source link.

---

## 14. SCORING METHODOLOGY

### 14.1 Composite Safety Score Formula (IDW Engine)

  Component 1 (30%): Scam Ratio
    = SUM(combined_weight x is_scam) / SUM(combined_weight)

  Component 2 (25%): Severity Index
    = SUM(combined_weight x risk_level/3) / SUM(combined_weight)

  Component 3 (20%): Scam Diversity Penalty
    = min(unique_scam_types / 5, 1.0)

  Component 4 (15%): Source Credibility Factor
    = min(tier1_confirmed_scams / 3, 1.0)

  Component 5 (10%): Recency Factor
    = min(scams_in_last_90_days / 5, 1.0)

  Final = 0.30xC1 + 0.25xC2 + 0.20xC3 + 0.15xC4 + 0.10xC5
  Where: combined_weight = spatial_weight x source_weight x temporal_weight

### 14.2 Temporal Decay (Half-Life 180 Days)

  temporal_weight = e^(-lambda x days_ago)
  lambda = log(2) / 180 = 0.00385

  Today          -> weight 1.000
  6 months ago   -> weight 0.500
  1 year ago     -> weight 0.250
  2 years ago    -> weight 0.063

### 14.3 Wilson Score Lower Bound (Anti-Gaming)

  wilsonLower(successes=1, n=1) = 0.21   (not 1.0 — prevents single-report gaming)
  wilsonLower(successes=8, n=10) = 0.58  (not 0.80)
  wilsonLower(successes=50, n=100) = 0.41

### 14.4 Bayesian Shrinkage (Small-N Correction)

  shrunkScore = (N x rawScore + alpha x globalPrior) / (N + alpha)
  alpha = 0.05 | globalPrior = 0.30

  N=3, rawScore=0.80 -> shrunkScore = 0.766  (significantly pulled toward mean)
  N=100, rawScore=0.80 -> shrunkScore = 0.799 (barely affected)

### 14.5 Exposure Normalisation

  incident_rate = (weighted_incidents / footfall) x 100,000

  Allows fair cross-district comparison: a district with 1,000 incidents
  but 4M visitors may be safer than one with 50 incidents and 80,000 visitors.

### 14.6 Quantile-Relative Tier Assignment

  Tiers are computed fresh on every request against the CURRENT distribution:
  q25 = 25th percentile of all scored district scores
  q50 = 50th percentile
  q75 = 75th percentile

  score <= q25 -> LOW
  score <= q50 -> MODERATE
  score <= q75 -> HIGH
  score > q75  -> SEVERE

  HIGH risk always means top quartile of TODAY's evidence base —
  not a fixed absolute threshold. This is self-calibrating as more data arrives.

---

## APPENDIX A: ENVIRONMENT CONFIGURATION

`
# backend/.env
PROJECT_NAME=SafeTravel LK
API_V1_STR=/api/v1
SQLALCHEMY_DATABASE_URI=postgresql://user:pass@localhost/safetravel
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_MAPS_API_KEY=your_google_maps_key
`

## APPENDIX B: RUNNING LOCALLY

`ash
# Backend (from e:\research\backend)
..\.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000

# Frontend (from e:\research\frontend)
npm run dev
# Opens at http://localhost:5173

# API Docs (interactive Swagger UI)
# http://localhost:8000/docs
`

## APPENDIX C: KEY FILE REFERENCE

`
e:\research\
├── backend/
│   ├── app/main.py                      FastAPI entry + scheduler
│   ├── app/api/endpoints/
│   │   ├── safety.py                    IDW assess + heatmap endpoints
│   │   ├── districts.py                 GeoJSON district risk-map
│   │   ├── chat.py                      Gemini AI advisor
│   │   ├── analytics.py                 Research analytics dashboard data
│   │   └── admin.py                     DB stats + purge tools
│   ├── app/core/
│   │   ├── safety_intelligence.py       Primary IDW scoring engine
│   │   └── district_engine.py           District choropleth + Bayesian scoring
│   ├── app/ml/
│   │   ├── nlp_pipeline.py              2-tier NLP classifier
│   │   ├── source_weights.py            Credibility tier definitions
│   │   └── models/                      Trained .joblib + pattern_insights.json
│   ├── app/db/
│   │   ├── models.py                    SQLAlchemy ORM (Report, RiskZone)
│   │   └── session.py                   DB engine + PostgreSQL/SQLite fallback
│   ├── data_pipeline/
│   │   ├── scrape_sl_news_v3.py         Main news scraper (80+ queries)
│   │   ├── continuous_runner.py         Always-on high-frequency scraper
│   │   ├── strict_filter.py             Tourism relevance gate
│   │   └── collectors/                  Reddit, YouTube, Google Maps, forums
│   ├── training/
│   │   ├── train_enhanced_model.py      GB+RF ensemble training
│   │   └── train_classifier.py          TF-IDF+RF scam classifier
│   └── safety_heatmap.db               Live SQLite database
├── frontend/
│   └── src/
│       ├── SafeTravelLK_Page1.jsx       District map + incident panel
│       └── SafeTravelLK_Analytics.jsx  Research analytics dashboard
└── dataset/
    ├── Derana_News.csv                  509 MB — Ada Derana archive
    ├── Destination Reviews (final).csv  3.7 MB — 16,156 TripAdvisor reviews
    ├── Reviews.csv                      9.2 MB — Combined review dataset
    └── SriLanka_Weather_Dataset.csv     23 MB  — Historical weather
`

---

*Document generated: 2026-08-12 | IT22629180 | SafeTravel LK Safety Intelligence System*
