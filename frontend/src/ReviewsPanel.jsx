import { useState, useEffect, useRef } from "react";

/* ── Design tokens ───────────────────────────────────────────────────────── */
const T = {
  bg:     "#f5f7fa",
  card:   "#ffffff",
  navy:   "#0D1B2A",
  gold:   "#E8B84B",
  red:    "#B04A2F",
  muted:  "rgba(13,27,42,.48)",
  faint:  "rgba(13,27,42,.05)",
  line:   "rgba(13,27,42,.07)",
  shadow: "0 1px 3px rgba(13,27,42,.05), 0 6px 20px rgba(13,27,42,.06)",
  font:   "'Inter', system-ui, sans-serif",
};

function barColor(rate) {
  if (rate > 50) return T.red;
  if (rate > 30) return "#C8702A";
  if (rate > 15) return "#C8952A";
  return "#5A9A6A";
}

/* ── Sub-nav tabs ───────────────────────────────────────────────────────── */
const SUB_TABS = [
  { id: "map",     label: "Map",              icon: "🗺" },
  { id: "stories", label: "Stories & Videos", icon: "▶"  },
  { id: "share",   label: "Add a Review",     icon: "✏"  },
];

function SubNav({ active, onSelect }) {
  return (
    <div style={{
      display: "flex", alignItems: "stretch",
      height: 44, flexShrink: 0,
      background: T.card,
      borderBottom: `1px solid ${T.line}`,
      padding: "0 20px",
      gap: 0,
    }}>
      {SUB_TABS.map(({ id, label, icon }) => {
        const on = active === id;
        return (
          <button
            key={id}
            onClick={() => onSelect(id)}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "0 14px", height: "100%",
              border: "none",
              borderBottom: `2px solid ${on ? T.red : "transparent"}`,
              borderRadius: 0,
              background: "transparent",
              color: on ? T.navy : T.muted,
              fontSize: 13, fontWeight: on ? 600 : 500,
              cursor: "pointer",
              fontFamily: T.font,
              transition: "color 0.12s, border-color 0.12s",
            }}
          >
            <span style={{ fontSize: 12 }}>{icon}</span>
            <span>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ── Aspect bar row ─────────────────────────────────────────────────────── */
function AspectRow({ label, rate, last }) {
  return (
    <div style={{ padding: "9px 14px", borderBottom: last ? "none" : `1px solid ${T.line}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 500 }}>{label}</span>
        <span style={{ fontSize: 11, fontWeight: 700, fontVariantNumeric: "tabular-nums", color: barColor(rate) }}>
          {rate}%
        </span>
      </div>
      <div style={{ height: 4, background: T.faint, borderRadius: 2, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${rate}%`, background: barColor(rate), borderRadius: 2 }} />
      </div>
    </div>
  );
}

/* ── Stats sidebar ──────────────────────────────────────────────────────── */
function StatsSidebar({ corpus, district, onClear }) {
  const sideStyle = {
    width: 300, flexShrink: 0,
    overflowY: "auto",
    padding: "20px 16px",
    borderRight: `1px solid ${T.line}`,
    background: T.bg,
    transition: "opacity 0.15s",
  };

  /* ── District detail view ── */
  if (district) {
    const top = district.aspects[0];
    const dests = district.destinations || [];
    return (
      <div style={sideStyle}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: T.muted, margin: 0 }}>
            District
          </p>
          <button onClick={onClear} style={{ fontSize: 11, color: T.muted, background: "none", border: "none", cursor: "pointer", padding: "2px 6px", borderRadius: 4, fontFamily: T.font }}>
            ← Overview
          </button>
        </div>

        {/* Hero card */}
        <div style={{ background: T.card, borderRadius: 10, padding: "16px", marginBottom: 12, boxShadow: T.shadow }}>
          <p style={{ fontSize: 13, fontWeight: 700, margin: "0 0 2px" }}>{district.name}</p>
          <p style={{ fontSize: 11, color: T.muted, margin: "0 0 10px" }}>
            {district.n_destinations} destinations · {district.n_reviews.toLocaleString()} reviews
          </p>
          {top && (
            <>
              <span style={{ fontSize: 36, fontWeight: 800, lineHeight: 1, color: T.red, fontVariantNumeric: "tabular-nums", letterSpacing: "-.03em", display: "block", marginBottom: 2 }}>
                {top.rate.toFixed(1)}%
              </span>
              <p style={{ fontSize: 11, fontWeight: 600, color: T.red, margin: 0 }}>{top.label} — top complaint</p>
            </>
          )}
        </div>

        {/* Aspect breakdown */}
        <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: T.muted, margin: "0 0 6px" }}>
          Complaint Rate by Topic
        </p>
        <div style={{ background: T.card, borderRadius: 10, boxShadow: T.shadow, marginBottom: 12 }}>
          {district.aspects.map((a, i) => (
            <AspectRow key={a.key} label={a.label} rate={parseFloat(a.rate.toFixed(1))} last={i === district.aspects.length - 1} />
          ))}
        </div>

        {/* Top destinations */}
        {dests.length > 0 && (
          <>
            <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: T.muted, margin: "0 0 6px" }}>
              Top Destinations
            </p>
            <div style={{ background: T.card, borderRadius: 10, boxShadow: T.shadow }}>
              {dests.map((d, i) => (
                <div key={d.name} style={{ padding: "8px 14px", borderBottom: i < dests.length - 1 ? `1px solid ${T.line}` : "none" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span style={{ fontSize: 12, fontWeight: 500, flex: 1, marginRight: 8 }}>{d.name}</span>
                    <span style={{ fontSize: 10, color: T.muted, fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>{d.n_reviews} reviews</span>
                  </div>
                  {d.top_aspect && (
                    <p style={{ fontSize: 10, color: T.muted, margin: "2px 0 0" }}>
                      Top issue: {d.top_aspect} ({d.top_rate != null ? d.top_rate.toFixed(1) : "—"}%)
                    </p>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    );
  }

  /* ── Global overview (loading or loaded) ── */
  if (!corpus) {
    return (
      <div style={{ ...sideStyle, display: "flex", alignItems: "center", justifyContent: "center", color: T.muted, fontSize: 12 }}>
        Loading…
      </div>
    );
  }

  const topAspect = corpus.aspects[0];
  const worst = corpus.worst_safety_districts;

  return (
    <div style={sideStyle}>
      <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: T.muted, margin: "0 0 8px" }}>
        Key Finding
      </p>
      <div style={{ background: T.card, borderRadius: 10, padding: "18px", marginBottom: 14, boxShadow: T.shadow }}>
        <p style={{ fontSize: 11, color: T.muted, margin: "0 0 4px" }}>Most-complained-about topic</p>
        <span style={{ fontSize: 44, fontWeight: 800, lineHeight: 1, color: T.red, fontVariantNumeric: "tabular-nums", letterSpacing: "-.03em", display: "block", marginBottom: 2 }}>
          {topAspect.complaint_rate}%
        </span>
        <p style={{ fontSize: 13, fontWeight: 600, margin: "0 0 3px" }}>{topAspect.label} complaints</p>
        <p style={{ fontSize: 11, color: T.muted, margin: "0 0 14px" }}>
          {topAspect.n_negative.toLocaleString()} complaints · {topAspect.n_positive.toLocaleString()} praise
        </p>
        {worst.length > 0 && (
          <div style={{ borderTop: `1px solid ${T.line}`, paddingTop: 12 }}>
            <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: T.muted, margin: "0 0 8px" }}>
              Worst districts for safety
            </p>
            {worst.map((d, i) => (
              <div key={d.district} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 8px", marginBottom: 3, background: T.faint, borderRadius: 6, border: `1px solid ${T.line}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <span style={{ width: 17, height: 17, borderRadius: "50%", background: T.red, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, flexShrink: 0 }}>
                    {i + 1}
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 500 }}>{d.district}</span>
                </div>
                <span style={{ fontSize: 12, fontWeight: 700, color: T.red, fontVariantNumeric: "tabular-nums" }}>
                  {d.complaint_count}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
      <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: T.muted, margin: "0 0 8px" }}>
        Complaint Rate by Topic
      </p>
      <div style={{ background: T.card, borderRadius: 10, boxShadow: T.shadow, marginBottom: 12 }}>
        {corpus.aspects.map((a, i) => (
          <AspectRow key={a.key} label={a.label} rate={a.complaint_rate} last={i === corpus.aspects.length - 1} />
        ))}
      </div>
      <p style={{ fontSize: 10, color: T.muted, textAlign: "center" }}>
        {corpus.total_reviews.toLocaleString()} reviews · {corpus.destinations} destinations · {corpus.districts} districts
      </p>
    </div>
  );
}

/* ── Map view (stats sidebar + 3D map iframe) ───────────────────────────── */
function MapView({ corpusData }) {
  const [mapLoaded, setMapLoaded] = useState(false);
  const [district, setDistrict] = useState(null);
  const [mapMode, setMapMode] = useState("iso");
  const iframeRef = useRef(null);

  useEffect(() => {
    function onMessage(e) {
      if (!e.data || e.data.type !== 'travellens:district') return;
      if (e.data.district && e.data.data) {
        setDistrict({ name: e.data.district, ...e.data.data });
      } else {
        setDistrict(null);
      }
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, []);

  function switchMode(mode) {
    setMapMode(mode);
    try { iframeRef.current?.contentWindow?.postMessage({ type: 'travellens:setMode', mode }, '*'); } catch(e) {}
  }

  const btnBase = { border: "none", cursor: "pointer", fontSize: 11, fontWeight: 600, fontFamily: T.font, padding: "5px 12px", borderRadius: 5, transition: "all 0.12s" };

  return (
    <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
      <StatsSidebar corpus={corpusData} district={district} onClear={() => setDistrict(null)} />

      {/* Right: map */}
      <div style={{ flex: 1, position: "relative", background: "#FCFBF7" }}>
        {/* Flat / 3D toggle */}
        <div style={{ position: "absolute", top: 10, left: 10, zIndex: 10, display: "flex", gap: 3, background: "rgba(255,255,255,0.92)", borderRadius: 7, padding: 3, boxShadow: "0 1px 6px rgba(13,27,42,.10)", backdropFilter: "blur(4px)" }}>
          {[{ id: "flat", label: "Flat" }, { id: "iso", label: "3D" }].map(({ id, label }) => (
            <button key={id} onClick={() => switchMode(id)} style={{ ...btnBase, background: mapMode === id ? T.navy : "transparent", color: mapMode === id ? "#fff" : T.muted }}>
              {label}
            </button>
          ))}
        </div>

        {!mapLoaded && (
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, color: T.muted, fontSize: 13 }}>
            <div style={{ width: 28, height: 28, borderRadius: "50%", border: `2px solid ${T.line}`, borderTopColor: T.red, animation: "spin 0.8s linear infinite" }} />
            Loading 3D map…
          </div>
        )}
        <iframe
          ref={iframeRef}
          src="/travellens/dashboard/index.html?maponly=1"
          title="Sri Lanka 3D complaint map"
          onLoad={() => setMapLoaded(true)}
          style={{ width: "100%", height: "100%", border: "none", opacity: mapLoaded ? 1 : 0, transition: "opacity 0.3s ease" }}
        />
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      </div>
    </div>
  );
}

/* ── Portal panel iframe (stories / share) ───────────────────────────────── */
function PortalPanel({ hash }) {
  const [loaded, setLoaded] = useState(false);

  return (
    <div style={{ flex: 1, position: "relative", background: T.bg }}>
      {!loaded && (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: T.muted, fontSize: 13 }}>
          Loading…
        </div>
      )}
      <iframe
        key={hash}
        src={`/travellens/portal/index.html?embedded=1#${hash}`}
        title={hash}
        onLoad={() => setLoaded(true)}
        style={{ width: "100%", height: "100%", border: "none", opacity: loaded ? 1 : 0, transition: "opacity 0.25s ease" }}
      />
    </div>
  );
}

/* ── Root component ─────────────────────────────────────────────────────── */
export default function ReviewsPanel() {
  const [view, setView] = useState("map");
  const [corpusData, setCorpusData] = useState(null);

  useEffect(() => {
    fetch("/travellens/corpus-summary")
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(setCorpusData)
      .catch(() => {
        /* fallback to precomputed research-corpus constants when the
           server hasn't been restarted yet to serve the new endpoint */
        setCorpusData({
          total_reviews: 33993, destinations: 293, districts: 19,
          aspects: [
            { key: "safety",         label: "Safety",           complaint_rate: 69.8, n_negative: 1444,  n_positive: 626   },
            { key: "price_value",    label: "Price & Value",    complaint_rate: 50.6, n_negative: 2087,  n_positive: 2038  },
            { key: "cleanliness",    label: "Cleanliness",      complaint_rate: 41.8, n_negative: 1750,  n_positive: 2438  },
            { key: "roads_access",   label: "Roads & Access",   complaint_rate: 29.7, n_negative: 1847,  n_positive: 4381  },
            { key: "facilities",     label: "Facilities",       complaint_rate: 24.4, n_negative: 1280,  n_positive: 3970  },
            { key: "crowding_noise", label: "Crowding & Noise", complaint_rate: 15.2, n_negative: 710,   n_positive: 3965  },
            { key: "scenery_nature", label: "Scenery & Nature", complaint_rate:  8.9, n_negative: 2443,  n_positive: 25086 },
          ],
          worst_safety_districts: [
            { district: "Matale",       complaint_count: 288 },
            { district: "Badulla",      complaint_count: 184 },
            { district: "Nuwara Eliya", complaint_count: 178 },
          ],
        });
      });
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", fontFamily: T.font, color: T.navy }}>
      <SubNav active={view} onSelect={setView} />
      {view === "map"     && <MapView corpusData={corpusData}  />}
      {view === "stories" && <PortalPanel hash="stories" />}
      {view === "share"   && <PortalPanel hash="share" />}
    </div>
  );
}
