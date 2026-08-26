"""Entry point shim.

The application now lives in the `app` package (see `app/main.py`). This module
is kept so the documented run command continues to work unchanged:

    uvicorn main:app --reload

Equivalent:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from app.main import app

__all__ = ["app"]
