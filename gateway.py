"""One URL for all three applications.

    python gateway.py            http://localhost:8080

What this is
------------
The repository holds three independent applications with five services between
them, and running them meant five ports and five things to start. This puts all
of it behind one origin:

    /               a landing page
    /safety/        SafeTravel LK          (built React app)
    /api/...          its FastAPI backend  (proxied)
    /assistance/... , /budget_planner/... , /questions/...
                      its Flask services   (proxied to wherever they run)
    /food/          the food assistant     (built React app)
    /food/api/...     its FastAPI backend  (proxied)
    /travellens/    LostinSriLanka         (mounted, not proxied)

Why the three are handled differently, which is the whole design
----------------------------------------------------------------
**travellens is mounted**, not proxied. It is a FastAPI app in this
repository, so it becomes part of this process: no extra port, nothing else to
start, and no proxy hop. Its own routes then live under /travellens, which it
handles because its root redirect is built from `root_path` and its portal
derives the API base from its own path rather than from `location.origin`.

**The two React apps are served as built files.** A single-page app behind a
path prefix needs that prefix compiled into its asset URLs (`base` in
vite.config.js), so proxying a dev server would serve a page asking this
gateway for /assets/... and getting 404s. Building is also what a reader of
this repository should be running anyway. Neither app uses a router, so there
is no client-side basename to worry about.

**Their backends are proxied**, because they are separate Python applications
with their own dependencies -- importing them into this process would make one
project's requirements everybody's problem. They stay on their own ports and
this forwards to them.

What it does not do
-------------------
It does not start the two backends. They have their own environments and their
own start-up costs, and a gateway that silently spawns other people's servers
is a gateway nobody can debug. `python gateway.py --check` says which are up.
"""
# No `from __future__ import annotations` here, deliberately. It turns every
# annotation into a string, and FastAPI then resolves them with
# typing.get_type_hints() against the MODULE globals -- where `Request` is not
# defined, because fastapi is imported inside build_app() so that --check can
# run without it. The result was FastAPI reading `request: Request` as a query
# parameter and answering every proxied call with
# 422 {"loc": ["query", "request"], "msg": "Field required"}.

import argparse
import sys
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent

# Where each proxied backend lives. Overridable so this works against a
# deployed instance as easily as a local one.
UPSTREAMS: Dict[str, str] = {
    "safety_api": "http://127.0.0.1:8000",
    "food_api": "http://127.0.0.1:8001",
    # The safety frontend's own dev proxy points at a deployed host for these,
    # so the default here matches what that app already expects rather than
    # assuming somebody is running Flask locally.
    "flask": "http://51.20.34.58:5001",
}

SPAS = {
    "/safety": ROOT / "frontend" / "dist",
    "/food": ROOT / "food-assistant" / "frontend" / "dist",
}

BUILD_HINT = {
    "/safety": "cd frontend && npm install && npm run build",
    "/food": ("cd food-assistant/frontend && npm install && npm run build"),
}


