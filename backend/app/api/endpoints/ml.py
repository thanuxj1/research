"""
ML Prediction API Endpoint
IT22629180

Exposes:
  POST /ml/predict    — predict risk for a lat/lon + traveller profile
  GET  /ml/model-stats — model accuracy, feature importances, training size
  GET  /ml/safe-zones  — (alias) delegated to safety router
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy import func as sqlfunc

from app.db.session import get_db
from app.db.models import Report
from app.ml.pattern_predictor import (
    get_predictor, SAFETY_TIPS, PROFILE_RISK_MAP, SL_LOCATIONS_FOR_SAFE_ZONES
)
from app.ml.source_weights import get_all_weights_table, get_source_weight

router = APIRouter()


# ── Request/Response schemas ──────────────────────────────────────────────────

class PredictRequest(BaseModel):
    lat:     float = Field(..., ge=5.5, le=10.0,  description="Latitude (Sri Lanka bounds)")
    lon:     float = Field(..., ge=79.0, le=82.5, description="Longitude (Sri Lanka bounds)")
    profile: Optional[str] = Field("General", description="Traveller profile")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/predict")
def predict_risk(req: PredictRequest, db: Session = Depends(get_db)):
    """
    Predict risk level and expected threats for a given location + profile.
    The model is trained on all geolocated reports in the DB.
    """
    predictor = get_predictor()

    # Lazily train if not yet trained (first call after cold start)
    if not predictor._trained:
        reports = db.query(Report).filter(
            Report.latitude.isnot(None),
            Report.longitude.isnot(None),
        ).all()
        predictor.train(reports)

    result = predictor.predict(req.lat, req.lon, req.profile or "General")

    # Attach personalised tips for the profile
    result["safety_tips"] = SAFETY_TIPS.get(req.profile or "General", SAFETY_TIPS["General"])

    return result


@router.get("/model-stats")
def model_stats(db: Session = Depends(get_db)):
    """Returns ML model performance metrics and training info."""
    predictor = get_predictor()
    if not predictor._trained:
        # Trigger training
        reports = db.query(Report).filter(
            Report.latitude.isnot(None),
            Report.longitude.isnot(None),
        ).all()
        predictor.train(reports)

    stats = predictor.get_model_stats()
    stats["total_db_records"] = db.query(Report).count()
    return stats


@router.post("/train")
def retrain_model(db: Session = Depends(get_db)):
    """Force-retrain the model with the latest data."""
    predictor = get_predictor()
    reports = db.query(Report).filter(
        Report.latitude.isnot(None),
        Report.longitude.isnot(None),
    ).all()
    metrics = predictor.train(reports)
    return {"message": "Model retrained successfully.", **metrics}


@router.get("/source-weights")
def source_weights():
    """
    Returns the full source credibility weight table.
    Shows every data source and its assigned weight (0.0 – 1.0).
    Higher weight = more influence on the risk score calculation.
    Useful for the admin dashboard and academic paper documentation.
    """
    table = get_all_weights_table()
    return {
        "description": (
            "Source credibility weights used in risk score calculation. "
            "Records from higher-weight sources contribute proportionally more "
            "to location risk scores than lower-weight sources."
        ),
        "tier_guide": {
            "0.85 – 0.97": "Tier 1 — Sri Lanka certified domestic news (editorial oversight)",
            "0.65 – 0.84": "Tier 2 — Verified journalism / licensed open sources",
            "0.55 – 0.64": "Tier 2c — Semi-verified platforms (Google News, Maps, TripAdvisor)",
            "0.25 – 0.49": "Tier 3 — Unverified user-generated content",
        },
        "sources": table,
    }


@router.get("/source-weight-stats")
def source_weight_stats(db: Session = Depends(get_db)):
    """
    Returns the distribution of source weights currently in the database.
    Shows how many records come from each trust tier.
    """
    records = db.query(Report.source, Report.source_weight).all()
    tier_counts = {"tier_1_certified": 0, "tier_2_journalism": 0,
                   "tier_2c_semi": 0, "tier_3_ugc": 0, "unknown": 0}
    source_summary: dict = {}

    for source, weight in records:
        w = weight or 0.35
        if w >= 0.85:
            tier_counts["tier_1_certified"] += 1
        elif w >= 0.65:
            tier_counts["tier_2_journalism"] += 1
        elif w >= 0.55:
            tier_counts["tier_2c_semi"] += 1
        elif w > 0:
            tier_counts["tier_3_ugc"] += 1
        else:
            tier_counts["unknown"] += 1

        src = source or "unknown"
        if src not in source_summary:
            source_summary[src] = {"count": 0, "weight": round(w, 3)}
        source_summary[src]["count"] += 1

    total = len(records)
    return {
        "total_records": total,
        "tier_distribution": tier_counts,
        "tier_percentages": {
            k: round(v / total * 100, 1) if total else 0
            for k, v in tier_counts.items()
        },
        "by_source": dict(sorted(
            source_summary.items(),
            key=lambda x: x[1]["weight"],
            reverse=True
        )),
    }
