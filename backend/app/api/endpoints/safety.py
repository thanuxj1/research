"""
Safety / Heatmap API endpoint.
IT22629180

Returns both clustered risk zones AND individual geolocated reports
so the frontend can show a rich, multi-layer map.
"""
from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case, distinct
from typing import List, Optional
from urllib.parse import quote_plus
from app.db.session import get_db
from app.db.models import RiskZone, Report
from app.ml.clustering_service import ClusteringService
from app.ml.pattern_predictor import get_predictor, SAFETY_TIPS, SL_LOCATIONS_FOR_SAFE_ZONES

router = APIRouter()
_clustering_service = ClusteringService(eps_km=2.0, min_samples=3)


DOMAIN_MAP = {
    "dailymirror": "dailymirror.lk",
    "daily_mirror": "dailymirror.lk",
    "daily mirror": "dailymirror.lk",
    "newsfirst": "newsfirst.lk",
    "news_first": "newsfirst.lk",
    "adaderana": "adaderana.lk",
    "derana": "adaderana.lk",
    "sundaytimes": "sundaytimes.lk",
    "sunday_times": "sundaytimes.lk",
    "hirunews": "hirunews.lk",
    "hiru": "hirunews.lk",
    "newswire": "newswire.lk",
    "ceylon": "ceylontoday.lk",
    "theisland": "island.lk",
    "island": "island.lk",
    "tamilguardian": "tamilguardian.com",
    "tripadvisor": "tripadvisor.com",
}


def build_source_link(raw_url: str, title: str, content: str = None, location_name: str = None, source: str = None) -> str:
    if raw_url and str(raw_url).strip().startswith("http"):
        u = str(raw_url).strip()
        if "maps.google.com" not in u and "google.com/maps/place" not in u:
            return u

    clean_t = (title or "").strip()
    if clean_t.startswith("Review:"):
        clean_t = clean_t.replace("Review:", "").strip()

    # Extract clean concise headline snippet
    headline = clean_t.split(" - ")[0].split(". ")[0].strip()[:90]

    combo = f"{source or ''} {title or ''} {content or ''}".lower()
    matched_domain = None
    for k, domain in DOMAIN_MAP.items():
        if k in combo:
            matched_domain = domain
            break

    if matched_domain and headline and len(headline) > 5 and headline.lower() != (location_name or "").lower():
        query = f'site:{matched_domain} "{headline}"'
        return f"https://www.google.com/search?q={quote_plus(query)}&btnI=1"
    elif headline and len(headline) > 5 and headline.lower() != (location_name or "").lower() and headline != "Safety Incident Report":
        query = f'"{headline}" {location_name or ""} Sri Lanka'
        return f"https://www.google.com/search?q={quote_plus(query)}&btnI=1"
    elif content and len(str(content).strip()) > 10:
        c_snip = str(content).strip().split(". ")[0][:80]
        query = f'"{c_snip}" {location_name or ""} Sri Lanka'
        return f"https://www.google.com/search?q={quote_plus(query)}&btnI=1"
    else:
        query = f"{location_name or 'Sri Lanka'} travel review"
        return f"https://www.google.com/search?q={quote_plus(query)}"

SOURCE_DISPLAY = {
    "adaderana": "Ada Derana 🏛️", "sundaytimes": "Sunday Times 🏛️",
    "daily_mirror": "Daily Mirror 🏛️", "google_news": "Google News 🏛️",
    "newsfirst": "Newsfirst 🏛️", "ceylon_today": "Ceylon Today 🏛️",
    "themorning_lk": "The Morning 🏛️", "hirunews_lk": "Hiru News 🏛️",
    "reddit": "Reddit 🟠", "youtube": "YouTube 🔴", "facebook": "Facebook 🔵",
    "google_maps": "Google Maps 📍", "tripadvisor": "TripAdvisor 🟢",
}
TRUSTED_SOURCES = {
    "adaderana", "sundaytimes", "daily_mirror", "google_news",
    "colombo_gazette", "newsfirst", "ceylon_today", "themorning_lk",
    "hirunews_lk", "theisland_lk", "economynext_lk", "newswire_lk",
}

