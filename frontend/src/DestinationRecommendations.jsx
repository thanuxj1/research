import React, { useState, useEffect } from 'react';
import { getRecommendations, getAutomaticWeatherAndCrowd, calculateCrowdFromDate } from './api.js';

export default function DestinationRecommendations({ onBack }) {
  const [userPrefText, setUserPrefText] = useState('');
  const [plannedDate, setPlannedDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [origin, setOrigin] = useState('Colombo');
  const [days, setDays] = useState(3);
  const [transportMode, setTransportMode] = useState('car');

  const [recommendations, setRecommendations] = useState([]);
  const [routeRecommendations, setRouteRecommendations] = useState([]);
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [isLiveApi, setIsLiveApi] = useState(false);
  const [autoTelemetry, setAutoTelemetry] = useState(getAutomaticWeatherAndCrowd());

  // Backend JSON Response Debug Viewer state
  const [rawResponseJson, setRawResponseJson] = useState(null);
  const [rawRequestPayload, setRawRequestPayload] = useState(null);
  const [showJsonViewer, setShowJsonViewer] = useState(true);

  // Computed crowd metrics from the selected date
  const derivedCrowd = calculateCrowdFromDate(plannedDate);
  const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const dayName = dayNames[derivedCrowd.day_of_week];

  // Fetch recommendations automatically on mount & when inputs change
  useEffect(() => {
    fetchRecommendationsData(userPrefText, plannedDate, origin, days, transportMode);
  }, []);

  const fetchRecommendationsData = async (
    prefText = userPrefText,
    dateVal = plannedDate,
    origVal = origin,
    daysVal = days,
    modeVal = transportMode
  ) => {
    setLoadingRecs(true);
    const telemetry = getAutomaticWeatherAndCrowd();
    setAutoTelemetry(telemetry);

    const res = await getRecommendations(prefText, {
      plannedDate: dateVal,
      origin: origVal,
      days: Number(daysVal) || 3,
      transport_mode: modeVal,
    });

    setRecommendations(res.recommendations || []);
    setRouteRecommendations(res.route_recommendations || []);
    setIsLiveApi(res.isLive);
    setRawResponseJson(res.rawJson || null);
    setRawRequestPayload(res.requestPayload || null);
    setLoadingRecs(false);
  };

  const getPlaceImage = (pName, providedImg) => {
    if (providedImg && !providedImg.includes('undefined')) return providedImg;
    const clean = (pName || '').toLowerCase().trim();
    if (clean.includes('galle')) return '/images/galle.png';
    if (clean.includes('sigiriya')) return '/images/sigiriya.png';
    if (clean.includes('nuwara')) return '/images/nuwara_eliya.png';
    if (clean.includes('mirissa') || clean.includes('bentota') || clean.includes('arugam') || clean.includes('trincomalee') || clean.includes('hikkaduwa')) return '/images/mirissa.png';
    return '/images/ella.png';
  };

  const topRoute = routeRecommendations.length > 0 ? routeRecommendations[0] : null;

  return (
    <div style={styles.container}>
      {/* Navigation Header */}
      <header style={styles.exploreNavHeader}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button onClick={onBack} style={styles.backNavBtn}>
            ← Back
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ ...styles.cardIconBadge, width: 36, height: 36, marginBottom: 0, background: '#10b981' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.2">
                <path d="M12 2a8 8 0 0 0-8 8c0 5.25 8 12 8 12s8-6.75 8-12a8 8 0 0 0-8-8z"></path>
                <circle cx="12" cy="10" r="3"></circle>
              </svg>
            </div>
            <span style={{ fontSize: 16, fontWeight: 700, color: '#0f172a' }}>
              SafeTravel AI Route Assistant
            </span>
          </div>
        </div>

        {/* API Connection Indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: isLiveApi ? '#10b981' : '#f59e0b',
          }} />
          <span style={{ fontSize: 12, color: isLiveApi ? '#059669' : '#d97706', fontWeight: 700 }}>
            {isLiveApi ? '🟢 Live Route Engine Connected' : '🟠 Telemetry Simulation'}
          </span>
        </div>
      </header>

      {/* Main Content Container */}
      <div style={styles.recsMainContainer}>
        {/* Header Title Section */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={styles.recsTitle}>AI Route Recommendation & Optimization</h1>
          <p style={styles.recsSubtitle}>
            Intelligent multi-destination route sequence optimization, daily schedule planning & AI explainability
          </p>
        </div>

        {/* Route Planning Inputs Card */}
        <div style={styles.prefCard}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr auto', gap: 12, alignItems: 'flex-end' }}>
            {/* Preference Input */}
            <div>
              <label style={styles.prefCardLabel}>Tell us your preference</label>
              <input
                value={userPrefText}
                onChange={(e) => setUserPrefText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && fetchRecommendationsData(userPrefText, plannedDate, origin, days, transportMode)}
                placeholder="e.g., I want a quiet cold place"
                style={styles.prefInput}
              />
            </div>

            {/* Starting Origin */}
            <div>
              <label style={styles.prefCardLabel}>📍 Starting Origin</label>
              <select
                value={origin}
                onChange={(e) => {
                  setOrigin(e.target.value);
                  fetchRecommendationsData(userPrefText, plannedDate, e.target.value, days, transportMode);
                }}
                style={styles.prefSelect}
              >
                <option value="Colombo">Colombo</option>
                <option value="Kandy">Kandy</option>
                <option value="Galle">Galle</option>
                <option value="Negombo">Negombo</option>
              </select>
            </div>

            {/* Days Duration */}
            <div>
              <label style={styles.prefCardLabel}>📅 Duration (Days)</label>
              <select
                value={days}
                onChange={(e) => {
                  const numDays = Number(e.target.value);
                  setDays(numDays);
                  fetchRecommendationsData(userPrefText, plannedDate, origin, numDays, transportMode);
                }}
                style={styles.prefSelect}
              >
                <option value={1}>1 Day</option>
                <option value={2}>2 Days</option>
                <option value={3}>3 Days</option>
                <option value={4}>4 Days</option>
                <option value={5}>5 Days</option>
              </select>
            </div>

            {/* Transport Mode */}
            <div>
              <label style={styles.prefCardLabel}>🚗 Transport</label>
              <select
                value={transportMode}
                onChange={(e) => {
                  setTransportMode(e.target.value);
                  fetchRecommendationsData(userPrefText, plannedDate, origin, days, e.target.value);
                }}
                style={styles.prefSelect}
              >
                <option value="car">Car (🚗)</option>
                <option value="bus">Bus (🚌)</option>
                <option value="train">Train (🚆)</option>
              </select>
            </div>

            {/* Visit Date */}
            <div>
              <label style={styles.prefCardLabel}>🗓️ Visit Date</label>
              <input
                type="date"
                value={plannedDate}
                onChange={(e) => {
                  const newDate = e.target.value;
                  setPlannedDate(newDate);
                  fetchRecommendationsData(userPrefText, newDate, origin, days, transportMode);
                }}
                style={{ ...styles.prefInput, cursor: 'pointer', padding: '0 10px' }}
              />
            </div>

            {/* Submit Button */}
            <div>
              <button
                onClick={() => fetchRecommendationsData(userPrefText, plannedDate, origin, days, transportMode)}
                disabled={loadingRecs}
                style={styles.getRecsBtn}
              >
                {loadingRecs ? 'Optimizing...' : 'Optimize Route'}
              </button>
            </div>
          </div>

          {/* Quick Preference Chips & Computed Date Parameters */}
          <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <button
              onClick={() => {
                const text = 'I want a quiet cold place';
                setUserPrefText(text);
                fetchRecommendationsData(text, plannedDate, origin, days, transportMode);
              }}
              style={styles.quickChipBtn}
            >
              <span style={{ fontSize: 13 }}>❄️</span> Cold & quiet route
            </button>
            <button
              onClick={() => {
                const text = 'I want beach and nature';
                setUserPrefText(text);
                fetchRecommendationsData(text, plannedDate, origin, days, transportMode);
              }}
              style={styles.quickChipBtn}
            >
              <span style={{ fontSize: 13 }}>🏖️</span> Beach & coastal route
            </button>

            {/* Derived Date Telemetry Badge */}
            <span style={styles.dateTelemetryBadge}>
              🗓️ <strong>Parameters:</strong> month: {derivedCrowd.month}, day: {derivedCrowd.day_of_week} ({dayName})
            </span>
          </div>
        </div>

        {/* ── BACKEND JSON RETURN VIEWER PANEL ── */}
        <div style={styles.jsonPanelContainer}>
          <div style={styles.jsonPanelHeader}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 16 }}>🔌</span>
              <strong style={{ fontSize: 13, color: '#f8fafc' }}>
                Backend JSON Return (POST http://127.0.0.1:5000/assistance/recommend)
              </strong>
            </div>
            <button
              onClick={() => setShowJsonViewer(!showJsonViewer)}
              style={styles.jsonToggleBtn}
            >
              {showJsonViewer ? 'Hide JSON ▲' : 'Show JSON ▼'}
            </button>
          </div>

          {showJsonViewer && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, padding: '16px 20px', background: '#090d16' }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', marginBottom: 6, textTransform: 'uppercase' }}>
                  Request Payload (JSON)
                </div>
                <pre style={styles.codeBlock}>
                  {rawRequestPayload ? JSON.stringify(rawRequestPayload, null, 2) : '// Sending request...'}
                </pre>
              </div>

              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: isLiveApi ? '#34d399' : '#fbbf24', marginBottom: 6, textTransform: 'uppercase' }}>
                  Response Return (JSON) {isLiveApi ? '(Live Backend API)' : '(Fallback)'}
                </div>
                <pre style={{ ...styles.codeBlock, borderColor: isLiveApi ? 'rgba(52, 211, 153, 0.4)' : 'rgba(251, 191, 36, 0.4)', color: isLiveApi ? '#6ee7b7' : '#fde68a' }}>
                  {rawResponseJson ? JSON.stringify(rawResponseJson, null, 2) : '// Awaiting backend response...'}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* ── PRIMARY FEATURE: AI RECOMMENDED ROUTE CARD ── */}
        {loadingRecs ? (
          <div style={styles.loadingBox}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>🧭</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
              Calculating segment distances, optimizing route sequence & evaluating feasibility...
            </div>
          </div>
        ) : topRoute ? (
          <div style={styles.routeHeroCard}>
            {/* Header Badge & Score */}
            <div style={styles.routeHeroHeader}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={styles.trophyBadge}>🏆 AI Recommended Route</span>
                <span style={styles.rankDecisionBadge}>
                  #{topRoute.rank || 1} {topRoute.decision || 'Highly Recommended'}
                </span>
              </div>
              <div style={styles.routeScoreBox}>
                <span style={styles.routeScoreNum}>{topRoute.overall_route_score}</span>
                <span style={styles.routeScoreMax}>/ 100</span>
              </div>
            </div>

            {/* Route Sequence Display */}
            <h2 style={styles.routeSequenceTitle}>
              {topRoute.route_display || (topRoute.route ? topRoute.route.join(' → ') : 'Colombo → Kandy → Nuwara Eliya → Ella')}
            </h2>

            {/* Summary Stat Pills */}
            <div style={styles.statPillsRow}>
              <span style={styles.statPill}>
                🚗 <strong>{topRoute.total_distance_km} km</strong>
              </span>
              <span style={styles.statPill}>
                ⏱ <strong>{topRoute.total_travel_time} total travel</strong>
              </span>
              <span style={styles.statPill}>
                📅 <strong>{topRoute.days} Days</strong>
              </span>
              <span style={{
                ...styles.statPill,
                background: topRoute.feasible ? '#ecfdf5' : '#fef2f2',
                color: topRoute.feasible ? '#047857' : '#b91c1c',
                borderColor: topRoute.feasible ? '#a7f3d0' : '#fecaca'
              }}>
                {topRoute.feasible ? '✓ Feasible' : '⚠ High Travel Time'}
              </span>
            </div>

            {/* Route Timeline */}
            <div style={styles.sectionDivider}>
              <h3 style={styles.subSectionTitle}>📍 Route Timeline (Independent Segments)</h3>
              <div style={styles.timelineContainer}>
                {(topRoute.route || []).map((stop, idx) => {
                  const segment = (topRoute.segments || [])[idx];
                  return (
                    <React.Fragment key={idx}>
                      <div style={styles.timelineNode}>
                        <div style={styles.timelineDot} />
                        <span style={styles.timelineNodeName}>{stop}</span>
                      </div>
                      {segment && (
                        <div style={styles.timelineArrowRow}>
                          <div style={styles.timelineLine} />
                          <span style={styles.segmentTimeBadge}>
                            ↓ {segment.estimated_travel_time} ({segment.distance_km} km)
                          </span>
                        </div>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>

            {/* Daily Travel Plan */}
            <div style={styles.sectionDivider}>
              <h3 style={styles.subSectionTitle}>🗓️ Daily Travel Plan</h3>
              <div style={styles.dailyPlanGrid}>
                {(topRoute.daily_plan || []).map((dp, dIdx) => (
                  <div key={dIdx} style={styles.dailyPlanCard}>
                    <div style={styles.dayBadge}>DAY {dp.day}</div>
                    <div style={styles.dayRouteHeader}>{dp.route}</div>
                    <div style={{ fontSize: 12, color: '#64748b', marginBottom: 10 }}>⏱ Travel: {dp.travel_time}</div>
                    
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#334155', marginBottom: 4 }}>Scheduled Activities:</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {(dp.activities || []).map((act, aIdx) => (
                        <div key={aIdx} style={styles.activityItem}>
                          <span>🎯 {act.name}</span>
                          <span style={{ fontSize: 11, color: '#059669', fontWeight: 600 }}>{act.time}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Why AI Recommends & Tradeoffs */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginTop: 24 }}>
              {/* Why Recommended */}
              <div style={styles.reasonsCard}>
                <h4 style={{ ...styles.cardSubHeader, color: '#047857' }}>Why AI Recommends This Route</h4>
                <ul style={styles.bulletList}>
                  {(topRoute.why_recommended || []).map((reason, rIdx) => (
                    <li key={rIdx} style={styles.whyListItem}>
                      <span style={{ color: '#10b981', fontWeight: 800 }}>✓</span> {reason}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Trade-offs */}
              <div style={styles.tradeoffsCard}>
                <h4 style={{ ...styles.cardSubHeader, color: '#b45309' }}>Trade-offs</h4>
                <ul style={styles.bulletList}>
                  {(topRoute.tradeoffs || []).map((to, tIdx) => (
                    <li key={tIdx} style={styles.tradeoffListItem}>
                      <span style={{ color: '#f59e0b', fontWeight: 800 }}>⚠</span> {to}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        ) : null}

        {/* ── SECONDARY FEATURE: INDIVIDUAL DESTINATION CARDS ── */}
        <div style={{ marginTop: 44 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ ...styles.recsSectionHeader, margin: 0 }}>
              Supporting Individual Destination Scores ({recommendations.length})
            </h2>
            <span style={{ fontSize: 12, color: '#64748b' }}>
              Steps 1–6 Sub-component Evaluations
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {recommendations.map((rec, index) => {
              const rank = index + 1;
              const rankBg = rank === 1 ? '#10b981' : rank === 2 ? '#eab308' : rank === 3 ? '#06b6d4' : '#64748b';
              const crowdText = rec.crowd_label || (rec.crowd < 110 ? 'Low' : rec.crowd < 200 ? 'Moderate' : 'High');
              const crowdBg = crowdText === 'Low' ? '#ecfdf5' : crowdText === 'Moderate' ? '#fefce8' : '#fef2f2';
              const crowdColor = crowdText === 'Low' ? '#047857' : crowdText === 'Moderate' ? '#ca8a04' : '#b91c1c';

              const weatherText = rec.weather || 'Low';
              const weatherBg = weatherText === 'Low' || weatherText === 'Good' ? '#ecfdf5' : '#fefce8';
              const weatherColor = weatherText === 'Low' || weatherText === 'Good' ? '#047857' : '#ca8a04';

              return (
                <div key={index} style={styles.recItemCard}>
                  {/* Thumbnail Image + Rank Badge Overlay */}
                  <div style={styles.recImageContainer}>
                    <img
                      src={getPlaceImage(rec.place, rec.image)}
                      alt={rec.place}
                      style={styles.recImage}
                    />
                    <div style={{ ...styles.rankBadge, background: rankBg }}>
                      {rank}
                    </div>
                  </div>

                  {/* Destination Details Column */}
                  <div style={styles.recInfoCol}>
                    <h3 style={styles.recPlaceTitle}>{rec.place}</h3>
                    <p style={styles.recPlaceDesc}>
                      {rec.desc || `Top destination in Sri Lanka with optimal live weather and crowd metrics.`}
                    </p>
                  </div>

                  {/* Right Metrics Grid Columns */}
                  <div style={styles.recMetricsGrid}>
                    <div style={styles.metricBlock}>
                      <div style={styles.metricLabel}>Crowd Level</div>
                      <div style={{ ...styles.metricBadge, background: crowdBg, color: crowdColor }}>
                        <span style={{ fontSize: 13 }}>👥</span> {crowdText} <span style={{ fontSize: 10, opacity: 0.7 }}>({rec.crowd})</span>
                      </div>
                    </div>

                    <div style={styles.metricBlock}>
                      <div style={styles.metricLabel}>Weather</div>
                      <div style={{ ...styles.metricBadge, background: weatherBg, color: weatherColor }}>
                        <span style={{ fontSize: 13 }}>🌤️</span> {weatherText}
                      </div>
                    </div>

                    <div style={styles.metricBlock}>
                      <div style={styles.metricLabel}>Score</div>
                      <div style={styles.scoreValue}>
                        {rec.score}<span style={styles.scoreMax}>/100</span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Styling definitions ──
const styles = {
  container: {
    minHeight: '100vh',
    background: '#f8fafc',
    fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
    color: '#0f172a',
    paddingBottom: '60px',
  },

  exploreNavHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px 40px',
    background: '#ffffff',
    borderBottom: '1px solid #e2e8f0',
    position: 'sticky',
    top: 0,
    zIndex: 100,
  },

  backNavBtn: {
    padding: '8px 16px',
    borderRadius: '10px',
    border: '1px solid #cbd5e1',
    background: '#ffffff',
    color: '#334155',
    fontWeight: '600',
    fontSize: '13px',
    cursor: 'pointer',
  },

  cardIconBadge: {
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },

  recsMainContainer: {
    maxWidth: '1100px',
    margin: '32px auto',
    padding: '0 24px',
  },

  recsTitle: {
    fontSize: '28px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 6px 0',
    letterSpacing: '-0.02em',
  },

  recsSubtitle: {
    fontSize: '14.5px',
    color: '#64748b',
    margin: 0,
  },

  prefCard: {
    background: '#ffffff',
    borderRadius: '20px',
    border: '1px solid #e2e8f0',
    padding: '24px 28px',
    boxShadow: '0 8px 24px rgba(0,0,0,0.03)',
  },

  prefCardLabel: {
    fontSize: '12.5px',
    fontWeight: '700',
    color: '#334155',
    display: 'block',
    marginBottom: '6px',
  },

  prefInput: {
    width: '100%',
    boxSizing: 'border-box',
    height: '42px',
    padding: '0 14px',
    borderRadius: '10px',
    border: '1.5px solid #cbd5e1',
    background: '#f8fafc',
    fontSize: '13.5px',
    color: '#0f172a',
    outline: 'none',
  },

  prefSelect: {
    width: '100%',
    boxSizing: 'border-box',
    height: '42px',
    padding: '0 10px',
    borderRadius: '10px',
    border: '1.5px solid #cbd5e1',
    background: '#f8fafc',
    fontSize: '13px',
    fontWeight: '600',
    color: '#0f172a',
    outline: 'none',
    cursor: 'pointer',
  },

  getRecsBtn: {
    height: '42px',
    padding: '0 20px',
    borderRadius: '10px',
    border: 'none',
    background: '#059669',
    color: '#ffffff',
    fontWeight: '700',
    fontSize: '13.5px',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    boxShadow: '0 4px 14px rgba(5,150,105,0.25)',
  },

  quickChipBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 12px',
    borderRadius: '16px',
    border: '1px solid #a7f3d0',
    background: '#ecfdf5',
    color: '#047857',
    fontSize: '12px',
    fontWeight: '600',
    cursor: 'pointer',
  },

  dateTelemetryBadge: {
    fontSize: '12px',
    color: '#1e40af',
    background: '#eff6ff',
    border: '1px solid #bfdbfe',
    padding: '5px 12px',
    borderRadius: '16px',
  },

  jsonPanelContainer: {
    marginTop: '20px',
    background: '#0f172a',
    borderRadius: '16px',
    border: '1px solid #1e293b',
    overflow: 'hidden',
    boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
  },

  jsonPanelHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 20px',
    background: '#1e293b',
    borderBottom: '1px solid rgba(255,255,255,0.05)',
  },

  jsonToggleBtn: {
    background: 'rgba(255,255,255,0.1)',
    border: 'none',
    color: '#94a3b8',
    fontSize: '12px',
    fontWeight: '600',
    padding: '4px 10px',
    borderRadius: '6px',
    cursor: 'pointer',
  },

  codeBlock: {
    margin: 0,
    padding: '14px',
    background: '#040810',
    border: '1px solid #1e293b',
    borderRadius: '10px',
    fontFamily: "'Fira Code', 'Consolas', monospace",
    fontSize: '12px',
    color: '#38bdf8',
    maxHeight: '200px',
    overflowY: 'auto',
    lineHeight: 1.4,
  },

  /* Primary Route Hero Card Styles */
  routeHeroCard: {
    marginTop: '32px',
    background: '#ffffff',
    borderRadius: '24px',
    border: '2px solid #10b981',
    padding: '32px',
    boxShadow: '0 20px 40px rgba(16,185,129,0.1)',
  },

  routeHeroHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
  },

  trophyBadge: {
    background: '#10b981',
    color: '#ffffff',
    padding: '6px 14px',
    borderRadius: '20px',
    fontSize: '13px',
    fontWeight: '800',
  },

  rankDecisionBadge: {
    background: '#ecfdf5',
    color: '#047857',
    border: '1px solid #a7f3d0',
    padding: '6px 14px',
    borderRadius: '20px',
    fontSize: '13px',
    fontWeight: '700',
  },

  routeScoreBox: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '4px',
    background: '#f0fdf4',
    padding: '8px 18px',
    borderRadius: '16px',
    border: '1px solid #bbf7d0',
  },

  routeScoreNum: {
    fontSize: '32px',
    fontWeight: '900',
    color: '#059669',
  },

  routeScoreMax: {
    fontSize: '14px',
    color: '#94a3b8',
    fontWeight: '600',
  },

  routeSequenceTitle: {
    fontSize: '26px',
    fontWeight: '900',
    color: '#0f172a',
    margin: '0 0 16px 0',
    letterSpacing: '-0.02em',
  },

  statPillsRow: {
    display: 'flex',
    gap: '12px',
    flexWrap: 'wrap',
    marginBottom: '28px',
  },

  statPill: {
    padding: '8px 16px',
    borderRadius: '12px',
    background: '#f1f5f9',
    border: '1px solid #e2e8f0',
    fontSize: '13.5px',
    color: '#334155',
  },

  sectionDivider: {
    marginTop: '24px',
    paddingTop: '24px',
    borderTop: '1px solid #f1f5f9',
  },

  subSectionTitle: {
    fontSize: '16px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 16px 0',
  },

  timelineContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    overflowX: 'auto',
    padding: '12px 16px',
    background: '#f8fafc',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
  },

  timelineNode: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    background: '#ffffff',
    padding: '8px 16px',
    borderRadius: '12px',
    border: '1.5px solid #059669',
    boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
    whiteSpace: 'nowrap',
  },

  timelineDot: {
    width: '10px',
    height: '10px',
    borderRadius: '50%',
    background: '#10b981',
  },

  timelineNodeName: {
    fontSize: '14px',
    fontWeight: '700',
    color: '#0f172a',
  },

  timelineArrowRow: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '2px',
    whiteSpace: 'nowrap',
  },

  timelineLine: {
    width: '30px',
    height: '2px',
    background: '#cbd5e1',
  },

  segmentTimeBadge: {
    fontSize: '11px',
    fontWeight: '700',
    color: '#059669',
    background: '#ecfdf5',
    padding: '2px 8px',
    borderRadius: '8px',
  },

  dailyPlanGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
    gap: '16px',
  },

  dailyPlanCard: {
    background: '#f8fafc',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
    padding: '16px 18px',
  },

  dayBadge: {
    fontSize: '11px',
    fontWeight: '800',
    color: '#059669',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '4px',
  },

  dayRouteHeader: {
    fontSize: '15px',
    fontWeight: '800',
    color: '#0f172a',
    marginBottom: '4px',
  },

  activityItem: {
    fontSize: '12.5px',
    color: '#334155',
    background: '#ffffff',
    padding: '6px 10px',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  reasonsCard: {
    background: '#f0fdf4',
    borderRadius: '16px',
    border: '1px solid #bbf7d0',
    padding: '20px',
  },

  tradeoffsCard: {
    background: '#fffbeb',
    borderRadius: '16px',
    border: '1px solid #fef3c7',
    padding: '20px',
  },

  cardSubHeader: {
    fontSize: '14.5px',
    fontWeight: '800',
    margin: '0 0 12px 0',
  },

  bulletList: {
    margin: 0,
    paddingLeft: 0,
    listStyle: 'none',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },

  whyListItem: {
    fontSize: '13px',
    color: '#166534',
    display: 'flex',
    alignItems: 'baseline',
    gap: '8px',
  },

  tradeoffListItem: {
    fontSize: '13px',
    color: '#92400e',
    display: 'flex',
    alignItems: 'baseline',
    gap: '8px',
  },

  recsSectionHeader: {
    fontSize: '18px',
    fontWeight: '700',
    color: '#0f172a',
    margin: '0 0 16px 0',
  },

  loadingBox: {
    marginTop: '32px',
    padding: '48px 24px',
    textAlign: 'center',
    background: '#ffffff',
    borderRadius: '20px',
    border: '1px solid #e2e8f0',
  },

  recItemCard: {
    background: '#ffffff',
    borderRadius: '18px',
    border: '1px solid #e2e8f0',
    padding: '16px 20px',
    display: 'flex',
    alignItems: 'center',
    gap: '20px',
    boxShadow: '0 4px 16px rgba(0,0,0,0.02)',
  },

  recImageContainer: {
    position: 'relative',
    width: '160px',
    height: '100px',
    borderRadius: '14px',
    overflow: 'hidden',
    flexShrink: 0,
  },

  recImage: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  },

  rankBadge: {
    position: 'absolute',
    top: '8px',
    left: '8px',
    width: '24px',
    height: '24px',
    borderRadius: '50%',
    color: '#ffffff',
    fontSize: '12px',
    fontWeight: '800',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
  },

  recInfoCol: {
    flex: 1,
    minWidth: 0,
  },

  recPlaceTitle: {
    fontSize: '18px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 4px 0',
  },

  recPlaceDesc: {
    fontSize: '12.5px',
    color: '#64748b',
    margin: 0,
    lineHeight: '1.4',
  },

  recMetricsGrid: {
    display: 'flex',
    alignItems: 'center',
    gap: '24px',
    flexShrink: 0,
    paddingLeft: '16px',
    borderLeft: '1px solid #f1f5f9',
  },

  metricBlock: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    minWidth: '70px',
  },

  metricLabel: {
    fontSize: '10.5px',
    color: '#94a3b8',
    marginBottom: '4px',
    fontWeight: '600',
  },

  metricBadge: {
    padding: '3px 8px',
    borderRadius: '8px',
    fontSize: '12px',
    fontWeight: '600',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
  },

  scoreValue: {
    fontSize: '18px',
    fontWeight: '800',
    color: '#059669',
  },

  scoreMax: {
    fontSize: '11px',
    fontWeight: '500',
    color: '#94a3b8',
  },
};
