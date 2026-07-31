"""
Pydantic schemas for reports & heatmap responses.
IT22629180
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ReportCreate(BaseModel):
    """Tourist-submitted incident report"""
    source: str = Field(default="user_app")
    title: Optional[str] = None
    content: str = Field(..., min_length=10, description="Description of the incident")
    incident_type: Optional[str] = None   # gem_scam, harassment, etc.
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    demographic_target: Optional[str] = None  # Solo Female, Family, etc.


class ReportResponse(BaseModel):
    id: int
    source: str
    title: Optional[str]
    content: str
    url: Optional[str]
    sentiment_score: Optional[float]
    is_scam: bool
    scam_type: Optional[str]
    risk_level: int
    latitude: Optional[float]
    longitude: Optional[float]
    location_name: Optional[str]
    demographic_target: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SafetyHeatmapResponse(BaseModel):
    cluster_id: int
    risk_score: float
    center_lat: Optional[float]
    center_lon: Optional[float]
    primary_scam_type: Optional[str]
    report_count: int
    scam_count: Optional[int] = 0
    location_name: Optional[str] = None
    scam_types: Optional[dict] = None
    sources: Optional[dict] = None
    sample_titles: Optional[list] = None

    class Config:
        from_attributes = True
