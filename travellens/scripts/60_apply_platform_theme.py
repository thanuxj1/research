"""Give the Reviews component the same look as the rest of the LostinSriLanka platform.

  python scripts/60_apply_platform_theme.py

The unified app (frontend/, served by gateway.py) has three tabs. The AI Assistant and
the Food Guide share one visual language: Inter type, slate ink on a near-white ground,
white cards with 16px corners and soft shadows, rounded controls, emerald green for
actions, and a navy (#0D1B2A) + gold (#E8B84B) brand bar. The Reviews component was
designed separately (warm paper, serif headings, monospace controls, square corners,
a charcoal masthead), so inside the app it read as a different product.

This rewrites the pages in place, idempotently:
  1. a token block (between /* platform-theme */ markers) appended to the page's main
     stylesheet, so every rule written against var(--...) picks up the platform values;
  2. corner radii on cards and controls (not on bars, ramps or scrollbars, where a
     rounded end would distort the data);
  3. the Inter weights the headings need.
The map's complaint ramp is data colour and is deliberately left alone.

Applied to the built pages AND their templates, so a rebuild keeps the look.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "portal" / "index.html", ROOT / "portal" / "template.html",
         ROOT / "dashboard" / "index.html", ROOT / "dashboard" / "template.html"]
START, END = "/* platform-theme:start */", "/* platform-theme:end */"

THEME = START + """
/* Shared with the AI Assistant and Food Guide tabs -- see scripts/60_apply_platform_theme.py */
:root {
  --paper: #F8FAFC; --ground: #F8FAFC; --surface: #FFFFFF; --surface-2: #F1F5F9;
  --line: #E2E8F0; --line-soft: #EEF2F6;
  --ink: #0F172A; --ink-muted: #475569; --ink-faint: #64748B;
  --accent: #059669; --accent-soft: #ECFDF5; --accent-fill: #059669;
  --accent-on-fill: #FFFFFF; --accent-text: #047857;
  --good: #047857; --good-soft: #ECFDF5;
  --brand-ink: #0D1B2A; --brand-ink2: #0D1B2A; --brand-gold: #E8B84B;
  --f-display: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  --f-body:    "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  --f-mono:    "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  --shadow: 0 1px 2px rgba(15,23,42,.04), 0 6px 20px rgba(15,23,42,.06);
}
:root[data-theme="dark"] {
  --paper: #0B1220; --ground: #0B1220; --surface: #111A2B; --surface-2: #1A2538;
  --line: #26324A; --line-soft: #1E2A3E;
  --ink: #F1F5F9; --ink-muted: #A7B3C6; --ink-faint: #8391A7;
  --accent: #34D399; --accent-soft: rgba(52,211,153,.14); --accent-fill: #34D399;
  --accent-on-fill: #06281D; --accent-text: #6EE7B7;
  --good: #34D399; --good-soft: rgba(52,211,153,.14);
}
body { font-feature-settings: "cv11", "ss01"; }
h1, h2, h3, .brand, .lede, .an-num { letter-spacing: -.02em; }
h1, h2, .brand, .an-num { font-weight: 800 !important; }
h3 { font-weight: 700; }
td.num, .counter, .an-td-num, [class*="pct"], [class*="-num"] { font-variant-numeric: tabular-nums; }
button, select, input, textarea { font-family: var(--f-body); }
button { transition: background .15s, color .15s, border-color .15s, box-shadow .15s; }

/* masthead = the platform's navy bar with the gold "in" */
.masthead { background: var(--brand-ink) !important; }
.tab[aria-selected="true"] { color: var(--brand-gold) !important; border-bottom-color: var(--brand-gold) !important; }

/* Inside the platform the navy bar is already on screen; the second dark band is
   replaced by a light sub-navigation with pill tabs, like the Food Guide header. */
html.embedded .masthead {
  background: var(--surface) !important; padding: 10px 0 !important; margin-bottom: 24px !important;
  border-bottom: 1px solid var(--line); box-shadow: 0 1px 2px rgba(15,23,42,.03);
}
html.embedded .tabs {
  margin-top: 0 !important; gap: 4px; width: fit-content; padding: 4px !important;
  background: var(--surface-2); border: 1px solid var(--line); border-radius: 12px;
  max-width: none; margin-left: max(24px, calc((100% - 1040px) / 2 + 24px)) !important;
}
html.embedded .tab {
  color: var(--ink-muted) !important; border-bottom: 0 !important; border-radius: 9px !important;
  padding: 7px 16px !important; font-size: 13.5px; font-weight: 600;
}
html.embedded .tab:hover { color: var(--ink) !important; background: rgba(15,23,42,.04); }
/* ---- Map first. The Map tab used to spend ~330px on two stacked intros (the
   portal's sentence, then the dashboard's 44px title, deck and evidence note)
   before the map began, so the map was cut off inside its frame. Now the
   portal's sentence is dropped on that tab, the frame loses its card border,
   and inside the frame the dashboard header collapses to one compact line
   (the evidence note stays, small, because it is a statement of scope). The
   map and its panel then fill the frame, which is sized to the window. */
#panel-map > .lede, #panel-map > .sub { display: none !important; }
.frame-wrap { border: 0 !important; border-radius: 0 !important; background: transparent !important;
  box-shadow: none !important; overflow: visible !important; }
:root[data-framed="true"] .wrap { padding-top: 6px !important; }
:root[data-framed="true"] .view-head {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 14px; margin: 0 0 12px !important; }
:root[data-framed="true"] h2.view-title, :root[data-framed="true"] .view-title {
  font-size: 22px !important; margin: 0 !important; line-height: 1.2; }
