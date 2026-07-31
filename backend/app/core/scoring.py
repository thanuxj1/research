"""
Shared scoring logic for safety risk calculation.
IT22629180
"""

import math
from datetime import datetime, timezone

def calculate_risk_score(group_reports: list) -> float:
    """
    Calculates a risk score (0.0 to 1.0) for a group of reports.
    Applies an Exponential Temporal Decay Algorithm so older clusters cool down over time.
    """
    if not group_reports:
        return 0.0
    
    # avg_severity: (sum of risk levels) / (count * 3)
    total_severity = sum((getattr(r, "risk_level", 1) or 1) for r in group_reports)
    avg_severity = total_severity / (len(group_reports) * 3)
    
    # scam_ratio: percentage of reports in this group that are scams
    scam_reports = [r for r in group_reports if getattr(r, "is_scam", False)]
    scam_ratio = len(scam_reports) / len(group_reports)
    
    # Base weighted calculation
    base_risk = avg_severity * 0.75 + scam_ratio * 0.25
    
    # --- TEMPORAL DECAY ALGORITHM ---
    # Half-life = 180 days (approx 6 months). lambda = ln(2)/180 ≈ 0.00385
    DECAY_LAMBDA = 0.00385
    now = datetime.now(timezone.utc)
    
    total_decay_weight = 0.0
    for r in group_reports:
        created_at = getattr(r, "created_at", None)
        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            days_ago = max(0, (now - created_at).days)
        else:
            days_ago = 0
            
        decay_factor = math.exp(-DECAY_LAMBDA * days_ago)
        total_decay_weight += decay_factor
        
    # The final cluster multiplier is the average decay weight
    # e.g., if all reports are 1 year old, the risk score drops by ~75%
    avg_decay_multiplier = total_decay_weight / len(group_reports)
    
    final_risk_score = min(base_risk * avg_decay_multiplier, 1.0)
    
    return round(final_risk_score, 4)
