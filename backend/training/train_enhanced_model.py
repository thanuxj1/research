"""
Enhanced Training Script — trains on both Reviews.csv and safety_heatmap.db
IT22629180

Builds:
  - Gradient Boosting + Random Forest ensemble for risk prediction
  - Pattern insights JSON for the advisor API
  - Seasonal risk calendar per city
  - Location-type risk table

Run from backend/ directory:
    python training/train_enhanced_model.py
"""
import os
import sys
import json
import sqlite3
import numpy as np

# Add backend root to path so app imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ml.review_analyzer import ReviewAnalyzer, CITY_COORDS, MONTH_RISK_BOOST

try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier, VotingClassifier
    from sklearn.preprocessing import LabelEncoder, StandardScaler
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
    from sklearn.pipeline import Pipeline
    import joblib
    _SKLEARN_OK = True
except ImportError:
    _SKLEARN_OK = False
    print("[ERROR] scikit-learn not installed. Run: pip install scikit-learn joblib")
    sys.exit(1)

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
BACKEND_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH      = os.path.join(BACKEND_DIR, "safety_heatmap.db")
CSV_PATH     = os.path.join(BACKEND_DIR, "..", "Reviews.csv")
MODEL_DIR    = os.path.join(BACKEND_DIR, "app", "ml", "models")
MODEL_PATH   = os.path.join(MODEL_DIR, "enhanced_predictor.joblib")
META_PATH    = os.path.join(MODEL_DIR, "enhanced_meta.joblib")
INSIGHTS_PATH = os.path.join(MODEL_DIR, "pattern_insights.json")


