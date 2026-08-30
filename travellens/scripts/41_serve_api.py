"""Run the LostinSriLanka review analysis API.

Usage
-----
    python scripts/41_serve_api.py           # port 8778 (default)
    PORT=9000 python scripts/41_serve_api.py # specific port

The interactive docs are at:
    http://localhost:8778/docs    (Swagger UI)
    http://localhost:8778/redoc  (ReDoc)

Key endpoints
-------------
    POST /analyse      send a review, get aspect labels back instantly
    GET  /reviews      list all user submissions
    GET  /reviews/{id} full breakdown for one submission
    GET  /stats        complaint-rate summary across submissions
    GET  /districts    canonical district names for the 'district' field
    GET  /aspects      the seven aspects and their definitions

Storage
-------
User submissions go to user_submissions.db by default (sibling of
travellens.db), or to Postgres if SUBMISSIONS_DATABASE_URL is set -- see
src/travellens/submissions_db.py. Running `python scripts/29_load_db.py`
never touches either.

Rows written before per-aspect polarity existed carry no per-aspect
verdicts; /stats reports them as `segments_awaiting_rescore` rather than
counting them. `python scripts/42_rescore_submissions.py` fills them in.

Environment (all optional, see .env.example)
--------------------------------------------
    SUBMISSIONS_DATABASE_URL  Postgres instead of local SQLite
    ALLOWED_ORIGINS           comma-separated CORS origins; default "*"
    ANALYSE_RATE_LIMIT        POST /analyse submissions per IP per minute
    PORT                      listen port; default 8778
"""
import os
import sys
from pathlib import Path

# Make the travellens package importable regardless of how the script is called.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# .env is read here, once, at the process that actually needs the variables
# in it -- not inside a library module, where auto-loading would surprise
# any other caller or test that imports it. A hosted deploy sets real
# environment variables directly and skips this entirely: load_dotenv()
# never overrides a variable that is already set, so nothing here can
# clobber a platform-injected value.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass  # python-dotenv not installed: fine, as long as the real env is set

import uvicorn

DEFAULT_PORT = 8778


def main():
    from travellens.submissions_db import active_backend

    port = int(os.environ.get("PORT") or DEFAULT_PORT)
    print("LostinSriLanka Review API")
    print("  docs  : http://localhost:{}/docs".format(port))
    print("  redoc : http://localhost:{}/redoc".format(port))
    print("  db    : submissions -> {}".format(active_backend()))
    print()
    sys.stdout.flush()

    uvicorn.run(
        "travellens.api:app",
        host="0.0.0.0",
        port=port,
        reload=False,           # set reload=True during development
        log_level="info",
    )


if __name__ == "__main__":
    main()
