"""
Analytics API Endpoint — Live Dynamic Research Dashboard Data.
Serves real-time dynamic statistics derived from the SQLite/PostgreSQL Report table.
IT22629180
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from collections import defaultdict
from typing import Dict, List, Any

from app.db.session import get_db
from app.db.models import Report
from app.core.district_engine import get_boundary_index
from app.ml.source_weights import get_source_weight, get_weight_tier_label

router = APIRouter()

SOURCE_DISPLAY_NAMES = {
    "uk_fcdo": "UK FCDO",
    "fcdo_gov_uk": "UK FCDO",
    "tourist_police": "Tourist Police LK",
    "sl_tourism": "SLTDA Official",
    "ada_derana": "Ada Derana",
    "daily_mirror": "Daily Mirror",
    "sunday_times": "Sunday Times",
    "newsfirst": "Newsfirst",
    "newswire": "Newswire",
    "newswire_lk": "Newswire",
    "youtube": "YouTube",
    "google_news": "Google News",
    "tripadvisor_csv": "TripAdvisor",
    "tripadvisor": "TripAdvisor",
    "reddit": "Reddit",
    "dataset_csv": "Dataset Seed Data",
}

SOURCE_TIERS = {
    "UK FCDO": "Gov",
    "Tourist Police LK": "Gov",
    "SLTDA Official": "Gov",
    "Ada Derana": "News",
    "Daily Mirror": "News",
    "Sunday Times": "News",
    "Newsfirst": "News",
    "Newswire": "News",
    "YouTube": "Video",
    "Google News": "Aggr",
    "TripAdvisor": "Review",
    "Reddit": "UGC",
    "Dataset Seed Data": "Seed",
}


@router.get("/dashboard")
def get_analytics_dashboard(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Returns live dynamic analytics data computed directly from the Report database table:
    1. Temporal trends by year x district & year x scam_type.
    2. Demographic targeting distribution & scam affinity.
    3. Source credibility weights, report counts, and unweighted vs weighted risk score modeling.
    4. Cross-district pattern linking detected in the live incident dataset.
    """
    reports = db.query(Report).all()
    b_idx = get_boundary_index()

    yearly_district = defaultdict(lambda: defaultdict(int))
    yearly_scam_type = defaultdict(lambda: defaultdict(int))
    source_counts = defaultdict(int)
    source_risk_accum = defaultdict(lambda: {"raw_risk": 0.0, "count": 0, "weight": 0.0})
    demographic_counts = defaultdict(int)
    demographic_scams = defaultdict(lambda: defaultdict(int))
    week_scam_dists = defaultdict(lambda: defaultdict(list))

    total_incidents = len(reports)
    min_year = 2026
    max_year = 2010

    for r in reports:
        # Determine year
        yr_val = r.created_at.year if r.created_at else 2026
        yr_str = str(yr_val)
        if yr_val < min_year:
            min_year = yr_val
        if yr_val > max_year:
            max_year = yr_val

        # Determine district spatially or via location_name
        dist = None
        if r.latitude is not None and r.longitude is not None:
            dist = b_idx.locate(r.latitude, r.longitude)
        if not dist and r.location_name:
            loc_clean = r.location_name.strip()
            for entry in b_idx._entries:
                d = entry["district"]
                if d.lower() in loc_clean.lower():
                    dist = d
                    break
        if not dist:
            dist = "Colombo"

        scam = (r.scam_type or "General Safety").strip()
        raw_source = (r.source or "unknown").strip()
        display_source = SOURCE_DISPLAY_NAMES.get(raw_source, raw_source.replace("_", " ").title())
        demo = (r.demographic_target or "Tourists (general)").strip()
        if demo in ["None", "null", ""]:
            demo = "Tourists (general)"

        # Increment counts
        yearly_district[yr_str][dist] += 1
        yearly_scam_type[yr_str][scam] += 1
        source_counts[display_source] += 1
        demographic_counts[demo] += 1
        demographic_scams[demo][scam] += 1

        # Source risk modeling
        weight = getattr(r, "source_weight", None) or get_source_weight(raw_source)
        risk_val = float(r.risk_level or 1) / 5.0
        s_accum = source_risk_accum[display_source]
        s_accum["raw_risk"] += risk_val
        s_accum["count"] += 1
        s_accum["weight"] = weight

        # ISO Week grouping for cross-district detection
        if r.created_at:
            iso_wk = r.created_at.strftime("%Y-W%U")
            week_scam_dists[iso_wk][scam].append(dist)

    # Convert yearly dicts
    yearly_district_dict = {yr: dict(dists) for yr, dists in sorted(yearly_district.items())}
    yearly_scam_type_dict = {yr: dict(scams) for yr, scams in sorted(yearly_scam_type.items())}

    # Cross-district patterns detection
    cross_patterns = []
    for wk, scams_map in week_scam_dists.items():
        for scam_t, dist_list in scams_map.items():
            unique_dists = sorted(list(set(dist_list)))
            if len(unique_dists) > 1 or len(dist_list) >= 2:
                cross_patterns.append({
                    "week": wk,
                    "scam_type": scam_t,
                    "districts": unique_dists,
                    "count": len(dist_list),
                })
    cross_patterns.sort(key=lambda x: (x["count"], len(x["districts"])), reverse=True)

    # Source credibility table
    source_weight_data = []
    all_known_sources = [
        "UK FCDO", "SLTDA Official", "Ada Derana", "Daily Mirror", "Sunday Times",
        "Newswire", "YouTube", "Google News", "TripAdvisor", "Reddit"
    ]
    for src in all_known_sources:
        cnt = source_counts.get(src, 0)
        weight = get_source_weight(src.lower().replace(" ", "_"))
        tier = SOURCE_TIERS.get(src, "News")
        accum = source_risk_accum.get(src)
        adj_risk = round(accum["raw_risk"] / accum["count"] * weight, 2) if accum and accum["count"] > 0 else None
        source_weight_data.append({
            "source": src,
            "weight": round(weight, 2),
            "tier": tier,
            "reports": cnt,
            "adjusted_risk": adj_risk,
        })

    # Demographic breakdown data
    demographic_data = []
    demo_colors = {
        "Tourists (general)": "#3B82F6",
        "Tourists / Travel Vloggers": "#8B5CF6",
        "Solo Female": "#EC4899",
        "Backpacker": "#F59E0B",
        "Couple": "#10B981",
        "Family": "#06B6D4",
        "Senior Traveller": "#64748B",
    }
    for demo_name, cnt in demographic_counts.items():
        top_scams = sorted(demographic_scams[demo_name].items(), key=lambda x: x[1], reverse=True)
        demographic_data.append({
            "label": demo_name,
            "value": cnt,
            "color": demo_colors.get(demo_name, "#3B82F6"),
            "scam_affinity": [s[0] for s in top_scams[:3]],
        })

    return {
        "total_incidents": total_incidents,
        "date_range": f"{min_year} – {max_year}",
        "yearly_district": yearly_district_dict,
        "yearly_scam_type": yearly_scam_type_dict,
        "cross_district_patterns": cross_patterns[:15],
        "source_weight_data": source_weight_data,
        "demographic_data": demographic_data,
    }
