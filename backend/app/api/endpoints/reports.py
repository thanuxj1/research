"""
Reports API endpoint — tourist incident submission and retrieval.
IT22629180
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.db.models import Report
from app.schemas.report import ReportCreate, ReportResponse
from app.ml.nlp_pipeline import NLPPipeline
from data_pipeline.strict_filter import passes_strict_filter

router = APIRouter()
nlp = NLPPipeline()


@router.post("/", response_model=ReportResponse, status_code=201)
def create_report(report_in: ReportCreate, db: Session = Depends(get_db)):
    """Submit a tourist incident report. NLP analysis is run automatically."""
    text = f"{report_in.title or ''} {report_in.content}".strip()
    if not passes_strict_filter(report_in.title or "", report_in.content):
        raise HTTPException(
            status_code=422,
            detail=(
                "Report rejected: it must describe a negative experience or "
                "safety incident faced by tourists while travelling in Sri Lanka."
            ),
        )

    analysis = nlp.analyze_text(text)

    # Use GPS from the user if provided; otherwise use NLP-extracted location
    lat = report_in.latitude  if report_in.latitude  is not None else analysis["latitude"]
    lon = report_in.longitude if report_in.longitude is not None else analysis["longitude"]
    loc = report_in.location_name or analysis["location_name"]

    db_report = Report(
        source            = report_in.source,
        title             = report_in.title,
        content           = report_in.content,
        url               = None,
        latitude          = lat,
        longitude         = lon,
        location_name     = loc,
        demographic_target= report_in.demographic_target,
        sentiment_score   = analysis["sentiment_score"],
        is_scam           = analysis["is_scam"],
        scam_type         = report_in.incident_type or analysis["scam_type"],
        risk_level        = analysis["risk_level"],
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report


@router.get("/", response_model=List[ReportResponse])
def list_reports(
    source:    Optional[str] = None,
    is_scam:   Optional[bool] = None,
    scam_type: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """List reports with optional filters."""
    q = db.query(Report)
    if source:
        q = q.filter(Report.source == source)
    if is_scam is not None:
        q = q.filter(Report.is_scam == is_scam)
    if scam_type:
        q = q.filter(Report.scam_type == scam_type)
    return q.order_by(Report.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: int, db: Session = Depends(get_db)):
    r = db.query(Report).filter(Report.id == report_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    return r


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: int, db: Session = Depends(get_db)):
    r = db.query(Report).filter(Report.id == report_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(r)
    db.commit()
