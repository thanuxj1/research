import React, { useState, useEffect } from 'react';
import { getRecommendations, getAutomaticWeatherAndCrowd, calculateCrowdFromDate } from './api.js';

export default function DestinationRecommendations({ onBack }) {
  const [userPrefText, setUserPrefText] = useState('');
  // Default planned visit date to today (YYYY-MM-DD)
  const [plannedDate, setPlannedDate] = useState(() => new Date().toISOString().split('T')[0]);

  const [recommendations, setRecommendations] = useState([]);
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

  // Fetch recommendations automatically on mount & when date changes
  useEffect(() => {
    fetchRecommendationsData(userPrefText, plannedDate);
  }, []);

  const fetchRecommendationsData = async (prefText = userPrefText, dateVal = plannedDate) => {
    setLoadingRecs(true);
    const telemetry = getAutomaticWeatherAndCrowd();
    setAutoTelemetry(telemetry);

    const res = await getRecommendations(prefText, { plannedDate: dateVal });
    setRecommendations(res.recommendations || []);
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
              SafeTravel AI Assistant
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
            {isLiveApi ? '🟢 Live Backend Model API Connected' : '🟠 Telemetry Simulation'}
          </span>
        </div>
      </header>

      {/* Main Content Container */}
      <div style={styles.recsMainContainer}>
        {/* Header Title Section */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={styles.recsTitle}>AI Destination Recommendations</h1>
          <p style={styles.recsSubtitle}>
            Get the best places to visit based on live weather and crowd predictions
          </p>
        </div>

        {/* Preference & Visit Date Input Card */}
        <div style={styles.prefCard}>
          <div style={styles.prefInputGrid}>
            {/* Preference Input */}
            <div style={{ flex: 1 }}>
              <label style={styles.prefCardLabel}>Tell us your preference (optional)</label>
              <input
                value={userPrefText}
                onChange={(e) => setUserPrefText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && fetchRecommendationsData(userPrefText, plannedDate)}
                placeholder="e.g., I want low crowd places with good weather"
                style={styles.prefInput}
              />
            </div>

            {/* Visit Date Input */}
            <div style={{ width: '210px' }}>
              <label style={styles.prefCardLabel}>📅 Planning Visit Date</label>
              <input
                type="date"
                value={plannedDate}
                onChange={(e) => {
                  const newDate = e.target.value;
                  setPlannedDate(newDate);
                  fetchRecommendationsData(userPrefText, newDate);
                }}
                style={{ ...styles.prefInput, cursor: 'pointer' }}
              />
            </div>

            {/* Submit Button */}
            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <button
                onClick={() => fetchRecommendationsData(userPrefText, plannedDate)}
                disabled={loadingRecs}
                style={styles.getRecsBtn}
              >
                {loadingRecs ? 'Analyzing...' : 'Get Recommendations'}
              </button>
            </div>
          </div>

          {/* Quick Preference Chips & Computed Date Parameters */}
          <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <button
              onClick={() => {
                const text = 'I want low crowd places';
                setUserPrefText(text);
                fetchRecommendationsData(text, plannedDate);
              }}
              style={styles.quickChipBtn}
            >
              <span style={{ fontSize: 13 }}>💎</span> Prefer low crowd places
            </button>

            {/* Derived Date Telemetry Badge */}
            <span style={styles.dateTelemetryBadge}>
              🗓️ <strong>Date Crowd Parameters:</strong> month: {derivedCrowd.month}, day_of_week: {derivedCrowd.day_of_week} ({dayName}), is_weekend: {derivedCrowd.is_weekend}
            </span>

            {/* Automatic Weather Status Badge */}
            <span style={styles.autoWeatherBadge}>
              🌤️ Auto Weather: {autoTelemetry.weather.temperature_c}°C, {autoTelemetry.weather.rainfall_mm}mm rain
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
              {/* Request JSON Sent */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', marginBottom: 6, textTransform: 'uppercase' }}>
                  Request Payload (JSON)
                </div>
                <pre style={styles.codeBlock}>
                  {rawRequestPayload ? JSON.stringify(rawRequestPayload, null, 2) : '// Sending request...'}
                </pre>
              </div>

              {/* Response JSON Returned */}
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

        {/* Recommended Destinations List Section */}
        <div style={{ marginTop: 36 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ ...styles.recsSectionHeader, margin: 0 }}>Recommended Destinations ({recommendations.length})</h2>
            {isLiveApi && (
              <span style={{ fontSize: 12, background: '#ecfdf5', color: '#047857', padding: '4px 10px', borderRadius: 12, fontWeight: 700 }}>
                ✓ Live Model Response ({recommendations.length} places)
              </span>
            )}
          </div>

          {loadingRecs ? (
            <div style={styles.loadingBox}>
              <div style={{ fontSize: 24, marginBottom: 8 }}>🔄</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#334155' }}>
                Processing recommendations from AI Engine...
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 16 }}>
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
                      {/* Crowd Level */}
                      <div style={styles.metricBlock}>
                        <div style={styles.metricLabel}>Crowd Level</div>
                        <div style={{ ...styles.metricBadge, background: crowdBg, color: crowdColor }}>
                          <span style={{ fontSize: 13 }}>👥</span> {crowdText} <span style={{ fontSize: 10, opacity: 0.7 }}>({rec.crowd})</span>
                        </div>
                      </div>

                      {/* Weather */}
                      <div style={styles.metricBlock}>
                        <div style={styles.metricLabel}>Weather</div>
                        <div style={{ ...styles.metricBadge, background: weatherBg, color: weatherColor }}>
                          <span style={{ fontSize: 13 }}>🌤️</span> {weatherText}
                        </div>
                      </div>

                      {/* Score */}
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
          )}
        </div>
      </div>
    </div>
  );
}

