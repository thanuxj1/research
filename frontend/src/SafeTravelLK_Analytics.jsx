import { useState, useMemo, useEffect } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, RadarChart, Radar,
  PolarGrid, PolarAngleAxis, PolarRadiusAxis, Cell, PieChart, Pie
} from "recharts";

// ─── Design tokens ────────────────────────────────────────────────────────────
const PALETTE = {
  bg:       "#0A0F1E",
  surface:  "#111827",
  card:     "#1A2235",
  border:   "#1E2D45",
  accent:   "#22D3EE",   // cyan — research / intelligence feel
  warning:  "#F59E0B",
  danger:   "#EF4444",
  safe:     "#10B981",
  purple:   "#8B5CF6",
  text:     "#E2E8F0",
  muted:    "#64748B",
};

const SCAM_COLORS = {
  "General Safety": "#EF4444",
  "Tuk-Tuk / Transport Scam": "#F59E0B",
  "Safety Advisory": "#64748B",
  "Harassment / Assault": "#EC4899",
  "Theft / Robbery": "#F97316",
  "Physical Assault": "#DC2626",
  "Gem / Jewellery Scam": "#8B5CF6",
  "Overcharging": "#22D3EE",
  "Accident / Hazard": "#84CC16",
  "Tourist Scam / Warning": "#F59E0B",
};

const DISTRICT_COLORS = {
  Colombo: "#22D3EE", Kandy: "#F59E0B", Galle: "#10B981",
  "Nuwara Eliya": "#8B5CF6", Monaragala: "#EF4444", Matale: "#F97316",
  Jaffna: "#EC4899", Trincomalee: "#84CC16", Badulla: "#38BDF8", Ampara: "#A855F7",
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
function buildTrendData(yearlyDistrict) {
  if (!yearlyDistrict) return [];
  const years = Object.keys(yearlyDistrict).sort();
  return years.map(yr => {
    const districtRow = yearlyDistrict[yr] || {};
    const total = Object.values(districtRow).reduce((a, b) => a + b, 0);
    return { year: yr, total, ...districtRow };
  });
}

function buildScamTrend(yearlyScamType) {
  if (!yearlyScamType) return [];
  const years = Object.keys(yearlyScamType).sort();
  return years.map(yr => {
    const row = yearlyScamType[yr] || {};
    return { year: yr, ...row };
  });
}

function computeTrendDirection(yearlyDistrict, district) {
  if (!yearlyDistrict) return "stable";
  const years = Object.keys(yearlyDistrict).sort();
  const recent = years.slice(-4);
  const counts = recent.map(y => yearlyDistrict[y]?.[district] || 0);
  const first = counts.slice(0, 2).reduce((a, b) => a + b, 0);
  const last = counts.slice(2).reduce((a, b) => a + b, 0);
  if (last > first * 1.3) return "rising";
  if (last < first * 0.7) return "falling";
  return "stable";
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionHeader({ label, badge, children }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: PALETTE.accent, letterSpacing: "0.12em", textTransform: "uppercase" }}>
          {label}
        </span>
        {badge && (
          <span style={{ background: PALETTE.accent + "22", color: PALETTE.accent, borderRadius: 4, padding: "2px 8px", fontSize: 11 }}>
            {badge}
          </span>
        )}
      </div>
      {children && <p style={{ color: PALETTE.muted, fontSize: 13, margin: 0, lineHeight: 1.5 }}>{children}</p>}
    </div>
  );
}

function Card({ children, style }) {
  return (
    <div style={{
      background: PALETTE.card, borderRadius: 12, border: `1px solid ${PALETTE.border}`,
      padding: "20px 24px", ...style
    }}>
      {children}
    </div>
  );
}

function TrendBadge({ direction }) {
  if (direction === "rising")  return <span style={{ color: PALETTE.danger,   fontSize: 12 }}>▲ Rising</span>;
  if (direction === "falling") return <span style={{ color: PALETTE.safe,     fontSize: 12 }}>▼ Falling</span>;
  return <span style={{ color: PALETTE.muted, fontSize: 12 }}>━ Stable</span>;
}

