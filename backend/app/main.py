import os
import sys
import subprocess
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.config import settings
from app.api.endpoints import reports, safety, admin, pipeline, ml, advisor, chat, authority, districts, analytics

_scheduler = None
_continuous_process = None

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Dynamic Safety Heatmap & Scam Analytics Engine — IT22629180",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    # Restrict to localhost frontend origins only.
    # If deploying publicly, set ALLOWED_ORIGINS env var and read it here.
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

def run_daily_collection():
    """Triggers the deep data collection script as a separate background process."""
    print("[Scheduler] Starting daily deep data collection...")
    script_path = os.path.join(os.path.dirname(__file__), "..", "deep_data_collection.py")
    subprocess.Popen([sys.executable, script_path])

def run_continuous_collector():
    """Starts the high-frequency continuous collector as a background process."""
    global _continuous_process
    if _continuous_process and _continuous_process.poll() is None:
        print("[Scheduler] Continuous collector already running for this API process.")
        return

    print("[Scheduler] Launching automated continuous data collection (High-Frequency Mode)...")
    script_path = os.path.join(os.path.dirname(__file__), "..", "data_pipeline", "continuous_runner.py")
    # Subprocess.Popen runs it in the background so it doesn't block the API
    _continuous_process = subprocess.Popen([sys.executable, script_path])

@app.on_event("startup")
def start_automated_systems():
    """Initializes all automated safety intelligence systems on startup."""
    global _scheduler

    # RESEARCH_MODE freezes the corpus so that reported results are reproducible.
    # Set RESEARCH_MODE=true in .env for every evaluation run.
    # Set to false (or remove) when you want the live pipeline to run again.
    if os.getenv("RESEARCH_MODE", "").lower() == "true":
        print("[RESEARCH_MODE] Automated collection disabled — corpus is frozen.")
        return

    # 1. Start the Daily Deep Scraper (scheduled for 2:00 AM)
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            run_daily_collection,
            trigger=CronTrigger(hour=2, minute=0),
            id="daily_deep_collection",
            replace_existing=True,
        )
        _scheduler.start()
        print("[Scheduler] Daily deep data collection scheduled for 2:00 AM.")
    
    # 2. Start the Continuous Real-Time Scraper (Always-On)
    run_continuous_collector()

    # 3. Trigger enhanced model training if model not yet built
    _trigger_enhanced_training()


def _trigger_enhanced_training():
    """Run enhanced ML training in background if model doesn't exist."""
    import threading
    model_path = os.path.join(
        os.path.dirname(__file__), "ml", "models", "enhanced_predictor.joblib"
    )
    if os.path.exists(model_path):
        print("[ML] Enhanced model already trained — skipping auto-training.")
        return

    def _run_training():
        script = os.path.join(
            os.path.dirname(__file__), "..", "training", "train_enhanced_model.py"
        )
        subprocess.run([sys.executable, script], capture_output=False)

    t = threading.Thread(target=_run_training, daemon=True)
    t.start()
    print("[ML] Enhanced model training started in background.")

@app.get("/")
def root():
    return {"message": "Dynamic Safety Heatmap API — IT22629180", "version": "1.0.0"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

PREFIX = settings.API_V1_STR
app.include_router(reports.router,   prefix=f"{PREFIX}/reports",   tags=["Reports"])
app.include_router(safety.router,    prefix=f"{PREFIX}/safety",    tags=["Safety Heatmap"])
app.include_router(districts.router, prefix=f"{PREFIX}/districts", tags=["District Risk Map"])
app.include_router(admin.router,     prefix=f"{PREFIX}/admin",     tags=["Admin Dashboard"])
app.include_router(pipeline.router,  prefix=f"{PREFIX}/pipeline",  tags=["Data Pipeline"])
app.include_router(ml.router,        prefix=f"{PREFIX}/ml",        tags=["ML Predictor"])
app.include_router(advisor.router,   prefix=f"{PREFIX}/advisor",   tags=["AI Advisor"])
app.include_router(authority.router, prefix=f"{PREFIX}/authority", tags=["Authority Security Dispatch"])
app.include_router(analytics.router, prefix=f"{PREFIX}/analytics", tags=["Research Analytics"])
app.include_router(chat.router,      prefix=f"{PREFIX}",           tags=["AI Chat"])
