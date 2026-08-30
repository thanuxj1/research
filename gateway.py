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

    # ----------------------------------------- AI SPA images (before SPAs)
    _images_dir = ROOT / "frontend" / "dist" / "images"
    if _images_dir.exists():
        app.mount("/images", StaticFiles(directory=str(_images_dir)), name="images")

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
<title>LostinSriLanka</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden;background:#08111A;
  font-family:'Inter',system-ui,sans-serif;-webkit-font-smoothing:antialiased}

/* ── Cover ──────────────────────────────────────────── */
#cover{
  position:fixed;inset:0;z-index:200;
  display:flex;align-items:center;justify-content:center;
  transition:opacity .45s ease;
}
#cover-bg{position:absolute;inset:0;width:100%;height:100%}
.cover-body{
  position:relative;z-index:1;
  text-align:center;
  display:flex;flex-direction:column;align-items:center;gap:20px;
}
.c-wordmark{
  font-size:clamp(44px,9vw,96px);
  font-weight:800;letter-spacing:-.035em;color:#EFF7F2;line-height:1;
}
.c-wordmark .gold{color:#E8B84B}
.c-sub{
  font-size:clamp(10px,1.4vw,12px);letter-spacing:.18em;text-transform:uppercase;
  color:rgba(239,247,242,.38);
}
.c-stats{
  display:flex;gap:24px;
  color:rgba(239,247,242,.48);font-size:12.5px;
}
.c-stats b{color:#E8B84B;font-weight:600}
#enter-btn{
  margin-top:6px;display:flex;align-items:center;gap:10px;
  padding:14px 32px;
  background:#E8B84B;color:#08111A;
  border:none;border-radius:6px;
  font:700 14px/1 'Inter',system-ui,sans-serif;
  cursor:pointer;letter-spacing:.01em;
  transition:transform .15s,box-shadow .15s;
}
#enter-btn:hover{transform:translateY(-2px);box-shadow:0 12px 30px rgba(232,184,75,.42)}

/* ── Platform ───────────────────────────────────────── */
#platform{
  display:none;flex-direction:column;height:100%;
  opacity:0;transition:opacity .3s ease;
}
.p-nav{
  height:50px;flex-shrink:0;
  display:flex;align-items:center;padding:0 20px;gap:0;
  background:#0D1B2A;
  border-bottom:1px solid rgba(239,247,242,.07);
}
.p-brand{
  font-size:15px;font-weight:800;letter-spacing:-.02em;
  color:#EFF7F2;margin-right:32px;white-space:nowrap;flex-shrink:0;
}
.p-brand .gold{color:#E8B84B}
.p-tabs{display:flex;height:100%;gap:2px}
.p-tab{
  display:flex;align-items:center;gap:7px;
  padding:0 16px;height:100%;
  background:none;border:none;border-bottom:3px solid transparent;
  color:rgba(239,247,242,.50);
  font:500 13px/1 'Inter',system-ui,sans-serif;
  cursor:pointer;white-space:nowrap;
  transition:color .12s,background .12s,border-color .12s;
}
.p-tab:hover{color:rgba(239,247,242,.85);background:rgba(255,255,255,.05)}
.p-tab.active{color:#E8B84B;border-bottom-color:#E8B84B;font-weight:600;background:rgba(232,184,75,.08)}

/* ── Frames ─────────────────────────────────────────── */
.frames{flex:1;position:relative;overflow:hidden}
.frames iframe{
  position:absolute;inset:0;width:100%;height:100%;
  border:none;display:none;
}
.frames iframe.active{display:block}
</style>

<!-- Cover -->
<div id="cover">
  <canvas id="cover-bg"></canvas>
  <div class="cover-body">
    <div class="c-wordmark">Lost<span class="gold">in</span>SriLanka</div>
    <p class="c-sub">AI Powered Smart Tourism Ecosystem</p>
    <div class="c-stats">
      <span><b>46,854</b> reviews</span>
      <span><b>293</b> destinations</span>
      <span><b>19</b> districts</span>
    </div>
    <button id="enter-btn">Enter Platform &nbsp;&#8594;</button>
  </div>
</div>

<!-- Platform -->
<div id="platform">
  <nav class="p-nav">
    <div class="p-brand">Lost<span class="gold">in</span>SriLanka</div>
    <div class="p-tabs">
      <button class="p-tab active" data-tab="reviews">&#128506; Reviews</button>
      <button class="p-tab" data-tab="assistant">&#10024; AI Assistant</button>
      <button class="p-tab" data-tab="food">&#127835; Food Guide</button>
    </div>
  </nav>
  <div class="frames" id="frames">
    <iframe id="f-reviews"   class="active" src="/travellens/portal/index.html?embedded=1"></iframe>
    <iframe id="f-assistant" src=""></iframe>
    <iframe id="f-food"      src=""></iframe>
  </div>
</div>

<script>
// ── Canvas background ─────────────────────────────────
(function(){
  var c=document.getElementById('cover-bg'),x=c.getContext('2d');
  var W,H,t=0,raf;
  function resize(){W=c.width=innerWidth;H=c.height=innerHeight}
  function draw(){
    x.clearRect(0,0,W,H);
    var d1=Math.sin(t*.00028),d2=Math.cos(t*.00021);
    var bg=x.createLinearGradient(0,0,W*.7,H);
    bg.addColorStop(0,'#0D2236');bg.addColorStop(.55,'#081420');bg.addColorStop(1,'#050E16');
    x.fillStyle=bg;x.fillRect(0,0,W,H);
    // teal orb
    x.save();x.translate(W*(.65+d1*.012),H*(.30+d2*.010));
    var g1=x.createRadialGradient(-W*.08,-H*.09,0,0,0,W*.46);
    g1.addColorStop(0,'rgba(52,211,153,.55)');g1.addColorStop(.38,'rgba(16,133,96,.40)');
    g1.addColorStop(.72,'rgba(8,80,56,.28)');g1.addColorStop(1,'rgba(0,0,0,0)');
    x.fillStyle=g1;x.beginPath();
    x.ellipse(0,0,W*.40,H*.50,-.22+d1*.018,0,Math.PI*2);x.fill();x.restore();
    // gold orb
    x.save();x.translate(W*(.18+d2*.010),H*(.72+d1*.009));
    var g2=x.createRadialGradient(0,0,0,0,0,W*.28);
    g2.addColorStop(0,'rgba(232,184,75,.26)');g2.addColorStop(.5,'rgba(180,130,40,.10)');
    g2.addColorStop(1,'rgba(0,0,0,0)');
    x.fillStyle=g2;x.beginPath();
    x.ellipse(0,0,W*.24,H*.28,.3+d2*.014,0,Math.PI*2);x.fill();x.restore();
    // vignette
    var vig=x.createRadialGradient(W*.5,H*.5,H*.18,W*.5,H*.5,H*.85);
    vig.addColorStop(0,'rgba(0,0,0,0)');vig.addColorStop(1,'rgba(0,0,0,.58)');
    x.fillStyle=vig;x.fillRect(0,0,W,H);
    t++;raf=requestAnimationFrame(draw);
  }
  resize();window.addEventListener('resize',resize);
  if(window.matchMedia('(prefers-reduced-motion:reduce)').matches){t=60;x.clearRect(0,0,1,1);resize();draw();cancelAnimationFrame(raf);}
  else draw();
})();

// ── Enter Platform ────────────────────────────────────
document.getElementById('enter-btn').addEventListener('click',function(){
  var cover=document.getElementById('cover');
  var plat=document.getElementById('platform');
  cover.style.opacity='0';
  setTimeout(function(){
    cover.style.display='none';
    plat.style.display='flex';
    plat.offsetHeight;
    plat.style.opacity='1';
  },450);
});

// ── Tabs ──────────────────────────────────────────────
var SRCS={reviews:'/travellens/portal/index.html?embedded=1',assistant:'/ai/',food:'/food/'};
var loaded={reviews:true,assistant:false,food:false};
document.querySelectorAll('.p-tab').forEach(function(btn){
  btn.addEventListener('click',function(){
    var tab=btn.dataset.tab;
    document.querySelectorAll('.p-tab').forEach(function(b){b.classList.remove('active')});
    btn.classList.add('active');
    document.querySelectorAll('.frames iframe').forEach(function(f){f.classList.remove('active')});
    var frame=document.getElementById('f-'+tab);
    frame.classList.add('active');
    if(!loaded[tab]){frame.src=SRCS[tab];loaded[tab]=true;}
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
