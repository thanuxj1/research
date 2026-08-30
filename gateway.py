"""One URL. Three functions. One web app.

    python gateway.py            http://localhost:8080

The three functions
-------------------
This repository holds three independent applications. Running them meant
separate ports and separate things to start. This puts all of it behind one
origin with one navigation:

    /               unified portal (three-tab app)
    /ai/            AI Travel Assistant — destination recommendations,
                    budget planner, and cultural Q&A
    /food/          Food Guide — Nihara's food recommender
    /travellens/    Reviews — LostinSriLanka review analysis

Backend APIs (proxied, start separately)
-----------------------------------------
    /assistance/...      ⎫
    /budget_planner/...  ⎬ Flask AI services (udesh/irusha)
    /questions/...       ⎭

    /food/api/...        food assistant FastAPI

    python gateway.py --check     # says what is reachable, starts nothing

Why the three apps are handled differently
------------------------------------------
**travellens is mounted**, not proxied. It is a FastAPI app in this
repository — no extra port, no proxy hop. Its routes live under /travellens
and it handles them because its root redirect uses root_path, and the portal
derives its API base from its own URL path.

**The two React SPAs are served as built files.** A single-page app behind a
path prefix needs that prefix compiled into its asset URLs (base in
vite.config.js). Build first:

    cd frontend && npm install && npm run build
    cd food-assistant/frontend && npm install && npm run build

**The backends are proxied** because they are separate Python processes with
separate dependencies. The gateway forwards to them; start them yourself:

    cd backend_flask && python app.py               # port 5000 or 5001
    cd food-assistant/backend && uvicorn main:app   # port 8001

What it does not start
----------------------
Nothing. A gateway that silently spawns other people's servers is one nobody
can debug. Services that are down return a 502 with the address it tried.
"""
# No `from __future__ import annotations` here, deliberately. It turns every
# annotation into a string, and FastAPI resolves them with
# typing.get_type_hints() against MODULE globals — where `Request` is not
# defined, because fastapi is imported inside build_app() so that --check can
# run without it. The result was FastAPI reading `request: Request` as a query
# parameter and answering every proxied call with
# 422 {"loc": ["query", "request"], "msg": "Field required"}.

import argparse
import sys
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent

# Where each proxied backend lives. Override via CLI flags.
UPSTREAMS: Dict[str, str] = {
    "food_api": "http://127.0.0.1:8001",
    # Flask AI services — deployed host or local.
    "flask": "http://51.20.34.58:5001",
}

SPAS = {
    "/ai": ROOT / "frontend" / "dist",
    "/food": ROOT / "food-assistant" / "frontend" / "dist",
}

BUILD_HINT = {
    "/ai": "cd frontend && npm install && npm run build",
    "/food": "cd food-assistant/frontend && npm install && npm run build",
}


