
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.ml.clustering_service import ClusteringService

def update_heatmap():
    print("Running clustering service to update risk zones...")
    db = SessionLocal()
    service = ClusteringService(eps_km=0.5, min_samples=3)
    count = service.run(db)
    db.close()
    print(f"Successfully processed {count} risk zones.")

if __name__ == "__main__":
    update_heatmap()
