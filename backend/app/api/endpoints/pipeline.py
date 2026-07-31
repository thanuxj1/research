"""
Pipeline trigger API endpoint.
IT22629180
"""
from fastapi import APIRouter, BackgroundTasks
from datetime import datetime

router = APIRouter()

_last_run: dict = {"started_at": None, "status": "idle", "counts": {}}


def _run_pipeline():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    _last_run["status"] = "running"
    _last_run["started_at"] = datetime.utcnow().isoformat()
    try:
        from data_pipeline.main_pipeline import run_collection
        run_collection()
        _last_run["status"] = "completed"
    except Exception as e:
        _last_run["status"] = f"error: {e}"


@router.post("/run")
def trigger_pipeline(background_tasks: BackgroundTasks):
    """Trigger data collection pipeline (Reddit + YouTube + Web)."""
    if _last_run["status"] == "running":
        return {"message": "Pipeline already running.", "status": _last_run}
    background_tasks.add_task(_run_pipeline)
    return {"message": "Pipeline started.", "started_at": datetime.utcnow().isoformat()}


@router.get("/status")
def pipeline_status():
    """Get status of the last pipeline run."""
    return _last_run
