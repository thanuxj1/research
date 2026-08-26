"""Serve dashboard/ over HTTP. Run: python scripts/31_serve_dashboard.py

The dashboard is a static file, so this is only a convenience for viewing it
in a browser -- there is no application here to run.

Why this exists rather than `python -m http.server <port>`: that command takes
its port as a positional argument and ignores the PORT environment variable,
so it cannot cooperate with a harness that assigns a free port. Hard-coding a
number means a second session on the same machine collides with the first.

    PORT=8123 python scripts/31_serve_dashboard.py     # assigned port
    python scripts/31_serve_dashboard.py               # falls back to 8777
"""
import functools
import http.server
import os
import socketserver
import sys
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"
DEFAULT_PORT = 8777


def main():
    port = int(os.environ.get("PORT") or DEFAULT_PORT)
    if not DASHBOARD.exists():
        sys.exit("no dashboard yet -- run python scripts/10_refresh.py first")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(DASHBOARD))
    # Otherwise a restart within the TIME_WAIT window fails to bind.
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        print("serving {} on http://localhost:{}".format(DASHBOARD, port))
        sys.stdout.flush()
        httpd.serve_forever()


if __name__ == "__main__":
    main()
