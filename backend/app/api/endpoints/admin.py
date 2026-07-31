"""
Admin dashboard API endpoint.
IT22629180
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from collections import Counter
from app.db.session import get_db
from app.db.models import Report, RiskZone

router = APIRouter()


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """High-level dashboard statistics."""
    from app.core.clustering import get_grid_zones

    total_reports  = db.query(func.count(Report.id)).scalar()
    scam_reports   = db.query(func.count(Report.id)).filter(Report.is_scam == True).scalar()
    
    # Calculate high risk zones using the same logic as the map
    # to ensure consistency in reported numbers.
    geo_reports = db.query(Report).filter(Report.latitude.isnot(None), Report.longitude.isnot(None)).all()
    zones = get_grid_zones(geo_reports)
    
    total_zones    = len(zones)
    high_risk_zones = len([z for z in zones if z["risk_score"] >= 0.7])
    
    sources = db.query(Report.source, func.count(Report.id)).group_by(Report.source).all()

    return {
        "total_reports":   total_reports,
        "scam_reports":    scam_reports,
        "total_zones":     total_zones,
        "high_risk_zones": high_risk_zones,
        "sources":         {s: c for s, c in sources},
    }


@router.get("/trends")
def get_trends(days: int = 30, db: Session = Depends(get_db)):
    """Daily incident counts for the past N days (for Chart.js line chart)."""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(
            func.date(Report.created_at).label("day"),
            func.count(Report.id).label("count"),
        )
        .filter(Report.created_at >= cutoff)
        .group_by(func.date(Report.created_at))
        .order_by(func.date(Report.created_at))
        .all()
    )

    return [{"date": str(row.day), "count": row.count} for row in rows]


@router.get("/scam-types")
def get_scam_types(db: Session = Depends(get_db)):
    """Breakdown of reports by scam category (for pie chart)."""
    rows = (
        db.query(Report.scam_type, func.count(Report.id))
        .filter(Report.scam_type.isnot(None))
        .group_by(Report.scam_type)
        .order_by(desc(func.count(Report.id)))
        .all()
    )
    return [{"scam_type": r[0], "count": r[1]} for r in rows]


@router.get("/top-locations")
def get_top_locations(limit: int = 10, db: Session = Depends(get_db)):
    """Top N locations by report count."""
    rows = (
        db.query(Report.location_name, func.count(Report.id).label("count"),
                 func.avg(Report.risk_level).label("avg_risk"))
        .filter(Report.location_name.isnot(None))
        .group_by(Report.location_name)
        .order_by(desc(func.count(Report.id)))
        .limit(limit)
        .all()
    )
    return [
        {"location": r[0], "report_count": r[1], "avg_risk": round(r[2], 2)}
        for r in rows
    ]


@router.get("/patterns")
def get_scam_patterns(min_count: int = 3, db: Session = Depends(get_db)):
    """
    Pattern Recognition: Identify recurring scams at specific locations.
    Returns (location, scam_type) clusters with high report counts.
    """
    rows = (
        db.query(
            Report.location_name,
            Report.scam_type,
            func.count(Report.id).label("count"),
            func.avg(Report.risk_level).label("avg_risk")
        )
        .filter(Report.location_name.isnot(None))
        .filter(Report.scam_type.isnot(None))
        .group_by(Report.location_name, Report.scam_type)
        .having(func.count(Report.id) >= min_count)
        .order_by(desc("count"))
        .all()
    )
    return [
        {
            "location": r[0],
            "scam_type": r[1],
            "count": r[2],
            "avg_risk": round(r[3], 2)
        }
        for r in rows
    ]


@router.get("/reports")
def admin_list_reports(
    page: int = 1,
    per_page: int = 20,
    source: str = None,
    is_scam: bool = None,
    db: Session = Depends(get_db),
):
    """Paginated report list for admin management table."""
    q = db.query(Report).filter(Report.url.ilike("http%"))
    if source:
        q = q.filter(Report.source == source)
    if is_scam is not None:
        q = q.filter(Report.is_scam == is_scam)

    total = q.count()
    items = (
        q.order_by(desc(Report.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    (total + per_page - 1) // per_page,
        "items": [
            {
                "id":         r.id,
                "source":     r.source,
                "title":      r.title,
                "is_scam":    r.is_scam,
                "scam_type":  r.scam_type,
                "risk_level": r.risk_level,
                "location":   r.location_name,
                "url":        r.url,
                "created_at": r.created_at,
            }
            for r in items
        ],
    }