# Shared non-tourism noise filter (mirrors safety_intelligence.py)
_NOISE_KW = {
    "migrant worker", "foreign employment", "housemaid", "housemaids",
    "domestic worker", "saudi employer", "kuwait employer", "slbfe",
    "plantation worker", "garment factory", "garment worker",
    "ballot paper", "electorate", "polling booth", "elections commission",
    "parliament election", "presidential election", "cabinet minister",
    "prime minister", "minister of", "state minister", "opposition leader",
    "no-confidence motion", "impeachment", "new constitution",
    "political party", "political solution", "political crisis",
    "ceasefire", "peace process", "ltte", "tnpf",
    "calls for immediate arrest", "calls on the government",
    "underworld", "drug trafficking", "heroin", "cocaine", "narcotics bureau",
    "murder suspect", "murder charge", "child abuse", "domestic violence",
    "remanded till", "remanded until", "remanded to", "further remanded",
    "magistrate court", "court order", "bail application",
    "trade union", "salary arrears", "pension", "bus fare hike",
    "disaster management", "meteorology", "sluice gates",
    "prison riot", "inmate", "prisoner escape",
    "poaching ring", "illegal logging", "excise department",
    "bellanwila", "myan kumara", "chief incumbent", "tusker",
    "beaten or harassed", "zoological department", "animal rights",
    "captive elephant", "elephant bath", "thera", "monk", "buddhist monk",
    "temple premises", "animal cruelty", "stray dogs", "rabies vaccination",
    "archaeological department", "excavation", "police woman", "army lieutenant",
    "navy officer", "air force officer", "university vice chancellor",
    "student union", "lecturers involved", "student protest", "higher education",
    "pradeshiya sabha", "uc chairman",
}
_TOURISM_OVERRIDE = {
    "tourist", "traveler", "traveller", "backpack", "hotel guest",
    "tuk tuk", "tuk-tuk", "gem scam", "guide scam", "safari scam",
    "overcharg", "rip off", "rip-off", "ripoff",
}

def is_tourism_irrelevant(title: str, content: str) -> bool:
    text = f"{title or ''} {content or ''}".lower()
    if not any(k in text for k in _NOISE_KW):
        return False
    if any(k in text for k in _TOURISM_OVERRIDE):
        return False
    return True

@router.get("/location-search")
def search_location(
    q: str,
    db: Session = Depends(get_db),
):
    """
    Search for a location by name and return a structured safety summary
    with all incident details — used by the map search bar.
    """
    from collections import Counter

    reports = (
        db.query(Report)
        .filter(Report.location_name.ilike(f"%{q}%"))
        .filter(Report.latitude.isnot(None), Report.longitude.isnot(None))
        .order_by(Report.risk_level.desc(), Report.created_at.desc())
        .limit(100)
        .all()
    )

    if not reports:
        # Try a broader search (title/content)
        reports = (
            db.query(Report)
            .filter(Report.title.ilike(f"%{q}%"))
            .order_by(Report.risk_level.desc())
            .limit(50)
            .all()
        )

    if not reports:
        return {"found": False, "query": q, "message": f"No incidents found for '{q}'"}

    # Aggregate stats
    scam_counts = Counter(r.scam_type for r in reports if r.scam_type)
    source_counts = Counter(r.source for r in reports if r.source)
    total_scams = sum(1 for r in reports if r.is_scam)
    avg_risk = sum((r.risk_level or 1) for r in reports) / len(reports)
    risk_score = round(min(avg_risk / 3, 1.0), 3)

    # Center coords
    geo_reports = [r for r in reports if r.latitude and r.longitude]
    center_lat = sum(r.latitude for r in geo_reports) / len(geo_reports) if geo_reports else None
    center_lon = sum(r.longitude for r in geo_reports) / len(geo_reports) if geo_reports else None

    # Source credibility mapper helper for user-friendly display
    def get_source_cred(src: str):
        s = (src or "").lower()
        if any(k in s for k in ["derana", "mirror", "newsfirst", "sundaytimes", "google_news", "ceylon", "hirunews", "newswire"]):
            return (0.92, "🏛️ Verified News Outlets")
        if any(k in s for k in ["tripadvisor", "maps", "destination", "reviews.csv"]):
            return (0.70, "🟢 Verified Traveler Reviews")
        return (0.40, "💬 Public Community Discussion")

    # Order sample incidents by source credibility weight (highest credibility first)
    reports_sorted = sorted(reports, key=lambda r: (-get_source_cred(r.source)[0], -(r.risk_level or 1)))

    sample_incidents = []
    seen_fingerprints = set()
    for r in reports_sorted:
        if len(sample_incidents) >= 10:
            break
        # Skip non-tourism noise (migrant worker stories, politics, etc.)
        if is_tourism_irrelevant(r.title, r.content):
            continue
        text_fingerprint = f"{r.title or ''} {r.content or ''}".lower().strip()[:100]
        if text_fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(text_fingerprint)

        cred_score, cred_lbl = get_source_cred(r.source)
        sample_incidents.append({
            "id": r.id,
            "title": (r.title or "")[:180],
            "scam_type": r.scam_type,
            "risk_level": r.risk_level,
            "risk_label": ["", "Low", "Moderate", "High"][r.risk_level or 1],
            "source": r.source,
            "source_label": SOURCE_DISPLAY.get(r.source or "", r.source or "Unknown"),
            "credibility_label": cred_lbl,
            "credibility_score": cred_score,
            "is_verified": cred_score >= 0.80,
            "url": build_source_link(r.url, r.title, r.content, q.title(), source=r.source),
            "content_snippet": (r.content or "")[:200],
            "date": str(r.created_at.date()) if r.created_at else None,
        })

    return {
        "found": True,
        "query": q,
        "location_name": q.title(),
        "center_lat": center_lat,
        "center_lon": center_lon,
        "total_reports": len(reports),
        "total_scams": total_scams,
        "risk_score": risk_score,
        "risk_label": "High Risk" if risk_score >= 0.65 else ("Moderate Risk" if risk_score >= 0.35 else "Low Risk"),
        "top_scam_types": [{"type": t, "count": c} for t, c in scam_counts.most_common(5)],
        "sources": [
            {
                "source": s,
                "label": SOURCE_DISPLAY.get(s, s),
                "count": c,
                "is_verified": s.lower() in TRUSTED_SOURCES
            }
            for s, c in source_counts.most_common(8)
        ],
        "incidents": sample_incidents,
    }