def build_app(upstreams: Optional[Dict[str, str]] = None):
    import httpx
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import HTMLResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles

    up = dict(UPSTREAMS)
    up.update(upstreams or {})

    app = FastAPI(title="Sri Lanka Tourism", docs_url=None, redoc_url=None)

    client = httpx.AsyncClient(timeout=60.0, follow_redirects=False)

    @app.on_event("shutdown")
    async def _close():
        await client.aclose()

    async def forward(request: Request, target: str) -> Response:
        """Pass a request upstream and return the answer unchanged.

        Hop-by-hop headers are dropped on both legs: forwarding Host makes the
        upstream generate links for this gateway's name, and returning
        Content-Length or Transfer-Encoding alongside a re-encoded body
        produces a response the browser cannot parse.
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
                content=("Service not running.\n\nTried: {}\n".format(
                    target)).encode(),
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

    # ---------------------------------------------------------- Flask proxies
    # Registered before the static mounts so /ai/... API calls are not
    # swallowed by the SPA mount.
    for service in ("assistance", "budget_planner", "questions"):
        def make(svc):
            async def handler(path: str, request: Request):
                return await forward(
                    request,
                    "{}/{}/{}".format(up["flask"], svc, path))
            return handler
        app.add_api_route(
            "/{}/{{path:path}}".format(service), make(service),
            methods=["GET", "POST"])

    # ---------------------------------------------------------- food API proxy
    @app.api_route("/food/api/{path:path}",
                   methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def food_api(path: str, request: Request):
        return await forward(request, "{}/{}".format(up["food_api"], path))

    # ------------------------------------------------------- travellens mount
    try:
        sys.path.insert(0, str(ROOT / "travellens" / "src"))
        from travellens.api import app as travellens_app
        app.mount("/travellens", travellens_app)
        travellens_mounted = True
    except Exception as exc:
        travellens_mounted = False
        _travellens_error = str(exc)

        @app.get("/travellens", include_in_schema=False)
        @app.get("/travellens/{path:path}", include_in_schema=False)
        def travellens_missing(path: str = ""):
            return HTMLResponse(
                "<h1>Reviews not available</h1>"
                "<p>Could not import travellens: <code>{}</code></p>"
                "<p><code>cd travellens &amp;&amp; pip install -r "
                "requirements.txt</code></p>".format(_travellens_error),
                status_code=503)

    # ------------------------------------------------------- unified portal
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def portal():
        return PORTAL_HTML

    # Slash redirects so /ai and /food bare paths reach the SPA.
    @app.get("/ai", include_in_schema=False)
    def _ai_slash():
        return RedirectResponse("/ai/")

    @app.get("/food", include_in_schema=False)
    def _food_slash():
        return RedirectResponse("/food/")

    # ------------------------------------------------- built SPAs (last)
    for mount, dist in SPAS.items():
        if (dist / "index.html").exists():
            app.mount(mount, StaticFiles(directory=str(dist), html=True),
                      name=mount.strip("/"))
        else:
            def make_missing(m):
                def handler():
                    return HTMLResponse(
                        "<h1>Not built yet</h1><pre>{}</pre>".format(
                            BUILD_HINT[m]),
                        status_code=503)
                return handler
            app.add_api_route(mount, make_missing(mount),
                              include_in_schema=False)
            app.add_api_route(mount + "/{path:path}", make_missing(mount),
                              include_in_schema=False)

    return app


# ---------------------------------------------------------------------------
# The unified portal shell — one HTML page, three tabs, three iframes.
# Each iframe is pre-inserted but hidden; clicking a tab reveals its iframe.
# The first click on a tab loads the iframe src; subsequent clicks just show
# the already-loaded frame (no reload). This means the review map, which
# builds its assets on first load, only pays that cost once.
# ---------------------------------------------------------------------------
PORTAL_HTML = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sri Lanka Tourism</title>
<style>
  :root {
    --ink:    #16150F;
    --muted:  #5F5C50;
    --line:   #E0DDD0;
    --paper:  #FAFAF7;
    --accent: #1F5C57;
    --active-bg: #1F5C57;
    --active-fg: #FFFFFF;
    --nav-h:  52px;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0 }
  html, body { height: 100%; overflow: hidden }
  body {
    font: 14px/1.5 Inter, system-ui, sans-serif;
    background: var(--paper);
    color: var(--ink);
    display: flex;
    flex-direction: column;
  }

  /* ── top nav ──────────────────────────────────────────────── */
  nav {
    height: var(--nav-h);
    display: flex;
    align-items: center;
    gap: 0;
    padding: 0 20px;
    background: var(--paper);
    border-bottom: 1px solid var(--line);
    flex-shrink: 0;
  }
  .brand {
    font-weight: 700;
    font-size: 15px;
    letter-spacing: -0.02em;
    color: var(--accent);
    margin-right: 28px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .brand span { color: var(--muted); font-weight: 400 }
  .tabs {
    display: flex;
    gap: 2px;
  }
  .tab {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 6px 18px;
    border-radius: 6px;
    border: none;
    background: transparent;
    color: var(--muted);
    font: 13.5px/1 Inter, system-ui, sans-serif;
    font-weight: 500;
    cursor: pointer;
    transition: background .12s, color .12s;
    white-space: nowrap;
  }
  .tab:hover { background: rgba(31,92,87,.07); color: var(--accent) }
  .tab.active {
    background: var(--active-bg);
    color: var(--active-fg);
  }
  .tab .icon { font-size: 15px }

  /* ── frame area ───────────────────────────────────────────── */
  .frames {
    flex: 1;
    position: relative;
    overflow: hidden;
  }
  .frames iframe {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: none;
    display: none;
  }
  .frames iframe.active { display: block }
  .placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: var(--muted);
    font-size: 14px;
  }
  .placeholder.hidden { display: none }
  .placeholder .big { font-size: 36px }
</style>

<nav>
  <div class="brand">TravelLens <span>Sri Lanka</span></div>
  <div class="tabs">
    <button class="tab active" data-tab="reviews">
      <span class="icon">🗺️</span> Reviews
    </button>
    <button class="tab" data-tab="assistant">
      <span class="icon">✨</span> AI Assistant
    </button>
    <button class="tab" data-tab="food">
      <span class="icon">🍛</span> Food Guide
    </button>
  </div>
</nav>

<div class="frames" id="frames">
  <iframe id="f-reviews"   class="active" src="/travellens/portal/index.html"></iframe>
  <iframe id="f-assistant" src=""></iframe>
  <iframe id="f-food"      src=""></iframe>
</div>

<script>
const SRCS = {
  reviews:   '/travellens/portal/index.html',
  assistant: '/ai/',
  food:      '/food/',
};
const loaded = { reviews: true, assistant: false, food: false };

document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;

    // nav
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    // frames
    document.querySelectorAll('.frames iframe').forEach(f => f.classList.remove('active'));
    const frame = document.getElementById('f-' + tab);
    frame.classList.add('active');

    // lazy load
    if (!loaded[tab]) {
      frame.src = SRCS[tab];
      loaded[tab] = true;
    }
  });
});
</script>
"""