// ── Styles strictly following the provided mockup reference ──
const styles = {
  container: {
    minHeight: '100vh',
    background: '#ffffff',
    fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
    color: '#0f172a',
    paddingBottom: '40px',
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
    maxWidth: '1080px',
    margin: '36px auto',
    padding: '0 32px',
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
    boxShadow: '0 10px 30px rgba(0,0,0,0.03)',
  },

  prefCardLabel: {
    fontSize: '13px',
    fontWeight: '700',
    color: '#334155',
    display: 'block',
    marginBottom: '8px',
  },

  prefInputGrid: {
    display: 'flex',
    gap: '14px',
    alignItems: 'stretch',
  },

  prefInput: {
    width: '100%',
    boxSizing: 'border-box',
    height: '46px',
    padding: '0 16px',
    borderRadius: '12px',
    border: '1.5px solid #cbd5e1',
    background: '#f8fafc',
    fontSize: '14px',
    color: '#0f172a',
    outline: 'none',
  },

  getRecsBtn: {
    height: '46px',
    padding: '0 24px',
    borderRadius: '12px',
    border: 'none',
    background: '#059669',
    color: '#ffffff',
    fontWeight: '700',
    fontSize: '14px',
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

  autoWeatherBadge: {
    fontSize: '12px',
    color: '#64748b',
    background: '#f1f5f9',
    padding: '5px 12px',
    borderRadius: '16px',
  },

  /* Backend JSON Viewer Styles */
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
    maxHeight: '220px',
    overflowY: 'auto',
    lineHeight: 1.4,
  },

  recsSectionHeader: {
    fontSize: '20px',
    fontWeight: '700',
    color: '#0f172a',
    margin: '0 0 16px 0',
  },

  loadingBox: {
    padding: '48px 24px',
    textAlign: 'center',
    background: '#f8fafc',
    borderRadius: '16px',
    border: '1px border #e2e8f0',
  },

  recItemCard: {
    background: '#ffffff',
    borderRadius: '18px',
    border: '1px solid #e2e8f0',
    padding: '16px 20px',
    display: 'flex',
    alignItems: 'center',
    gap: '20px',
    boxShadow: '0 4px 16px rgba(0,0,0,0.03)',
  },

  recImageContainer: {
    position: 'relative',
    width: '180px',
    height: '110px',
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
    top: '10px',
    left: '10px',
    width: '26px',
    height: '26px',
    borderRadius: '50%',
    color: '#ffffff',
    fontSize: '13px',
    fontWeight: '800',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
  },

  recInfoCol: {
    flex: 1,
    minWidth: 0,
  },

  recPlaceTitle: {
    fontSize: '20px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 6px 0',
  },

  recPlaceDesc: {
    fontSize: '13px',
    color: '#64748b',
    margin: 0,
    lineHeight: '1.5',
  },

  recMetricsGrid: {
    display: 'flex',
    alignItems: 'center',
    gap: '32px',
    flexShrink: 0,
    paddingLeft: '16px',
    borderLeft: '1px solid #f1f5f9',
  },

  metricBlock: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    minWidth: '80px',
  },

  metricLabel: {
    fontSize: '11px',
    color: '#94a3b8',
    marginBottom: '6px',
    fontWeight: '500',
  },

  metricBadge: {
    padding: '4px 10px',
    borderRadius: '10px',
    fontSize: '12.5px',
    fontWeight: '600',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
  },

  scoreValue: {
    fontSize: '20px',
    fontWeight: '800',
    color: '#059669',
  },

  scoreMax: {
    fontSize: '12px',
    fontWeight: '500',
    color: '#94a3b8',
  },
};
