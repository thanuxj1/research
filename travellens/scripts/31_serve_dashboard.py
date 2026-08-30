"""Serve the built pages as plain static files, with no analyser.

  python scripts/31_serve_dashboard.py         port 8777
  PORT=8123 python scripts/31_serve_dashboard.py

This is the light path: it opens the two built HTML files and nothing else, so
it starts instantly. `scripts/50_launch.py` is the real one -- it also runs the
API, which is what the portal needs to analyse anything, and it costs a few
seconds to load the transformer.

Why this file changed
---------------------
It used to serve the `dashboard/` directory alone, which meant
`localhost:8777/portal/index.html` returned a bare 404 from http.server:
"Nothing matches the given URI". That is a true statement and a useless one --
the portal exists, it is simply not under this root, and nothing on the page
said so. Somebody following an old habit landed on a stock error page with no
route back.

So it now serves the project root, both pages resolve, `/` goes to the
dashboard, and a 404 says where the thing you asked for actually lives. The
portal will load and be read-only: it has no API on this port and says so.
"""
import functools
import http.server
import os
import socketserver
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8777

PAGES = {
    "dashboard": ROOT / "dashboard" / "index.html",
    "portal": ROOT / "portal" / "index.html",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/dashboard/index.html")
            self.end_headers()
            return
        return super().do_GET()

    def send_error(self, code, message=None, explain=None):
        """A 404 here should say where the pages are, not just that this is not
        one of them."""
        if code != 404:
            return super().send_error(code, message, explain)
        body = (
            "<h1>Not here</h1>"
            "<p>This is the static file server. It serves two pages:</p>"
            "<ul>"
            "<li><a href='/dashboard/index.html'>/dashboard/index.html</a></li>"
            "<li><a href='/portal/index.html'>/portal/index.html</a> "
            "&mdash; read-only on this port; there is no analyser here</li>"
            "</ul>"
            "<p>For the whole system on one port &mdash; both pages plus the "
            "API the portal needs &mdash; stop this and run:</p>"
            "<pre>python scripts/50_launch.py</pre>"
        ).encode("utf-8")
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stdout.write("  %s\n" % (fmt % args))


def main():
    port = int(os.environ.get("PORT") or DEFAULT_PORT)
    missing = [name for name, path in PAGES.items() if not path.exists()]
    if len(missing) == len(PAGES):
        sys.exit("nothing built yet -- run python scripts/49_build_all.py first")

    handler = functools.partial(Handler, directory=str(ROOT))
    # Otherwise a restart within the TIME_WAIT window fails to bind.
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        print("\nstatic files only -- no analyser on this port")
        print("-" * 62)
        print("  dashboard  http://localhost:{}/dashboard/index.html".format(port))
        print("  portal     http://localhost:{}/portal/index.html   "
              "(read-only)".format(port))
        if missing:
            print("  not built  {} -- python scripts/49_build_all.py".format(
                ", ".join(missing)))
        print("-" * 62)
        print("  For the portal to actually analyse anything, stop this and run")
        print("  python scripts/50_launch.py  -- everything on one port.\n")
        sys.stdout.flush()
        httpd.serve_forever()


if __name__ == "__main__":
    main()