def load_db_reports() -> pd.DataFrame:
    """Load geolocated safety incident reports from SQLite DB."""
    print("\n[1/5] Loading safety incident DB...")
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT id, source, latitude, longitude, sentiment_score,
               is_scam, scam_type, risk_level, location_name
        FROM reports
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """,
        conn,
    )
    conn.close()
    print(f"      -> {len(df)} geolocated reports loaded.")
    return df


def load_review_features(analyzer: ReviewAnalyzer) -> pd.DataFrame:
    """Build feature rows from Reviews.csv via the ReviewAnalyzer."""
    print("\n[2/5] Extracting review features...")
    rows = analyzer.build_training_rows()
    df = pd.DataFrame(rows)
    df = df.dropna(subset=["lat", "lon"])
    print(f"      -> {len(df)} review rows with coordinates.")
    return df


def build_combined_features(db_df: pd.DataFrame, review_df: pd.DataFrame) -> tuple:
    """
    Merge DB and review features into one feature matrix.
    Features:
      lat_bin, lon_bin, month, loc_type_risk, month_boost,
      is_scam_flag, neg_score, is_experienced, source_encoded
    """
    print("\n[3/5] Building combined feature matrix...")

    scam_enc    = LabelEncoder()
    source_enc  = LabelEncoder()
    loc_type_enc = LabelEncoder()

    # ── DB Records ────────────────────────────────────────────────────────────
    db_rows = []
    scam_types_db = (db_df["scam_type"].fillna("none")).tolist()
    sources_db    = (db_df["source"].fillna("unknown")).tolist()

    for i, row in db_df.iterrows():
        db_rows.append({
            "lat_bin":       round(float(row["latitude"]), 2),
            "lon_bin":       round(float(row["longitude"]), 2),
            "month":         6,         # DB records have no month — use mid-year default
            "loc_type_risk": 0.40,      # DB records have no location type
            "month_boost":   0.05,
            "is_scam_flag":  int(row.get("is_scam", 0) or 0),
            "neg_score":     0,
            "is_experienced": 0,
            "scam_type_raw": scam_types_db[list(db_df.index).index(i)],
            "source_raw":    sources_db[list(db_df.index).index(i)],
            "risk_level":    int(row.get("risk_level", 1) or 1),
            "data_source":   "db",
        })

    # ── Review Records ────────────────────────────────────────────────────────
    rev_rows = []
    for _, row in review_df.iterrows():
        rev_rows.append({
            "lat_bin":        round(float(row["lat"]), 2),
            "lon_bin":        round(float(row["lon"]), 2),
            "month":          int(row.get("month", 6)),
            "loc_type_risk":  float(row.get("loc_risk", 0.40)),
            "month_boost":    float(row.get("month_boost", 0.05)),
            "is_scam_flag":   int(row.get("is_scam", 0)),
            "neg_score":      int(min(row.get("neg_score", 0), 5)),
            "is_experienced": int(row.get("is_experienced", 0)),
            "scam_type_raw":  "none",
            "source_raw":     "reviews_csv",
            "risk_level":     int(row.get("risk_level", 1)),
            "data_source":    "csv",
        })

    all_rows = db_rows + rev_rows
    all_df = pd.DataFrame(all_rows)

    # Encode categoricals
    all_scam   = all_df["scam_type_raw"].tolist()
    all_source = all_df["source_raw"].tolist()
    scam_enc.fit(list(set(all_scam)))
    source_enc.fit(list(set(all_source)))

    X = np.column_stack([
        all_df["lat_bin"].values,
        all_df["lon_bin"].values,
        all_df["month"].values,
        all_df["loc_type_risk"].values,
        all_df["month_boost"].values,
        all_df["is_scam_flag"].values,
        all_df["neg_score"].values,
        all_df["is_experienced"].values,
        scam_enc.transform(all_scam),
        source_enc.transform(all_source),
    ])
    y = all_df["risk_level"].values

    # Clamp labels to 1-3
    y = np.clip(y, 1, 3)

    print(f"      -> Combined: {len(X)} samples | Labels: {dict(zip(*np.unique(y, return_counts=True)))}")
    return X, y, scam_enc, source_enc


def train_ensemble(X, y) -> dict:
    """Train GradientBoosting + RandomForest voting ensemble."""
    print("\n[4/5] Training ensemble model...")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    gb = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.08,
        min_samples_leaf=3,
        random_state=42,
    )
    rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_split=3,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    ensemble = VotingClassifier(
        estimators=[("gb", gb), ("rf", rf)],
        voting="soft",
        weights=[0.55, 0.45],
    )
    ensemble.fit(X_train, y_train)

    # Evaluate
    y_pred = ensemble.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\n  Test Accuracy: {acc:.1%}")
    print("\n--- Classification Report ---")
    print(classification_report(y_test, y_pred, target_names=["Low", "Moderate", "High"]))

    cm = confusion_matrix(y_test, y_pred)
    print("--- Confusion Matrix ---")
    for row in cm:
        print("  " + "  ".join(f"{v:4}" for v in row))

    # Cross-val
    try:
        cv = cross_val_score(ensemble, X, y, cv=5, scoring="accuracy")
        print(f"\n  CV Accuracy: {cv.mean():.1%} ± {cv.std():.1%}")
        cv_acc = float(cv.mean())
    except Exception:
        cv_acc = acc

    feat_names = [
        "lat_bin", "lon_bin", "month", "loc_type_risk", "month_boost",
        "is_scam_flag", "neg_score", "is_experienced",
        "scam_type_enc", "source_enc",
    ]
    # Feature importance from RF (GBM has different API)
    rf_fitted = ensemble.estimators_[1]
    feature_importance = {
        n: round(float(v), 4)
        for n, v in zip(feat_names, rf_fitted.feature_importances_)
    }

    return {
        "model":              ensemble,
        "accuracy":           round(cv_acc, 4),
        "test_accuracy":      round(acc, 4),
        "training_size":      len(X_train),
        "feature_importance": feature_importance,
    }


def save_artifacts(result: dict, scam_enc, source_enc, analyzer: ReviewAnalyzer):
    """Save trained model, meta, and pattern insights JSON."""
    print("\n[5/5] Saving artifacts...")
    os.makedirs(MODEL_DIR, exist_ok=True)

    joblib.dump(result["model"], MODEL_PATH)
    joblib.dump({
        "scam_encoder":       scam_enc,
        "source_encoder":     source_enc,
        "accuracy":           result["accuracy"],
        "test_accuracy":      result["test_accuracy"],
        "training_size":      result["training_size"],
        "feature_importance": result["feature_importance"],
    }, META_PATH)

    # Pattern insights JSON
    insights = {
        "patterns":          analyzer.get_top_patterns(50),
        "seasonal_risk":     analyzer.seasonal_risk,
        "location_type_risk": analyzer.location_type_risk,
        "city_profiles":     analyzer.city_scam_profile,
    }
    with open(INSIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2, ensure_ascii=False)

    model_kb = os.path.getsize(MODEL_PATH) / 1024
    insights_kb = os.path.getsize(INSIGHTS_PATH) / 1024

    print(f"  [OK] Model saved:    {MODEL_PATH} ({model_kb:.0f} KB)")
    print(f"  [OK] Meta saved:     {META_PATH}")
    print(f"  [OK] Insights saved: {INSIGHTS_PATH} ({insights_kb:.0f} KB)")
    print(f"\n  Accuracy: {result['accuracy']:.1%} | Training size: {result['training_size']} samples")
    print(f"\n  Top features:")
    for name, imp in sorted(result["feature_importance"].items(), key=lambda x: -x[1])[:5]:
        print(f"    {name:25s}: {imp:.4f}")


def main():
    print("=" * 60)
    print("  Enhanced ML Model Training — SafeTravel LK")
    print("  IT22629180")
    print("=" * 60)

    # 1. Load Reviews CSV
    analyzer = ReviewAnalyzer(CSV_PATH)
    if not analyzer.load():
        print("[WARN] Reviews.csv not found — training on DB only.")
    else:
        summary = analyzer.analyze()
        print(f"\n  Reviews:  {summary.get('total_reviews', 0)}")
        print(f"  Cities:   {summary.get('cities_analyzed', 0)}")
        print(f"  Patterns: {summary.get('pattern_count', 0)}")

    # 2. Load DB reports
    db_df = load_db_reports()

    # 3. Load review features (only if CSV was loaded)
    review_df = load_review_features(analyzer) if analyzer._loaded else pd.DataFrame()

    # 4. Build features
    X, y, scam_enc, source_enc = build_combined_features(db_df, review_df)

    if len(X) < 20:
        print("[ERROR] Too few training samples. Ensure DB has records.")
        sys.exit(1)

    # 5. Train
    result = train_ensemble(X, y)

    # 6. Save
    save_artifacts(result, scam_enc, source_enc, analyzer)

    print("\n" + "=" * 60)
    print("  Training complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