@router.get("/assess")
def assess_location(
    lat: float = Query(..., description="Latitude of the point to assess"),
    lng: float = Query(..., description="Longitude of the point to assess"),
    radius_km: float = Query(15.0, description="Search radius in km"),
    sort_by: Optional[str] = Query("credibility", description="Sort nearby incidents: credibility, nearest, risk"),
):
    """
    Click-anywhere Safety Intelligence Assessment.

    Computes a composite safety score for ANY GPS coordinate in Sri Lanka
    using IDW (Inverse Distance Weighted) spatial interpolation across
    120K+ cross-referenced, source-weighted, temporally-decayed reports.

    Returns: verdict, composite score, scam patterns, safety tips,
    nearby incidents, source breakdown, and authority report data.
    """
    from app.core.safety_intelligence import get_engine
    engine = get_engine()
    return engine.assess(lat, lng, radius_km, sort_by=sort_by or "credibility")



@router.get("/heatmap")
def get_heatmap(
    demographic: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Returns geolocated reports grouped into grid-based zones.
    Ensures consistency with the Dashboard by using shared scoring/clustering logic.
    """
    from app.core.clustering import get_grid_zones

    reports = db.query(Report).filter(
        Report.latitude.isnot(None),
        Report.longitude.isnot(None)
    ).all()

    if not reports:
        return _demo_zones()

    # Use shared grid-based clustering and scoring
    zones = get_grid_zones(reports)

    # Format for frontend and apply demographic adjustments
    result = []
    for i, z in enumerate(zones):
        # Additional metadata for the popup
        scam_types = {}
        sources = {}
        titles = []
        seen_fps = set()
        scam_count = 0
        
        for r in z["reports"]:
            if r.is_scam: scam_count += 1
            if r.scam_type:
                scam_types[r.scam_type] = scam_types.get(r.scam_type, 0) + 1
            src = r.source or "unknown"
            sources[src] = sources.get(src, 0) + 1

            if len(titles) < 5:
                # Skip non-tourism noise
                if is_tourism_irrelevant(r.title, r.content):
                    continue
                raw_t = (r.title or "").strip()
                if raw_t.startswith("Review:"):
                    raw_t = raw_t.replace("Review:", "").strip()

                if r.content and (not raw_t or raw_t.lower() == (z["location_name"] or "").lower() or len(raw_t) < 5):
                    snip = r.content.strip()[:85]
                    disp_t = snip[0].upper() + snip[1:] + ("..." if len(r.content) > 85 else "")
                else:
                    disp_t = raw_t if raw_t else f"Report - {z['location_name']}"

                fp = disp_t.lower()[:60]
                if fp not in seen_fps:
                    seen_fps.add(fp)
                    url = build_source_link(r.url, disp_t, r.content, z["location_name"], source=r.source)
                    titles.append({"title": disp_t, "url": url, "source": r.source})

        result.append({
            "cluster_id":        i,
            "risk_score":        z["risk_score"],
            "center_lat":        z["center_lat"],
            "center_lon":        z["center_lon"],
            "primary_scam_type": z["primary_scam_type"],
            "report_count":      z["report_count"],
            "scam_count":        scam_count,
            "location_name":     z["location_name"],
            "scam_types":        scam_types,
            "sources":           sources,
            "sample_titles":     titles,
        })

    # Apply demographic adjustment
    if demographic and demographic != "General":
        result = ClusteringService.apply_demographic_adjustment(result, demographic)

    result.sort(key=lambda x: x["report_count"], reverse=True)
    return result


@router.get("/reports-geo")
def get_geolocated_reports(
    scam_only: bool = False,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    """
    Returns individual geolocated reports for detailed map markers.
    """
    query = db.query(Report).filter(
        Report.latitude.isnot(None),
        Report.longitude.isnot(None),
    )
    if scam_only:
        query = query.filter(Report.is_scam == True)

    reports = query.order_by(Report.risk_level.desc()).limit(limit).all()

    return [
        {
            "id":              r.id,
            "lat":             r.latitude,
            "lon":             r.longitude,
            "title":           (r.title or "")[:120],
            "scam_type":       r.scam_type,
            "risk_level":      r.risk_level,
            "sentiment":       r.sentiment_score,
            "source":          r.source,
            "location_name":   r.location_name,
            "is_scam":         r.is_scam,
        }
        for r in reports
    ]


@router.get("/location/{location_name}")
def get_location_details(
    location_name: str,
    db: Session = Depends(get_db),
):
    """
    Returns detailed report data for a specific location.
    """
    reports = (
        db.query(Report)
        .filter(Report.location_name.ilike(f"%{location_name}%"))
        .order_by(Report.risk_level.desc())
        .limit(50)
        .all()
    )

    return {
        "location": location_name,
        "total_reports": len(reports),
        "reports": [
            {
                "id":         r.id,
                "title":      r.title,
                "content":    (r.content or "")[:300],
                "source":     r.source,
                "scam_type":  r.scam_type,
                "risk_level": r.risk_level,
                "sentiment":  r.sentiment_score,
                "url":        r.url,
            }
            for r in reports
        ],
    }


@router.post("/recluster")
def trigger_recluster(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    def _run():
        from app.db.session import SessionLocal
        _db = SessionLocal()
        try:
            count = _clustering_service.run(_db)
            print(f"[Recluster] Done - {count} zones updated.")
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": "Clustering started in background."}


@router.get("/zones")
def list_zones(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    zones = db.query(RiskZone).order_by(RiskZone.risk_score.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id":                zone.id,
            "cluster_id":        zone.cluster_id,
            "risk_score":        zone.risk_score,
            "primary_scam_type": zone.primary_scam_type,
            "report_count":      zone.report_count,
            "last_updated":      str(zone.last_updated) if zone.last_updated else None,
        }
        for zone in zones
    ]

@router.get("/safe-zones")
def get_safe_zones(db: Session = Depends(get_db)):
    """
    Returns known Sri Lanka locations with zero or very-low incident rates.
    These are displayed as green markers on the map.
    """
    predictor = get_predictor()

    # Ensure predictor is trained
    if not predictor._trained:
        reports = db.query(Report).filter(
            Report.latitude.isnot(None),
            Report.longitude.isnot(None),
        ).all()
        predictor.train(reports)

    return predictor.get_safe_zones(SL_LOCATIONS_FOR_SAFE_ZONES)


@router.get("/personalized-advice")
def get_personalized_advice(
    profile: str = "General",
    location: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Returns personalized safety tips for a traveller profile.
    Optionally filters/boosts based on the location's actual incident data.
    """
    tips = SAFETY_TIPS.get(profile, SAFETY_TIPS["General"])

    # If a location is provided, surface the most common scam types there
    location_scams = []
    if location:
        reports = (
            db.query(Report.scam_type, func.count(Report.id).label("cnt"))
            .filter(Report.location_name.ilike(f"%{location}%"))
            .filter(Report.scam_type.isnot(None))
            .group_by(Report.scam_type)
            .order_by(func.count(Report.id).desc())
            .limit(5)
            .all()
        )
        location_scams = [
            {"scam_type": r.scam_type, "count": r.cnt}
            for r in reports
        ]

    return {
        "profile":        profile,
        "location":       location,
        "tips":           tips,
        "location_scams": location_scams,
    }



def _demo_zones():
    return [
        {"cluster_id": 1, "risk_score": 0.90, "center_lat": 6.9344, "center_lon": 79.8428,
         "primary_scam_type": "gem_scam", "report_count": 15, "scam_count": 12,
         "location_name": "Colombo Fort", "scam_types": {"gem_scam": 8, "tuk_tuk_scam": 4},
         "sources": {"reddit": 10}, "sample_titles": [{"title": "Gem scam in Colombo", "url": "https://www.reddit.com/r/srilanka/comments/1234/gem_scam/"}]},
        {"cluster_id": 2, "risk_score": 0.55, "center_lat": 7.2906, "center_lon": 80.6337,
         "primary_scam_type": "overcharging", "report_count": 6, "scam_count": 4,
         "location_name": "Kandy", "scam_types": {"overcharging": 4, "fake_guide": 2},
         "sources": {"reddit": 4}, "sample_titles": [{"title": "Overcharged in Kandy", "url": "https://www.reddit.com/r/srilanka/comments/5678/overcharged/"}]},
    ]