def build_app(upstreams: Optional[Dict[str, str]] = None):
    import httpx
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import HTMLResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles

    up = dict(UPSTREAMS)
    up.update(upstreams or {})

    app = FastAPI(title="research gateway", docs_url=None, redoc_url=None)

    # One client for the process. Opening a connection per request to a local
    # service is not free, and this sits in front of every API call the two
    # React apps make.
    client = httpx.AsyncClient(timeout=60.0, follow_redirects=False)

    @app.on_event("shutdown")
    async def _close():
        await client.aclose()

    async def forward(request: Request, target: str) -> Response:
        """Pass a request upstream and hand the answer back unchanged.

        Hop-by-hop headers are dropped on both legs: forwarding Host makes the
        upstream generate links for this gateway's name, and returning
        Content-Length or Transfer-Encoding alongside a body the server
        re-encodes produces a response the browser cannot parse.
        """
        drop_req = {"host", "content-length", "connection"}
        headers = {k: v for k, v in request.headers.items()
                   if k.lower() not in drop_req}
        try:
            upstream = await client.request(
                request.method, target,
                headers=headers,
                content=await request.body(),
                params=request.query_params,
            )
        except httpx.ConnectError:
            return Response(
                content=("The service behind this path is not running.\n\n"
                         "Tried: {}\n".format(target)).encode(),
                status_code=502, media_type="text/plain")
        drop_res = {"content-length", "transfer-encoding", "connection",
                    "content-encoding"}
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers={k: v for k, v in upstream.headers.items()
                     if k.lower() not in drop_res},
            media_type=upstream.headers.get("content-type"),
        )

    # ---------------------------------------------------------- proxies
    # Registered before the static mounts so a path like /food/api is matched
    # here rather than swallowed by the /food SPA mount.
    @app.api_route("/food/api/{path:path}",
                   methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def food_api(path: str, request: Request):
        return await forward(request, "{}/{}".format(up["food_api"], path))

    @app.api_route("/api/{path:path}",
                   methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def safety_api(path: str, request: Request):
        return await forward(request, "{}/api/{}".format(up["safety_api"], path))

    for service in ("assistance", "budget_planner", "questions"):
        def make(svc):
            async def handler(path: str, request: Request):
                return await forward(
                    request, "{}/{}/{}".format(up["flask"], svc, path))
            return handler
        app.add_api_route("/{}/{{path:path}}".format(service), make(service),
                          methods=["GET", "POST"])

    # ------------------------------------------------------- travellens
    # Mounted, so it runs in this process. Its own /docs comes along with it.
    try:
        sys.path.insert(0, str(ROOT / "travellens" / "src"))
        from travellens.api import app as travellens_app
        app.mount("/travellens", travellens_app)
        travellens_mounted = True
    except Exception as exc:                       # deps missing, or not built
        travellens_mounted = False
        _travellens_error = str(exc)

        @app.get("/travellens", include_in_schema=False)
        @app.get("/travellens/{path:path}", include_in_schema=False)
        def travellens_missing(path: str = ""):
            return HTMLResponse(
                "<h1>travellens is not available</h1><p>It could not be "
                "imported: <code>{}</code></p><p>Install its dependencies:<br>"
                "<code>cd travellens &amp;&amp; pip install -r "
                "requirements.txt</code></p>".format(_travellens_error),
                status_code=503)

    # ------------------------------------------------------- landing page
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index():
        cards = []
        for path, label, blurb in (
            ("/safety/", "SafeTravel LK",
             "Safety heatmap and scam analytics across Sri Lankan districts."),
            ("/food/", "Food assistant",
             "Sri Lankan food recommendations, with a health and price view."),
            ("/travellens/", "LostinSriLanka",
             "What visitors complain about, from 46,854 tourist reviews."),
        ):
            ready = True
            hint = ""
            for mount, dist in SPAS.items():
                if path.startswith(mount + "/") and not (dist / "index.html").exists():
                    ready, hint = False, BUILD_HINT[mount]
            if path == "/travellens/" and not travellens_mounted:
                ready, hint = False, "cd travellens && pip install -r requirements.txt"
            cards.append(
                "<a class='card{cls}' href='{href}'><h2>{label}</h2>"
                "<p>{blurb}</p>{note}</a>".format(
                    cls="" if ready else " down", href=path if ready else "#",
                    label=label, blurb=blurb,
                    note="" if ready else
                    "<code>{}</code>".format(hint)))
        return PAGE.replace("__CARDS__", "\n".join(cards))

    # ------------------------------------------------- the built SPAs
    # Mounted last: a StaticFiles mount matches every path beneath it, so it
    # has to come after the API routes that live under the same prefix.
    for mount, dist in SPAS.items():
        if (dist / "index.html").exists():
            app.mount(mount, StaticFiles(directory=str(dist), html=True),
                      name=mount.strip("/"))
        else:
            def make_missing(m):
                def handler():
                    return HTMLResponse(
                        "<h1>Not built yet</h1><p>Run:</p><pre>{}</pre>".format(
                            BUILD_HINT[m]), status_code=503)
                return handler
            app.add_api_route(mount, make_missing(mount), include_in_schema=False)
            app.add_api_route(mount + "/{path:path}", make_missing(mount),
                              include_in_schema=False)

    # A mount at /safety only answers /safety/... -- without this, the bare
    # path 404s and the landing page's own links look broken.
    @app.get("/safety", include_in_schema=False)
    def _safety_slash():
        return RedirectResponse("/safety/")

    @app.get("/food", include_in_schema=False)
    def _food_slash():
        return RedirectResponse("/food/")

    return app


PAGE = """<!doctype html><meta charset="utf-8">
<title>research</title>
<style>
  :root { --ink:#16150F; --muted:#5F5C50; --line:#DFDBCD; --paper:#FCFBF7;
          --card:#FFFFFF; --accent:#1F5C57; }
  * { box-sizing:border-box }
  body { margin:0; background:var(--paper); color:var(--ink); min-height:100vh;
         font:15px/1.6 Inter,system-ui,sans-serif; display:flex;
         align-items:center; justify-content:center; padding:40px 24px }
  main { max-width:900px; width:100% }
  h1 { font:600 30px/1.2 Georgia,serif; margin:0 0 6px; letter-spacing:-.02em }
  .sub { color:var(--muted); margin:0 0 34px; max-width:60ch }
  .grid { display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)) }
  .card { display:block; text-decoration:none; color:inherit; background:var(--card);
          border:1px solid var(--line); border-radius:5px; padding:20px 22px }
  .card:hover { border-color:var(--accent) }
  .card h2 { font:600 17px/1.3 Georgia,serif; margin:0 0 6px; color:var(--accent) }
  .card p { margin:0; color:var(--muted); font-size:14px }
  .card.down { opacity:.6; cursor:default }
  .card.down:hover { border-color:var(--line) }
  .card code { display:block; margin-top:10px; font-size:12px; color:var(--ink);
               background:#F4F2EA; padding:6px 8px; border-radius:3px;
               overflow-wrap:anywhere }
</style>
<main>
  <h1>research</h1>
  <p class="sub">Three applications, one origin. Each is independent &mdash;
    separate stack, separate data. A card without a link needs building or
    installing first; the command is on the card.</p>
  <div class="grid">__CARDS__</div>
</main>
"""


def check(port: int) -> int:
    """Say what is reachable, without starting anything."""
    import httpx
    print("\ngateway checks")
    print("-" * 62)
    ok = True
    for mount, dist in SPAS.items():
        built = (dist / "index.html").exists()
        ok = ok and built
        print("  {:<10} {}".format(
            mount, "built" if built else "NOT BUILT -> " + BUILD_HINT[mount]))
    for name, url in UPSTREAMS.items():
        try:
            httpx.get(url + "/", timeout=3)
            print("  {:<10} up at {}".format(name, url))
        except Exception:
            print("  {:<10} NOT REACHABLE at {}".format(name, url))
    try:
        sys.path.insert(0, str(ROOT / "travellens" / "src"))
        import travellens.api  # noqa: F401
        print("  {:<10} importable (runs in this process)".format("travellens"))
    except Exception as exc:
        ok = False
        print("  {:<10} NOT importable: {}".format("travellens", exc))
    print("-" * 62)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--check", action="store_true",
                    help="report what is reachable, then exit")
    ap.add_argument("--safety-api", default=UPSTREAMS["safety_api"])
    ap.add_argument("--food-api", default=UPSTREAMS["food_api"])
    ap.add_argument("--flask", default=UPSTREAMS["flask"])
    args = ap.parse_args()

    if args.check:
        return check(args.port)

    import uvicorn
    app = build_app({"safety_api": args.safety_api,
                     "food_api": args.food_api,
                     "flask": args.flask})
    base = "http://{}:{}".format(
        "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host,
        args.port)
    print("\neverything on one URL")
    print("-" * 62)
    print("  {}/".format(base))
    print("  {}/safety/".format(base))
    print("  {}/food/".format(base))
    print("  {}/travellens/".format(base))
    print("-" * 62)
    print("  travellens runs in this process. The two backends are proxied:")
    print("    safety API  {}".format(args.safety_api))
    print("    food API    {}".format(args.food_api))
    print("  Start those separately; see README.md.\n")
    sys.stdout.flush()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
