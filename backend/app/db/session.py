"""
Database session — with SQLite fallback for local development.
If PostgreSQL connection fails, automatically uses SQLite at e:/research/backend/safety_heatmap.db
IT22629180
"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


def _get_engine():
    """Try PostgreSQL first, fall back to SQLite for local dev."""
    pg_uri = settings.SQLALCHEMY_DATABASE_URI
    try:
        engine = create_engine(pg_uri, pool_pre_ping=True, connect_args={})
        # Quick connection test
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[DB] Connected to PostgreSQL")
        return engine
    except Exception as e:
        print(f"[DB] PostgreSQL unavailable ({e.__class__.__name__}): {e}")
        print("[DB] Falling back to SQLite: safety_heatmap.db")
        # SQLite fallback — stores in backend dir
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "safety_heatmap.db"
        )
        sqlite_uri = f"sqlite:///{db_path}"
        sqlite_engine = create_engine(
            sqlite_uri,
            connect_args={"check_same_thread": False},
        )
        print(f"[DB] SQLite DB at: {db_path}")
        return sqlite_engine


engine = _get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