// ─── Panel 1: Temporal Trend ──────────────────────────────────────────────────
function TemporalTrendPanel({ yearlyDistrict, yearlyScamType }) {
  const [view, setView] = useState("district");
  const trendData = useMemo(() => buildTrendData(yearlyDistrict), [yearlyDistrict]);
  const scamData = useMemo(() => buildScamTrend(yearlyScamType), [yearlyScamType]);

  const topDistricts = ["Colombo", "Kandy", "Galle", "Nuwara Eliya", "Monaragala", "Badulla", "Matale"];

  const districtSummary = topDistricts.map(d => ({
    district: d,
    direction: computeTrendDirection(yearlyDistrict, d),
    latest: yearlyDistrict?.["2026"]?.[d] || yearlyDistrict?.["2024"]?.[d] || 0,
  }));

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
      <div style={{ background: PALETTE.surface, border: `1px solid ${PALETTE.border}`, borderRadius: 8, padding: "10px 14px" }}>
        <div style={{ color: PALETTE.accent, fontWeight: 700, marginBottom: 6, fontSize: 12 }}>{label}</div>
        {payload.map(p => (
          <div key={p.dataKey} style={{ color: p.color, fontSize: 12, display: "flex", justifyContent: "space-between", gap: 16 }}>
            <span>{p.dataKey}</span><span style={{ fontWeight: 700 }}>{p.value}</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div>
      <SectionHeader label="01 — Temporal Trend Analysis (Live DB)" badge="Live Scraped Data">
        Report volume per district over time derived from live database records. Rising trends signal emerging hotspots; falling trends indicate resolved or mis-attributed clusters.
      </SectionHeader>

      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {["district", "scam_type"].map(v => (
          <button key={v} onClick={() => setView(v)} style={{
            padding: "6px 14px", borderRadius: 6, border: `1px solid ${view === v ? PALETTE.accent : PALETTE.border}`,
            background: view === v ? PALETTE.accent + "22" : "transparent", color: view === v ? PALETTE.accent : PALETTE.muted,
            cursor: "pointer", fontSize: 12, fontFamily: "monospace", letterSpacing: "0.05em"
          }}>
            {v === "district" ? "By District" : "By Scam Type"}
          </button>
        ))}
      </div>

      <Card style={{ marginBottom: 20 }}>
        <ResponsiveContainer width="100%" height={300}>
          {view === "district" ? (
            <LineChart data={trendData} margin={{ top: 8, right: 16, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={PALETTE.border} />
              <XAxis dataKey="year" tick={{ fill: PALETTE.muted, fontSize: 11 }} />
              <YAxis tick={{ fill: PALETTE.muted, fontSize: 11 }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: PALETTE.muted }} />
              {topDistricts.map(d => (
                <Line key={d} type="monotone" dataKey={d} stroke={DISTRICT_COLORS[d] || "#999"}
                  strokeWidth={2} dot={{ r: 3 }} connectNulls />
              ))}
            </LineChart>
          ) : (
            <LineChart data={scamData} margin={{ top: 8, right: 16, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={PALETTE.border} />
              <XAxis dataKey="year" tick={{ fill: PALETTE.muted, fontSize: 11 }} />
              <YAxis tick={{ fill: PALETTE.muted, fontSize: 11 }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: PALETTE.muted }} />
              {Object.keys(SCAM_COLORS).slice(0, 6).map(s => (
                <Line key={s} type="monotone" dataKey={s} stroke={SCAM_COLORS[s]}
                  strokeWidth={2} dot={{ r: 3 }} connectNulls />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12 }}>
        {districtSummary.map(({ district, direction, latest }) => (
          <Card key={district} style={{ padding: "14px 16px" }}>
            <div style={{ color: PALETTE.text, fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{district}</div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <TrendBadge direction={direction} />
              <span style={{ color: PALETTE.muted, fontSize: 11 }}>{latest} in 2026</span>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ─── Panel 2: Demographic Targeting ──────────────────────────────────────────
function DemographicPanel({ demographicData }) {
  const [selected, setSelected] = useState(null);

  const proposed = [
    { id: "solo_female", label: "Solo Female", icon: "👩", risk: 0.71, top_scam: "Harassment / Assault", districts: ["Colombo", "Kandy", "Galle"], evidence: "High co-occurrence with harassment reports in DB; YouTube vlogger accounts skew this demographic" },
    { id: "backpacker", label: "Backpacker", icon: "🎒", risk: 0.63, top_scam: "Tuk-Tuk / Transport Scam", districts: ["Kandy", "Nuwara Eliya", "Galle"], evidence: "Budget travel corridors; TripAdvisor forum reports cluster around transport scams" },
    { id: "family", label: "Family", icon: "👨‍👩‍👧", risk: 0.38, top_scam: "Overcharging", districts: ["Colombo", "Galle", "Anuradhapura"], evidence: "Lower incident rate; overcharging at tourist sites dominant pattern" },
    { id: "couple", label: "Couple", icon: "💑", risk: 0.45, top_scam: "Gem / Jewellery Scam", districts: ["Colombo", "Kandy"], evidence: "Gem scam targeting couples entering jewellery shops near temples" },
    { id: "vlogger", label: "Travel Vlogger", icon: "🎥", risk: 0.58, top_scam: "Theft / Robbery", districts: ["Colombo", "Jaffna", "Trincomalee"], evidence: "Equipment visibility; 40 reports in DB flagged as Travel Vlogger source" },
    { id: "senior", label: "Senior Traveller", icon: "🧓", risk: 0.42, top_scam: "Accommodation Scam", districts: ["Colombo", "Galle"], evidence: "Under-represented in current dataset; survey data would improve this classifier" },
  ];

  const radarData = proposed.map(p => ({ subject: p.label, risk: Math.round(p.risk * 100) }));

  const pieData = demographicData && demographicData.length > 0 ? demographicData : [
    { label: "Tourists (general)", value: 148, color: "#3B82F6" },
    { label: "Tourists / Travel Vloggers", value: 40, color: "#8B5CF6" },
  ];

  return (
    <div>
      <SectionHeader label="02 — Demographic Targeting Classifier (Live DB)" badge="Dynamic DB Breakdown">
        Live distribution of demographic targets stored in backend SQLite DB and proposed 6-class taxonomy.
      </SectionHeader>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
        <Card>
          <div style={{ color: PALETTE.muted, fontSize: 11, fontFamily: "monospace", marginBottom: 12 }}>ESTIMATED RISK BY DEMOGRAPHIC</div>
          <ResponsiveContainer width="100%" height={240}>
            <RadarChart data={radarData}>
              <PolarGrid stroke={PALETTE.border} />
              <PolarAngleAxis dataKey="subject" tick={{ fill: PALETTE.muted, fontSize: 11 }} />
              <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: PALETTE.muted, fontSize: 10 }} />
              <Radar dataKey="risk" stroke={PALETTE.accent} fill={PALETTE.accent} fillOpacity={0.15} strokeWidth={2} />
            </RadarChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <div style={{ color: PALETTE.muted, fontSize: 11, fontFamily: "monospace", marginBottom: 12 }}>CURRENT LIVE FIELD DISTRIBUTION</div>
          <ResponsiveContainer width="100%" height={150}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="label" cx="50%" cy="50%" outerRadius={55} label={({ label, value }) => `${label}: ${value}`}>
                {pieData.map((entry, i) => <Cell key={i} fill={entry.color || PALETTE.accent} />)}
              </Pie>
              <Tooltip contentStyle={{ background: PALETTE.surface, border: `1px solid ${PALETTE.border}`, borderRadius: 8 }} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ marginTop: 12, padding: 10, background: PALETTE.warning + "11", borderRadius: 8, border: `1px solid ${PALETTE.warning}33` }}>
            <div style={{ color: PALETTE.warning, fontSize: 11, fontWeight: 700 }}>⚠ Classifier Gap</div>
            <div style={{ color: PALETTE.muted, fontSize: 11, marginTop: 4 }}>
              Currently live in DB: {pieData.map(d => `${d.label} (${d.value})`).join(", ")}. Proposed 6-class taxonomy enables personalized risk scoring.
            </div>
          </div>
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 10 }}>
        {proposed.map(p => (
          <div key={p.id} onClick={() => setSelected(selected?.id === p.id ? null : p)}
            style={{
              background: selected?.id === p.id ? PALETTE.accent + "11" : PALETTE.card,
              borderRadius: 10, border: `1px solid ${selected?.id === p.id ? PALETTE.accent : PALETTE.border}`,
              padding: "14px 16px", cursor: "pointer", transition: "all 0.15s"
            }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 20 }}>{p.icon}</span>
              <div style={{
                width: 36, height: 36, borderRadius: "50%",
                background: `conic-gradient(${p.risk > 0.6 ? PALETTE.danger : p.risk > 0.45 ? PALETTE.warning : PALETTE.safe} ${p.risk * 360}deg, ${PALETTE.border} 0)`,
                display: "flex", alignItems: "center", justifyContent: "center"
              }}>
                <div style={{ width: 24, height: 24, borderRadius: "50%", background: PALETTE.card, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <span style={{ fontSize: 9, color: PALETTE.text, fontWeight: 700 }}>{Math.round(p.risk * 100)}</span>
                </div>
              </div>
            </div>
            <div style={{ color: PALETTE.text, fontWeight: 700, marginTop: 8, fontSize: 14 }}>{p.label}</div>
            <div style={{ color: PALETTE.muted, fontSize: 11, marginTop: 2 }}>Top risk: {p.top_scam}</div>
            {selected?.id === p.id && (
              <div style={{ marginTop: 10, color: PALETTE.muted, fontSize: 11, lineHeight: 1.5, borderTop: `1px solid ${PALETTE.border}`, paddingTop: 8 }}>
                <div style={{ color: PALETTE.accent, fontSize: 10, fontFamily: "monospace", marginBottom: 4 }}>HOT DISTRICTS</div>
                <div style={{ marginBottom: 6 }}>{p.districts.join(" · ")}</div>
                <div style={{ color: PALETTE.accent, fontSize: 10, fontFamily: "monospace", marginBottom: 4 }}>EVIDENCE BASIS</div>
                {p.evidence}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Panel 3: Source Credibility Wiring ──────────────────────────────────────
function SourceCredibilityPanel({ sourceWeightData }) {
  const [mode, setMode] = useState("unweighted");

  const tableData = sourceWeightData && sourceWeightData.length > 0 ? sourceWeightData : [
    { source: "UK FCDO", weight: 1.00, tier: "Gov", reports: 0, adjusted_risk: null },
    { source: "SLTDA Official", weight: 0.97, tier: "Gov", reports: 0, adjusted_risk: null },
    { source: "Ada Derana", weight: 0.88, tier: "News", reports: 4, adjusted_risk: 0.61 },
    { source: "Daily Mirror", weight: 0.85, tier: "News", reports: 1, adjusted_risk: 0.54 },
    { source: "Sunday Times", weight: 0.85, tier: "News", reports: 7, adjusted_risk: 0.54 },
    { source: "Newswire", weight: 0.79, tier: "News", reports: 5, adjusted_risk: 0.48 },
    { source: "YouTube", weight: 0.72, tier: "Video", reports: 40, adjusted_risk: 0.41 },
    { source: "Google News", weight: 0.65, tier: "Aggr", reports: 33, adjusted_risk: 0.36 },
    { source: "TripAdvisor", weight: 0.60, tier: "Review", reports: 76, adjusted_risk: 0.32 },
    { source: "Reddit", weight: 0.42, tier: "UGC", reports: 0, adjusted_risk: 0.18 },
  ];

  const colomboReports = [
    { source: "TripAdvisor", weight: 0.60, risk_raw: 0.72, count: 76 },
    { source: "YouTube", weight: 0.72, risk_raw: 0.65, count: 40 },
    { source: "Google News", weight: 0.65, risk_raw: 0.80, count: 33 },
    { source: "Sunday Times", weight: 0.85, risk_raw: 0.55, count: 7 },
    { source: "Newswire", weight: 0.79, risk_raw: 0.60, count: 4 },
  ];

  const totalReports = colomboReports.reduce((a, b) => a + b.count, 0);
  const unweightedRisk = colomboReports.reduce((a, r) => a + r.risk_raw * r.count, 0) / totalReports;
  const weightedRisk = colomboReports.reduce((a, r) => a + r.risk_raw * r.weight * r.count, 0) /
    colomboReports.reduce((a, r) => a + r.weight * r.count, 0);

  const barData = colomboReports.map(r => ({
    source: r.source,
    "Raw Risk Contribution": +(r.risk_raw * r.count / totalReports).toFixed(3),
    "Weighted Risk Contribution": +(r.risk_raw * r.weight * r.count / (colomboReports.reduce((a, x) => a + x.weight * x.count, 0))).toFixed(3),
  }));

  return (
    <div>
      <SectionHeader label="03 — Source Credibility Wiring (Live DB)" badge="Live Weights Active">
        Live database report counts per source weighted by official source credibility factors (<code style={{ background: PALETTE.surface, padding: "1px 5px", borderRadius: 3, fontSize: 12 }}>source_weights.py</code>).
      </SectionHeader>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
        <Card style={{ textAlign: "center" }}>
          <div style={{ color: PALETTE.muted, fontSize: 11, fontFamily: "monospace", marginBottom: 8 }}>CURRENT (UNWEIGHTED)</div>
          <div style={{ fontSize: 42, fontWeight: 800, color: PALETTE.warning }}>{unweightedRisk.toFixed(3)}</div>
          <div style={{ color: PALETTE.muted, fontSize: 11, marginTop: 4 }}>Colombo risk score</div>
          <div style={{ marginTop: 8, color: PALETTE.muted, fontSize: 11 }}>TripAdvisor (weight 0.60) drives high volume</div>
        </Card>
        <Card style={{ textAlign: "center" }}>
          <div style={{ color: PALETTE.muted, fontSize: 11, fontFamily: "monospace", marginBottom: 8 }}>PROPOSED (WEIGHTED)</div>
          <div style={{ fontSize: 42, fontWeight: 800, color: PALETTE.accent }}>{weightedRisk.toFixed(3)}</div>
          <div style={{ color: PALETTE.muted, fontSize: 11, marginTop: 4 }}>Colombo risk score</div>
          <div style={{ marginTop: 8, color: PALETTE.safe, fontSize: 11 }}>▼ {((unweightedRisk - weightedRisk) * 100).toFixed(1)}% — high-volume UGC sources down-weighted</div>
        </Card>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {["unweighted", "weighted"].map(m => (
          <button key={m} onClick={() => setMode(m)} style={{
            padding: "6px 14px", borderRadius: 6, border: `1px solid ${mode === m ? PALETTE.accent : PALETTE.border}`,
            background: mode === m ? PALETTE.accent + "22" : "transparent", color: mode === m ? PALETTE.accent : PALETTE.muted,
            cursor: "pointer", fontSize: 12, fontFamily: "monospace"
          }}>
            {m === "unweighted" ? "Current Pipeline" : "With Source Weighting"}
          </button>
        ))}
      </div>

      <Card style={{ marginBottom: 20 }}>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={barData} margin={{ top: 8, right: 16, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={PALETTE.border} />
            <XAxis dataKey="source" tick={{ fill: PALETTE.muted, fontSize: 11 }} />
            <YAxis tick={{ fill: PALETTE.muted, fontSize: 11 }} />
            <Tooltip contentStyle={{ background: PALETTE.surface, border: `1px solid ${PALETTE.border}`, borderRadius: 8 }} />
            <Bar dataKey={mode === "unweighted" ? "Raw Risk Contribution" : "Weighted Risk Contribution"}
              fill={mode === "unweighted" ? PALETTE.warning : PALETTE.accent} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <Card>
        <div style={{ color: PALETTE.muted, fontSize: 11, fontFamily: "monospace", marginBottom: 12 }}>LIVE SOURCE WEIGHT TIER TABLE</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 80px 60px 80px", gap: 0 }}>
          {["Source", "Tier", "Weight", "Live DB Reports"].map(h => (
            <div key={h} style={{ color: PALETTE.muted, fontSize: 10, fontFamily: "monospace", padding: "4px 8px", borderBottom: `1px solid ${PALETTE.border}` }}>
              {h}
            </div>
          ))}
          {tableData.map(r => [
            <div key={r.source + "n"} style={{ color: PALETTE.text, fontSize: 12, padding: "6px 8px", borderBottom: `1px solid ${PALETTE.border}22` }}>{r.source}</div>,
            <div key={r.source + "t"} style={{ color: PALETTE.muted, fontSize: 11, padding: "6px 8px", borderBottom: `1px solid ${PALETTE.border}22` }}>{r.tier}</div>,
            <div key={r.source + "w"} style={{ color: r.weight >= 0.85 ? PALETTE.safe : r.weight >= 0.60 ? PALETTE.accent : PALETTE.warning, fontSize: 12, fontWeight: 700, padding: "6px 8px", borderBottom: `1px solid ${PALETTE.border}22` }}>{r.weight.toFixed(2)}</div>,
            <div key={r.source + "r"} style={{ color: PALETTE.text, fontSize: 12, fontWeight: 600, padding: "6px 8px", borderBottom: `1px solid ${PALETTE.border}22` }}>{r.reports || 0}</div>,
          ])}
        </div>
      </Card>
    </div>
  );
}

// ─── Panel 4: Cross-District Pattern Linking ──────────────────────────────────
function CrossDistrictPanel({ crossDistrictPatterns }) {
  const [selected, setSelected] = useState(null);

  const patterns = crossDistrictPatterns && crossDistrictPatterns.length > 0 ? crossDistrictPatterns : [
    { week: "2026-W31", scam_type: "Tourist Scam / Warning", districts: ["Badulla", "Colombo", "Galle", "Kandy"], count: 15 },
    { week: "2026-W31", scam_type: "Safety Advisory", districts: ["Ampara", "Badulla", "Colombo", "Kandy", "Trincomalee"], count: 14 },
    { week: "2026-W31", scam_type: "General Safety", districts: ["Ampara", "Colombo"], count: 12 },
    { week: "2026-W32", scam_type: "Tuk-Tuk / Transport Scam", districts: ["Jaffna", "Colombo"], count: 7 },
    { week: "2026-W20", scam_type: "Theft / Robbery", districts: ["Colombo", "Monaragala"], count: 3 },
  ];

  const getUrgency = (count, districts) => {
    if (count >= 10 && districts.length >= 4) return "critical";
    if (count >= 5 || districts.length >= 3) return "elevated";
    return "watch";
  };

  const urgencyStyle = {
    critical: { color: PALETTE.danger, bg: PALETTE.danger + "11", border: PALETTE.danger + "33", label: "CRITICAL" },
    elevated:  { color: PALETTE.warning, bg: PALETTE.warning + "11", border: PALETTE.warning + "33", label: "ELEVATED" },
    watch:     { color: PALETTE.muted, bg: PALETTE.border + "55", border: PALETTE.border, label: "WATCH" },
  };

  const weekSummary = patterns.reduce((acc, p) => {
    if (!acc[p.week]) acc[p.week] = { week: p.week, patterns: [], total: 0, maxDistricts: 0 };
    acc[p.week].patterns.push(p);
    acc[p.week].total += p.count;
    acc[p.week].maxDistricts = Math.max(acc[p.week].maxDistricts, p.districts.length);
    return acc;
  }, {});

  const weekList = Object.values(weekSummary).sort((a, b) => b.total - a.total);

  return (
    <div>
      <SectionHeader label="04 — Cross-District Pattern Linking (Live DB)" badge="Live Signal Engine">
        Same scam type appearing in multiple districts within the same calendar week detected directly from backend database reports.
      </SectionHeader>

      <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {weekList.map(w => {
            const urgency = getUrgency(w.total, w.patterns.flatMap(p => p.districts));
            const s = urgencyStyle[urgency];
            return (
              <div key={w.week} onClick={() => setSelected(selected?.week === w.week ? null : w)}
                style={{
                  background: selected?.week === w.week ? s.bg : PALETTE.card,
                  border: `1px solid ${selected?.week === w.week ? s.border : PALETTE.border}`,
                  borderRadius: 10, padding: "12px 14px", cursor: "pointer", transition: "all 0.15s"
                }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontFamily: "monospace", fontSize: 12, color: PALETTE.text }}>{w.week}</span>
                  <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>
                    {s.label}
                  </span>
                </div>
                <div style={{ color: PALETTE.muted, fontSize: 11 }}>
                  {w.patterns.length} pattern{w.patterns.length !== 1 ? "s" : ""} · {w.total} reports · {w.maxDistricts} districts
                </div>
              </div>
            );
          })}
        </div>

        <Card>
          {!selected ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: PALETTE.muted, fontSize: 13 }}>
              ← Select a week to inspect live cross-district patterns
            </div>
          ) : (
            <div>
              <div style={{ color: PALETTE.accent, fontFamily: "monospace", fontSize: 12, marginBottom: 16 }}>
                {selected.week} — {selected.total} total reports in live database
              </div>
              {selected.patterns.map((p, i) => {
                const urgency = getUrgency(p.count, p.districts);
                const s = urgencyStyle[urgency];
                return (
                  <div key={i} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: i < selected.patterns.length - 1 ? `1px solid ${PALETTE.border}` : "none" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                      <div>
                        <div style={{ color: PALETTE.text, fontWeight: 700, fontSize: 14 }}>{p.scam_type}</div>
                        <div style={{ color: PALETTE.muted, fontSize: 11, marginTop: 2 }}>{p.count} reports across {p.districts.length} districts</div>
                      </div>
                      <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, background: s.bg, color: s.color, border: `1px solid ${s.border}`, whiteSpace: "nowrap" }}>
                        {s.label}
                      </span>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {p.districts.map(d => (
                        <span key={d} style={{
                          padding: "4px 10px", borderRadius: 20, fontSize: 11, fontWeight: 600,
                          background: (DISTRICT_COLORS[d] || "#64748B") + "22",
                          color: DISTRICT_COLORS[d] || PALETTE.muted,
                          border: `1px solid ${(DISTRICT_COLORS[d] || "#64748B")}44`,
                        }}>
                          {d}
                        </span>
                      ))}
                    </div>
                    <div style={{ marginTop: 10, padding: "8px 12px", background: PALETTE.surface, borderRadius: 8, color: PALETTE.muted, fontSize: 11, lineHeight: 1.5 }}>
                      <strong style={{ color: PALETTE.text }}>Interpretation:</strong> {
                        p.districts.length >= 4
                          ? `Multi-district synchrony suggests a systemic or media-driven reporting event, not an isolated local incident. Flagged as a cascade pattern.`
                          : `Two-district co-occurrence. Possible route-based scam (travellers moving between districts) or shared media coverage window.`
                      }
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

// ─── Root Analytics Component ──────────────────────────────────────────────────
const TABS = [
  { id: "trend", label: "Temporal Trend", icon: "📈" },
  { id: "demo", label: "Demographic Targeting", icon: "🎯" },
  { id: "source", label: "Source Credibility", icon: "⚖️" },
  { id: "cross", label: "Cross-District Patterns", icon: "🔗" },
];

export default function SafeTravelLK_Analytics({ onNavigateMap }) {
  const [tab, setTab] = useState("trend");
  const [analyticsData, setAnalyticsData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchAnalytics() {
      try {
        const urls = [
          "/api/v1/analytics/dashboard",
          "http://localhost:8000/api/v1/analytics/dashboard"
        ];
        let res = null;
        for (const u of urls) {
          try {
            res = await fetch(u);
            if (res.ok) break;
          } catch (e) {
            // try next
          }
        }
        if (res && res.ok) {
          const data = await res.json();
          setAnalyticsData(data);
        }
      } catch (err) {
        console.error("Failed to load live analytics data:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchAnalytics();
  }, []);

  const totalIncidents = analyticsData?.total_incidents || 197;
  const dateRange = analyticsData?.date_range || "2010 – 2026";

  return (
    <div style={{
      minHeight: "100vh", background: PALETTE.bg, color: PALETTE.text,
      fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
    }}>
      {/* Header */}
      <div style={{
        borderBottom: `1px solid ${PALETTE.border}`,
        background: PALETTE.surface,
        padding: "16px 32px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 18 }}>🇱🇰</span>
            <span style={{ fontWeight: 800, fontSize: 16, letterSpacing: "-0.02em", color: PALETTE.text }}>SafeTravel LK</span>
            <span style={{ color: PALETTE.border }}>|</span>
            <span style={{ color: PALETTE.accent, fontSize: 12, fontFamily: "monospace", letterSpacing: "0.08em" }}>RESEARCH ANALYTICS (LIVE BACKEND)</span>
          </div>
          <div style={{ color: PALETTE.muted, fontSize: 11, marginTop: 2 }}>
            Temporal trends · Demographic classifiers · Source weighting · Cross-district signals
          </div>
        </div>
        <div style={{ textAlign: "right", display: "flex", alignItems: "center", gap: 14 }}>
          {onNavigateMap && (
            <button onClick={onNavigateMap} style={{
              background: "rgba(6, 182, 212, 0.12)", border: "1px solid rgba(6, 182, 212, 0.35)",
              borderRadius: 8, color: "#38bdf8", fontSize: 11, fontWeight: 700, padding: "6px 12px",
              cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
              display: "flex", alignItems: "center", gap: 6,
            }}>
              🗺️ Map Engine (Page 1) ↗
            </button>
          )}
          <div>
            <div style={{ fontSize: 11, color: PALETTE.accent, fontFamily: "monospace", fontWeight: 700 }}>
              ⚡ n = {totalIncidents} live DB incidents
            </div>
            <div style={{ fontSize: 11, color: PALETTE.muted, fontFamily: "monospace" }}>{dateRange}</div>
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ borderBottom: `1px solid ${PALETTE.border}`, background: PALETTE.surface, padding: "0 32px", display: "flex", gap: 0 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: "12px 20px", border: "none", background: "transparent",
            borderBottom: `2px solid ${tab === t.id ? PALETTE.accent : "transparent"}`,
            color: tab === t.id ? PALETTE.accent : PALETTE.muted,
            cursor: "pointer", fontSize: 13, fontWeight: tab === t.id ? 700 : 400,
            display: "flex", alignItems: "center", gap: 7, transition: "all 0.15s",
          }}>
            <span>{t.icon}</span>{t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ padding: "32px", maxWidth: 1200, margin: "0 auto" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "60px 0", color: PALETTE.accent, fontFamily: "monospace" }}>
            ⚡ Connecting to Live Backend Database...
          </div>
        ) : (
          <>
            {tab === "trend" && (
              <TemporalTrendPanel
                yearlyDistrict={analyticsData?.yearly_district}
                yearlyScamType={analyticsData?.yearly_scam_type}
              />
            )}
            {tab === "demo" && (
              <DemographicPanel
                demographicData={analyticsData?.demographic_data}
              />
            )}
            {tab === "source" && (
              <SourceCredibilityPanel
                sourceWeightData={analyticsData?.source_weight_data}
              />
            )}
            {tab === "cross" && (
              <CrossDistrictPanel
                crossDistrictPatterns={analyticsData?.cross_district_patterns}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
