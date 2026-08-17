"""
District Choropleth API.
IT22629180

GET /api/v1/districts/risk-map
    -> GeoJSON FeatureCollection, one Feature per district polygon, with a full
       scoring breakdown in `properties`. This is the ONLY endpoint the new
       frontend choropleth layer needs.

GET /api/v1/districts/methodology
    -> machine-readable methodology summary (constants, thresholds, exposure
       data coverage). Useful to render an in-app "How is this calculated?"
       panel, and to answer panel/viva questions with a live artifact instead
       of only a static document.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Report
from app.core.district_engine import (
    get_boundary_index,
    score_all_districts,
    methodology_report,
)
from app.api.endpoints.safety import build_source_link, SOURCE_DISPLAY

router = APIRouter()


def _format_recent_report(r) -> dict:
    return {
        "title": (r.title or "").strip()[:160],
        "scam_type": r.scam_type,
        "risk_level": r.risk_level,
        "is_scam": bool(r.is_scam),
        "source_label": SOURCE_DISPLAY.get(r.source or "", r.source or "Unknown"),
        "url": build_source_link(r.url, r.title, r.content, r.location_name, source=r.source),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/risk-map")
def get_district_risk_map(db: Session = Depends(get_db)):
    reports = db.query(Report).filter(
        Report.latitude.isnot(None), Report.longitude.isnot(None)
    ).all()

    scores = score_all_districts(reports)
    idx = get_boundary_index()
    fc = idx.feature_collection_template()

    for feat in fc["features"]:
        name = feat["properties"]["district"]
        s = scores.get(name)
        if not s:
            continue
        feat["properties"].update({
            "report_count": s["report_count"],
            "scam_report_count": s["scam_report_count"],
            "confidence": s["confidence"],
            "risk_tier": s["risk_tier"],
            "risk_score_0_1": s["risk_score_0_1"],
            "severity_component": s["severity_component"],
            "scam_ratio_component": s["scam_ratio_component"],
            "incident_rate_per_100k_presences": s["incident_rate_per_100k_presences"],
            "tiering_method": s.get("tiering_method", "density_only"),
            "exposure_status": s["exposure_status"],
            "exposure_footfall": s.get("exposure_footfall"),
            "exposure_source": s.get("exposure_source"),
            "exposure_period": s.get("exposure_period"),
            "top_scam_types": s["top_scam_types"],
            "breakpoints_used": s["breakpoints_used"],
            "recent_reports": [_format_recent_report(r) for r in s["recent_reports_raw"]],
        })

    return {
        "type": "FeatureCollection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "features": fc["features"],
        "legend": {
            "insufficient_data": {"label": "Insufficient Data", "color": "#6b7280",
                                   "note": f"Fewer than the minimum report threshold — no risk claim is made."},
            "low": {"label": "Low Risk", "color": "#22c55e"},
            "moderate": {"label": "Moderate Risk", "color": "#eab308"},
            "high": {"label": "High Risk", "color": "#f97316"},
            "severe": {"label": "Severe Risk", "color": "#ef4444"},
        },
    }


@router.get("/methodology")
def get_methodology():
    return methodology_report()


@router.get("/{district_name}/reports")
def get_district_reports(district_name: str, db: Session = Depends(get_db)):
    from shapely.geometry import Point
    idx = get_boundary_index()
    d_clean = district_name.strip().lower()
    
    target_entry = None
    for entry in idx._entries:
        if entry["district"].lower() == d_clean:
            target_entry = entry
            break
        for const in entry.get("constituents", []):
            if const.lower() == d_clean:
                target_entry = entry
                break
    
    reports = db.query(Report).filter(Report.latitude.isnot(None), Report.longitude.isnot(None)).all()
    matching = []
    seen_ids = set()

    for r in reports:
        if r.id in seen_ids:
            continue
        pt = Point(r.longitude, r.latitude)
        is_match = False
        if target_entry and (target_entry["prepared"].contains(pt) or target_entry["geom"].touches(pt)):
            is_match = True
        elif r.location_name and d_clean in r.location_name.lower():
            is_match = True
        elif r.title and d_clean in r.title.lower():
            is_match = True

        if is_match:
            seen_ids.add(r.id)
            matching.append(r)

    # Sort by risk level desc, helpful votes desc
    matching.sort(key=lambda r: (-(r.risk_level or 1), -(r.helpful_votes or 0)))

    return {
        "district": district_name,
        "total_reports": len(matching),
        "reports": [
            {
                "id": r.id,
                "title": (r.title or "").strip()[:180],
                "scam_type": r.scam_type,
                "risk_level": r.risk_level,
                "is_scam": bool(r.is_scam),
                "source": r.source,
                "source_label": SOURCE_DISPLAY.get(r.source or "", r.source or "Unknown"),
                "location": r.location_name or district_name,
                "url": build_source_link(r.url, r.title, r.content, r.location_name, source=r.source),
                "content": r.content or "",
                "helpful_votes": getattr(r, "helpful_votes", 0) or 0,
                "date": str(r.created_at.date()) if r.created_at else None,
            }
            for r in matching[:100]
        ]
    }

