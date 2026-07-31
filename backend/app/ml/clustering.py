from sklearn.cluster import DBSCAN
import numpy as np

class GeoClustering:
    def __init__(self, eps_km: float = 0.5, min_samples: int = 3):
        # Earth radius in km to convert km to radians for haversine
        self.kms_per_radian = 6371.0088
        self.eps = eps_km / self.kms_per_radian
        self.min_samples = min_samples

    def compute_clusters(self, locations):
        """
        locations: list of (latitude, longitude)
        """
        if len(locations) < self.min_samples:
            return []

        # Convert lat/lon to radians
        coords = np.radians(locations)
        
        # Using haversine metric for geospatial distance
        db = DBSCAN(eps=self.eps, min_samples=self.min_samples, algorithm='ball_tree', metric='haversine')
        db.fit(coords)
        
        cluster_labels = db.labels_
        return cluster_labels
