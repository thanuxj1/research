"""
Clustering service — wraps GeoClustering and persists RiskZones to DB.
IT22629180
"""
import numpy as np
from collections import Counter
from typing import List
from sqlalchemy.orm import Session
from app.db.models import Report, RiskZone
from app.ml.clustering import GeoClustering
from app.core.scoring import calculate_risk_score


# Demographic risk weight multipliers
DEMOGRAPHIC_WEIGHTS = {
    "Solo Female": {"harassment": 1.6, "gem_scam": 1.1, "tuk_tuk_scam": 1.3,
                    "unsafe_area": 1.4},
    "Solo Male":   {"gem_scam": 1.4, "transport_fraud": 1.2, "overcharging": 1.1},
    "Family":      {"overcharging": 1.3, "fake_guide": 1.2, "accommodation_scam": 1.2},
    "Couple":      {"overcharging": 1.2, "fake_guide": 1.1, "food_scam": 1.1},
    "Group":       {"transport_fraud": 1.2, "overcharging": 1.1},
}


class ClusteringService:
    def __init__(self, eps_km: float = 0.5, min_samples: int = 3):
        self.clusterer = GeoClustering(eps_km=eps_km, min_samples=min_samples)

    def run(self, db: Session) -> int:
        """
        Full clustering pipeline:
          1. Fetch geolocated reports from DB
          2. Run DBSCAN
          3. For each cluster: compute centroid, risk score, primary scam type
          4. Upsert into risk_zones table
        Returns: number of clusters created/updated
        """
        reports: List[Report] = (
            db.query(Report)
            .filter(Report.latitude.isnot(None), Report.longitude.isnot(None))
            .all()
        )

        if len(reports) < self.clusterer.min_samples:
            print(f"[Clustering] Not enough geolocated reports ({len(reports)}). "
                  f"Need at least {self.clusterer.min_samples}.")
            return 0

        locations = [(r.latitude, r.longitude) for r in reports]
        labels = self.clusterer.compute_clusters(locations)

        unique_clusters = set(labels) - {-1}   # -1 = DBSCAN noise
        print(f"[Clustering] {len(reports)} reports -> {len(unique_clusters)} clusters")

        updated = 0
        for cluster_id in unique_clusters:
            cluster_reports = [r for r, l in zip(reports, labels) if l == cluster_id]

            center_lat = float(np.mean([r.latitude  for r in cluster_reports]))
            center_lon = float(np.mean([r.longitude for r in cluster_reports]))

            risk_score = calculate_risk_score(cluster_reports)

            scam_types = [r.scam_type for r in cluster_reports if r.scam_type]
            primary_scam = (Counter(scam_types).most_common(1)[0][0]
                            if scam_types else None)

            existing = (
                db.query(RiskZone)
                .filter(RiskZone.cluster_id == int(cluster_id))
                .first()
            )

            if existing:
                existing.risk_score       = risk_score
                existing.primary_scam_type = primary_scam
                existing.report_count     = len(cluster_reports)
            else:
                zone = RiskZone(
                    cluster_id        = int(cluster_id),
                    risk_score        = risk_score,
                    primary_scam_type = primary_scam,
                    report_count      = len(cluster_reports),
                )
                db.add(zone)
            updated += 1

        db.commit()
        print(f"[Clustering] Upserted {updated} risk zones.")
        return updated

    @staticmethod
    def apply_demographic_adjustment(
        zones: list, demographic: str
    ) -> list:
        """
        Adjusts risk scores in-place based on tourist profile.
        Zones are dicts with keys: risk_score, primary_scam_type.
        """
        weights = DEMOGRAPHIC_WEIGHTS.get(demographic, {})
        # Normalize weights keys to lowercase for robust lookup
        norm_weights = {k.lower(): v for k, v in weights.items()}
        
        for zone in zones:
            scam = zone.get("primary_scam_type")
            if scam:
                # Normalize scam name (e.g. "Gem Scam" -> "gem_scam")
                norm_scam = str(scam).lower().replace(" ", "_")
                if norm_scam in norm_weights:
                    zone["risk_score"] = round(
                        min(zone["risk_score"] * norm_weights[norm_scam], 1.0), 4
                    )
        return zones