def check(port: int) -> int:
    """Report what is reachable without starting anything."""
    import httpx
    print("\ngateway check")
    print("-" * 62)
    ok = True
    for mount, dist in SPAS.items():
        built = (dist / "index.html").exists()
        ok = ok and built
        print("  {:<8} {}".format(
            mount,
            "built" if built
            else "NOT BUILT  ->  " + BUILD_HINT[mount]))
    for name, url in UPSTREAMS.items():
        try:
            httpx.get(url + "/", timeout=3)
            print("  {:<8} up at {}".format(name, url))
        except Exception:
            print("  {:<8} NOT REACHABLE at {}".format(name, url))
    try:
        sys.path.insert(0, str(ROOT / "travellens" / "src"))
        import travellens.api  # noqa: F401
        print("  {:<8} importable (runs in this process)".format("travellens"))
    except Exception as exc:
        ok = False
        print("  {:<8} NOT importable: {}".format("travellens", exc))
    print("-" * 62)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--check", action="store_true",
                    help="report what is reachable, then exit")
    ap.add_argument("--food-api",  default=UPSTREAMS["food_api"])
    ap.add_argument("--flask",     default=UPSTREAMS["flask"])
    args = ap.parse_args()

    if args.check:
        return check(args.port)

    import uvicorn
    app = build_app({"food_api": args.food_api, "flask": args.flask})
    base = "http://{}:{}".format(
        "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host,
        args.port)
    print("\nSri Lanka Tourism — one URL, three functions")
    print("-" * 62)
    print("  {}".format(base))
    print()
    print("  {}/             TravelLens Reviews".format(base))
    print("  {}/ai/          AI Travel Assistant".format(base))
    print("  {}/food/        Food Guide".format(base))
    print("-" * 62)
    print("  travellens runs in this process.")
    print("  AI backend (Flask):   {}".format(args.flask))
    print("  food API:             {}".format(args.food_api))
    print("  Start those separately; see README.md.\n")
    sys.stdout.flush()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