:root[data-framed="true"] .view-deck { margin: 0 !important; font-size: 13.5px; color: var(--ink-muted); }
:root[data-framed="true"] .view-deck, :root[data-framed="true"] .evidence-note { max-width: none !important; }
:root[data-framed="true"] .map-head { margin-bottom: 8px !important; }
:root[data-framed="true"] .map-head .section-title { font-size: 18px !important; }
/* the map is sized from the window, less the header, toolbar and card padding
   above and below it, so the whole island is on screen without scrolling */
:root[data-framed="true"] .map-svg {
  width: min(100%, max(240px, calc(min(100vh - 190px, 700px) * 0.5957))) !important; }
:root[data-framed="true"] .view-head .evidence-note {
  flex-basis: 100%; margin: 2px 0 0 !important; padding: 0 !important; border: 0 !important;
  font-size: 12px; color: var(--ink-faint); }

/* ---- Map tab as a dashboard screen: the frame spans the window (16px gutters)
   so the dashboard's two-column layout engages -- map + its controls on the
   left, the findings panel (headline, worst districts, every topic) on the
   right -- instead of the findings sitting below the fold. */
#panel-map .frame-wrap { width: calc(100vw - 32px); margin-left: calc(50% - 50vw + 16px); }
:root[data-framed="true"] .wrap { max-width: 1680px !important; padding: 0 16px 12px !important; }
:root[data-framed="true"] .view-head .evidence-note { flex-basis: auto !important; margin: 0 !important; }
:root[data-framed="true"] .view-head .evidence-note::before { content: "·  "; }
@media (min-width: 1080px) {
  :root[data-framed="true"] .bento { column-gap: 32px !important; }
  :root[data-framed="true"] .bento-hero .map-shell:not(.is-3d) {
    grid-template-columns: auto minmax(180px, 230px) !important; align-items: start; gap: 24px; }
  :root[data-framed="true"] .bento-hero .map-shell:not(.is-3d) .map-side {
    display: flex !important; flex-direction: column; gap: 14px;
    margin-top: 0 !important; padding-top: 0 !important; border-top: 0 !important;
    align-items: stretch !important; }
  :root[data-framed="true"] .bento-hero .map-shell:not(.is-3d) .map-side > *,
  :root[data-framed="true"] .bento-hero .map-side select { width: 100%; box-sizing: border-box; }
  /* 3D is a landscape figure: full card width, controls as a compact band below */
  :root[data-framed="true"] .bento-hero .map-shell.is-3d { grid-template-columns: minmax(0, 1fr) !important; }
  :root[data-framed="true"] .bento:has(.map-shell.is-3d) { grid-template-columns: minmax(0, 1.9fr) minmax(0, 1fr) !important; }
  :root[data-framed="true"] .map-shell.is-3d .map-side {
    grid-template-columns: minmax(160px, 220px) 1fr !important; gap: 10px 24px !important;
    margin-top: 10px !important; padding-top: 10px !important; }
}

/* legend keys read as sentences, not shouted labels */
.map3d-legend .key, .scale-ends span { text-transform: none !important; letter-spacing: 0 !important;
  font-size: 12.5px !important; color: var(--ink-muted); }
.map3d-legend { gap: 6px 20px !important; }

html.embedded .tab[aria-selected="true"] {
  color: #FFFFFF !important; background: var(--accent-fill) !important;
  box-shadow: 0 1px 2px rgba(5,150,105,.25);
}
""" + END

# rules whose rounded corners would misread as data (bars, ramps) or are tiny UI chrome
KEEP = re.compile(r"bar|track|scale|ramp|scrollbar|swatch|focus|legend|spark|cell|tick|dot", re.I)


def radius_rule(sel: str, body: str) -> str:
    m = re.search(r"border-radius:\s*([234])px", body)
    if not m or KEEP.search(sel):
        return body
    pad = [int(x) for x in re.findall(r"padding:\s*(\d+)px", body)]
    if "cursor: pointer" in body or re.search(r"\b(button|select|input|textarea)\b|btn|toggle|mode|view|pill|tab", sel):
        r = 10
    elif pad and max(pad) >= 10:
        r = 16
    else:
        r = 6
    body = re.sub(r"border-radius:\s*[234]px", "border-radius: %dpx" % r, body)
    if r == 16 and "box-shadow" not in body:
        body = body.rstrip() + " box-shadow: var(--shadow);"
    return body


def restyle_css(css: str) -> str:
    return re.sub(r"([^{}]+)\{([^{}]*)\}", lambda m: m.group(1) + "{" + radius_rule(m.group(1), m.group(2)) + "}", css)


def apply(path: Path) -> str:
    s = path.read_text(encoding="utf8")
    s = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", s, flags=re.S)   # idempotent
    # the main stylesheet is the first <style> block
    a = s.index("<style>") + len("<style>")
    b = s.index("</style>", a)
    css = restyle_css(s[a:b]).rstrip() + "\n\n" + THEME + "\n"
    # mark embedded pages before first paint so the sub-navigation styles apply at once
    # (these pages have no explicit <head>, so the flag goes straight after the stylesheet)
    flag = ("\n<script>/* platform-theme */if(new URLSearchParams(location.search).get('embedded')==='1'"
            "||window.top!==window.self)document.documentElement.classList.add('embedded');</script>")
    s = s.replace(flag, "")
    s = s[:a] + css + "</style>" + flag + s[b + len("</style>"):]
    s = s.replace("family=Inter:wght@400;500;600&", "family=Inter:wght@400;500;600;700;800&")
    path.write_text(s, encoding="utf8")
    return "%s: %d bytes" % (path.relative_to(ROOT), len(s))


if __name__ == "__main__":
    for f in FILES:
        print(apply(f))
