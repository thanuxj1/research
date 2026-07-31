"""
Shared grid-based clustering for geospatial reports.
IT22629180
"""
from collections import defaultdict
from app.core.scoring import calculate_risk_score

def get_grid_clusters(reports: list, precision: int = 2):
    """
    Groups reports by geolocated grid cells (rounding lat/lon).
    Precision 2 is roughly ~1km grid size in Sri Lanka.
    """
    location_groups = defaultdict(list)
    for r in reports:
        lat = getattr(r, "latitude", None)
        lon = getattr(r, "longitude", None)
        if lat is None or lon is None:
            continue
        key = (round(lat, precision), round(lon, precision))
        location_groups[key].append(r)
    return location_groups

def get_grid_zones(reports: list, precision: int = 2):
    """
    Groups reports into grid cells and calculates risk scores for each.
    Used to ensure consistency between the Map and Dashboard.
    """
    groups = get_grid_clusters(reports, precision)
    zones = []
    for (lat, lon), group_reports in groups.items():
        score = calculate_risk_score(group_reports)
        
        # Primary scam type
        scam_types = {}
        for r in group_reports:
            st = getattr(r, "scam_type", None)
            if st:
                scam_types[st] = scam_types.get(st, 0) + 1
        
        primary_scam = max(scam_types, key=scam_types.get) if scam_types else None
        
        # Location name (take first available)
        loc_name = None
        for r in group_reports:
            name = getattr(r, "location_name", None)
            if name:
                loc_name = name
                break
        
        zones.append({
            "center_lat": lat,
            "center_lon": lon,
            "risk_score": score,
            "report_count": len(group_reports),
            "primary_scam_type": primary_scam,
            "location_name": loc_name,
            "reports": group_reports  # Keep raw reports for further processing if needed
        })
    return zones
