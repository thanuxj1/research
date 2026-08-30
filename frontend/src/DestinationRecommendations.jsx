import React, { useState } from 'react';
import { getRecommendations, getAutomaticWeatherAndCrowd, calculateCrowdFromDate } from './api.js';

const formatDateStr = (d) => {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const getTomorrowDateStr = () => {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  return formatDateStr(tomorrow);
};

const getMaxDateStr = () => {
  const maxDate = new Date();
  maxDate.setDate(maxDate.getDate() + 1);
  maxDate.setMonth(maxDate.getMonth() + 2);
  return formatDateStr(maxDate);
};

export default function DestinationRecommendations({ onBack }) {
  const tomorrowStr = getTomorrowDateStr();
  const maxDateStr = getMaxDateStr();
  const [userPrefText, setUserPrefText] = useState('');
  const [plannedDate, setPlannedDate] = useState(tomorrowStr);
  const origin = 'Colombo';
  const [days, setDays] = useState(3);
  const [transportMode, setTransportMode] = useState('car');

  // Recommendation state (starts empty until user presses Get Recommendations)
  const [recommendations, setRecommendations] = useState([]);
  const [routeRecommendations, setRouteRecommendations] = useState([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [isLiveApi, setIsLiveApi] = useState(false);
  const [autoTelemetry, setAutoTelemetry] = useState(getAutomaticWeatherAndCrowd());

  // Backend JSON Response Debug Viewer state
  const [rawResponseJson, setRawResponseJson] = useState(null);
  const [rawRequestPayload, setRawRequestPayload] = useState(null);
  const [showJsonViewer, setShowJsonViewer] = useState(false);

  // Computed crowd metrics from the selected date
  const derivedCrowd = calculateCrowdFromDate(plannedDate);
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const monthLabel = monthNames[derivedCrowd.month - 1] || 'Sep';
  const weekendLabel = derivedCrowd.is_weekend ? 'Weekend' : 'Weekday';

  const fetchRecommendationsData = async (
    prefText = userPrefText,
    dateVal = plannedDate,
    origVal = origin,
    daysVal = days,
    modeVal = transportMode
  ) => {
    setLoadingRecs(true);
    setHasSearched(true);
    const telemetry = getAutomaticWeatherAndCrowd();
    setAutoTelemetry(telemetry);

    const res = await getRecommendations(prefText, {
      plannedDate: dateVal,
      origin: origVal,
      days: Number(daysVal) || 3,
      transport_mode: modeVal,
    });

    console.log("Frontend Received Response:", res);
    console.log("Route Recommendations Array:", res?.route_recommendations);
    console.log("Destination Recommendations Array:", res?.recommendations);

    setRecommendations(res?.recommendations || []);
    setRouteRecommendations(res?.route_recommendations || []);
    setIsLiveApi(res?.isLive || false);
    setRawResponseJson(res?.rawJson || null);
    setRawRequestPayload(res?.requestPayload || null);
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

  const getDestinationDefaults = (pName, rec) => {
    const clean = (pName || '').toLowerCase().trim();

    let topActName = "Scenic Heritage Walk";
    let topActCat = "Nature";
    let topActDuration = 2.5;
    let travelTimeStr = "2h 30m";
    let travelKm = 120;
    let categoryTags = ["Nature", "Scenic"];

    if (clean.includes('nuwara')) {
      topActName = "Horton Plains Hiking";
      topActCat = "Nature";
      topActDuration = 4;
      travelTimeStr = "3h 47m";
      travelKm = 170;
      categoryTags = ["Nature", "Tea Estates", "Cool Weather"];
    } else if (clean.includes('ella')) {
      topActName = "Little Adam's Peak";
      topActCat = "Hiking";
      topActDuration = 2.5;
      travelTimeStr = "4h 45m";
      travelKm = 205;
      categoryTags = ["Nature", "Hiking", "Scenic"];
    } else if (clean.includes('galle')) {
      topActName = "Galle Fort Walk";
      topActCat = "Culture";
      topActDuration = 2.5;
      travelTimeStr = "2h 28m";
      travelKm = 120;
      categoryTags = ["Culture", "Beach", "Heritage"];
    } else if (clean.includes('mirissa')) {
      topActName = "Whale Watching";
      topActCat = "Beach";
      topActDuration = 3;
      travelTimeStr = "2h 40m";
      travelKm = 150;
      categoryTags = ["Beach", "Ocean", "Relaxation"];
    } else if (clean.includes('bentota')) {
      topActName = "River Lagoon Safari";
      topActCat = "Beach";
      topActDuration = 2.5;
      travelTimeStr = "1h 45m";
      travelKm = 85;
      categoryTags = ["Beach", "Resort", "Water Sports"];
    } else if (clean.includes('sigiriya')) {
      topActName = "Rock Fortress Climb";
      topActCat = "Heritage";
      topActDuration = 3;
      travelTimeStr = "3h 30m";
      travelKm = 165;
      categoryTags = ["Culture", "Heritage", "History"];
    } else if (clean.includes('kandy')) {
      topActName = "Temple of Tooth Visit";
      topActCat = "Culture";
      topActDuration = 2;
      travelTimeStr = "2h 50m";
      travelKm = 115;
      categoryTags = ["Culture", "Heritage", "Temple"];
    }

    const scoreVal = rec.score != null ? Math.round(rec.score) : 70;
    let decisionStr = "SUITABLE";
    if (scoreVal >= 90) decisionStr = "HIGHLY RECOMMENDED";
    else if (scoreVal >= 80) decisionStr = "RECOMMENDED";
    else if (scoreVal >= 70) decisionStr = "SUITABLE";
    else if (scoreVal >= 60) decisionStr = "CONSIDER";
    else decisionStr = "NOT RECOMMENDED";

    return {
      topActName,
      topActCat,
      topActDuration,
      travelTimeStr,
      travelKm,
      decisionStr,
      scoreVal,
      categoryTags
    };
  };

  const recommendedRoute = routeRecommendations && routeRecommendations.length > 0 ? routeRecommendations[0] : null;

  return (
    <div style={styles.container}>
      {/* Top Header Bar */}
      <header style={styles.exploreNavHeader}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button onClick={onBack} style={styles.backNavBtn}>
            ← Back
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ ...styles.cardIconBadge, width: 34, height: 34, background: '#10b981' }}>
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

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: isLiveApi ? '#10b981' : '#f59e0b',
            }} />
            <span style={{ fontSize: 12, color: isLiveApi ? '#059669' : '#d97706', fontWeight: 700 }}>
              {isLiveApi ? '🟢 Live Route Engine Connected' : '🟠 Telemetry Active'}
            </span>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <div style={styles.recsMainContainer}>
        {/* Title Header */}
        <div style={{ marginBottom: 24 }}>
          <h1 style={styles.recsTitle}>AI Route Recommendation & Optimization</h1>
          <p style={styles.recsSubtitle}>
            Intelligent multi-destination route sequence optimization, daily schedule planning & AI explainability
          </p>
        </div>

        {/* 1. USER INPUT / PREFERENCES & ROUTE CONTROLS */}
        <div style={styles.topControlCard}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 12, alignItems: 'flex-end' }}>
            {/* Preference Input */}
            <div>
              <label style={styles.controlLabel}>Tell us your preference (optional)</label>
              <div style={styles.inputIconWrapper}>
                <span style={{ fontSize: 16, color: '#059669' }}>🪄</span>
                <input
                  value={userPrefText}
                  onChange={(e) => setUserPrefText(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && fetchRecommendationsData(userPrefText, plannedDate, origin, days, transportMode)}
                  placeholder="I want to go to a quiet cold place"
                  style={styles.prefInputWithIcon}
                />
              </div>
            </div>

            {/* Duration (Days) */}
            <div>
              <label style={styles.controlLabel}>📅 Days</label>
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                style={styles.selectControl}
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
              <label style={styles.controlLabel}>🚗 Transport</label>
              <select
                value={transportMode}
                onChange={(e) => setTransportMode(e.target.value)}
                style={styles.selectControl}
              >
                <option value="car">Car (🚗)</option>
                <option value="bus">Bus (🚌)</option>
                <option value="train">Train (🚆)</option>
              </select>
            </div>

            {/* Visit Date */}
            <div>
              <label style={styles.controlLabel}>🗓️ Visit Date</label>
              <input
                type="date"
                min={tomorrowStr}
                max={maxDateStr}
                value={plannedDate}
                onChange={(e) => {
                  const val = e.target.value;
                  if (!val || val < tomorrowStr) {
                    setPlannedDate(tomorrowStr);
                  } else if (val > maxDateStr) {
                    setPlannedDate(maxDateStr);
                  } else {
                    setPlannedDate(val);
                  }
                }}
                style={styles.dateInputControl}
              />
            </div>

            {/* Main Get Recommendations Action Button */}
            <div>
              <button
                onClick={() => fetchRecommendationsData(userPrefText, plannedDate, origin, days, transportMode)}
                disabled={loadingRecs}
                style={styles.mainActionBtn}
              >
                <span style={{ fontSize: 16 }}>✨</span>
                <span>{loadingRecs ? 'Optimizing...' : 'Get Recommendations'}</span>
              </button>
            </div>
          </div>

          {/* Quick Chip Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
            <button
              onClick={() => {
                const text = 'I want to go to a quiet cold place';
                setUserPrefText(text);
                fetchRecommendationsData(text, plannedDate, origin, days, transportMode);
              }}
              style={styles.controlChipBtn}
            >
              <span style={{ color: '#059669' }}>❄️</span> Cold & Quiet Place
            </button>

            <button
              onClick={() => {
                const text = 'beach and nature adventure';
                setUserPrefText(text);
                fetchRecommendationsData(text, plannedDate, origin, days, transportMode);
              }}
              style={styles.controlChipBtn}
            >
              <span style={{ color: '#059669' }}>🏖️</span> Beach & Nature
            </button>

            {userPrefText && (
              <button
                onClick={() => setUserPrefText('')}
                style={{ ...styles.controlChipBtn, background: '#f1f5f9', color: '#64748b', border: '1px solid #cbd5e1' }}
              >
                › Clear
              </button>
            )}
          </div>
        </div>

        {/* JSON Inspector Toggle commented out for now */}
        {/*
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 10 }}>
          <button
            onClick={() => setShowJsonViewer(!showJsonViewer)}
            style={styles.jsonToggleBtn}
          >
            {showJsonViewer ? 'Hide Backend JSON ▲' : 'Show Backend JSON ▼'}
          </button>
        </div>

        {showJsonViewer && (
          <div style={styles.jsonPanelContainer}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, padding: '14px 18px', background: '#090d16' }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', marginBottom: 6, textTransform: 'uppercase' }}>
                  Request Payload (JSON)
                </div>
                <pre style={styles.codeBlock}>
                  {rawRequestPayload ? JSON.stringify(rawRequestPayload, null, 2) : '// Click Get Recommendations to send request...'}
                </pre>
              </div>

              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: isLiveApi ? '#34d399' : '#fbbf24', marginBottom: 6, textTransform: 'uppercase' }}>
                  Backend JSON Return (POST http://127.0.0.1:5001/assistance/recommend)
                </div>
                <pre style={{ ...styles.codeBlock, borderColor: isLiveApi ? 'rgba(52, 211, 153, 0.4)' : 'rgba(251, 191, 36, 0.4)', color: isLiveApi ? '#6ee7b7' : '#fde68a' }}>
                  {rawResponseJson ? JSON.stringify(rawResponseJson, null, 2) : '// Awaiting response...'}
                </pre>
              </div>
            </div>
          </div>
        )}
        */}

        {/* Loading Indicator State */}
        {loadingRecs && (
          <div style={styles.loadingBox}>
            <div style={{ fontSize: 28, marginBottom: 10 }}>🧭</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
              Optimizing AI Travel Route & Evaluating Feasibility...
            </div>
            <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
              Calculating segment distances, pairwise travel times, backtracking penalties & daily schedule feasibility
            </div>
          </div>
        )}

        {/* INITIAL EMPTY STATE (Before User Clicks Get Recommendations) */}
        {!loadingRecs && !hasSearched && recommendations.length === 0 && !recommendedRoute && (
          <div style={styles.emptyInitialCard}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🗺️</div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
              Ready to Plan Your AI Route?
            </h3>
            <p style={{ fontSize: 13.5, color: '#64748b', margin: 0, maxWidth: '480px', lineHeight: '1.5' }}>
              Enter your preferences above (e.g. <i>"I want to go to a quiet cold place"</i>) and click <strong>Get Recommendations</strong> to generate a complete optimized route & daily travel plan.
            </p>
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {/* 2. PRIMARY RESULT: AI RECOMMENDED ROUTE HERO CARD                          */}
        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {!loadingRecs && hasSearched && recommendedRoute && (
          <div style={styles.routeHeroCard}>
            {/* Header Badge & Score */}
            <div style={styles.routeHeroHeader}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={styles.trophyBadge}>🏆 AI RECOMMENDED ROUTE</span>
                <span style={styles.rankDecisionBadge}>
                  #{recommendedRoute.rank || 1} {recommendedRoute.decision || 'Highly Recommended'}
                </span>
              </div>
              <div style={styles.routeScoreBox}>
                <span style={styles.routeScoreNum}>{recommendedRoute.overall_route_score}</span>
                <span style={styles.routeScoreMax}>/ 100</span>
              </div>
            </div>

            {/* Route Sequence Title */}
            <h2 style={styles.routeSequenceTitle}>
              {recommendedRoute.route_display || (recommendedRoute.route ? recommendedRoute.route.join(' → ') : 'Colombo → Kandy → Nuwara Eliya → Ella')}
            </h2>

            {/* Stat Pills Row (Distance, Time, Days, Feasibility) */}
            <div style={styles.statPillsRow}>
              <span style={styles.statPill}>
                🚗 <strong>{recommendedRoute.total_distance_km} km</strong>
              </span>
              <span style={styles.statPill}>
                ⏱ <strong>{recommendedRoute.total_travel_time}</strong> total travel
              </span>
              <span style={styles.statPill}>
                📅 <strong>{recommendedRoute.days} Days</strong>
              </span>
              <span style={{
                ...styles.statPill,
                background: recommendedRoute.feasible ? '#ecfdf5' : '#fef2f2',
                color: recommendedRoute.feasible ? '#047857' : '#b91c1c',
                borderColor: recommendedRoute.feasible ? '#a7f3d0' : '#fecaca'
              }}>
                {recommendedRoute.feasible ? '✓ Feasible' : '⚠ High Travel Time'}
              </span>
            </div>

            {/* 3. & 4. ROUTE TIMELINE VISUAL SEQUENCE */}
            <div style={styles.sectionDivider}>
              <h3 style={styles.subSectionTitle}>📍 Route Sequence</h3>
              <div style={styles.timelineContainer}>
                {(recommendedRoute.route || []).map((stop, idx) => {
                  const segment = (recommendedRoute.segments || [])[idx];
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

            {/* 5. ROUTE SEGMENTS & INDEPENDENT TRANSFERS */}
            {recommendedRoute.segments && recommendedRoute.segments.length > 0 && (
              <div style={styles.sectionDivider}>
                <h3 style={styles.subSectionTitle}>🚗 Route Segments & Transfers</h3>
                <div style={styles.segmentsGrid}>
                  {recommendedRoute.segments.map((seg, sIdx) => (
                    <div key={sIdx} style={styles.segmentCard}>
                      <div style={styles.segmentHeader}>
                        <span>🚗 {seg.from} → {seg.to}</span>
                        {seg.is_estimated_distance && (
                          <span style={styles.estimatedDistBadge}>Estimated</span>
                        )}
                      </div>
                      <div style={styles.segmentMetricsRow}>
                        <span>📏 <strong>{seg.distance_km} km</strong></span>
                        <span>⏱ <strong>{seg.estimated_travel_time}</strong></span>
                      </div>
                      {seg.warnings && seg.warnings.length > 0 && (
                        <div style={styles.segmentWarningsBox}>
                          {seg.warnings.map((w, wIdx) => (
                            <div key={wIdx} style={{ fontSize: 11.5, color: '#b45309' }}>⚠ {w}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 6. DAILY AI TRAVEL PLAN */}
            {recommendedRoute.daily_plan && recommendedRoute.daily_plan.length > 0 && (
              <div style={styles.sectionDivider}>
                <h3 style={styles.subSectionTitle}>🗓️ Your AI Travel Plan</h3>
                <div style={styles.dailyPlanGrid}>
                  {recommendedRoute.daily_plan.map((dp, dIdx) => (
                    <div key={dIdx} style={styles.dailyPlanCard}>
                      <div style={styles.dayBadge}>DAY {dp.day}</div>
                      <div style={styles.dayRouteHeader}>{dp.route}</div>
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 10 }}>⏱ Travel: {dp.travel_time}</div>
                      
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#334155', marginBottom: 6 }}>Activities:</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {(dp.activities || []).map((act, aIdx) => (
                          <div key={aIdx} style={styles.activityItem}>
                            <span>• {act.name}</span>
                            <span style={{ fontSize: 11.5, color: '#059669', fontWeight: 600 }}>{act.time}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 7. WHY AI RECOMMENDS THIS ROUTE & 8. TRADE-OFFS */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 24 }}>
              {/* 7. Why AI Recommends */}
              <div style={styles.reasonsCard}>
                <h4 style={{ ...styles.cardSubHeader, color: '#047857' }}>Why AI Recommends This Route</h4>
                <ul style={styles.bulletList}>
                  {(recommendedRoute.why_recommended || []).map((reason, rIdx) => (
                    <li key={rIdx} style={styles.whyListItem}>
                      <span style={{ color: '#10b981', fontWeight: 800 }}>✓</span> {reason}
                    </li>
                  ))}
                </ul>
              </div>

              {/* 8. Trade-offs / Things to Consider */}
              {recommendedRoute.tradeoffs && recommendedRoute.tradeoffs.length > 0 && (
                <div style={styles.tradeoffsCard}>
                  <h4 style={{ ...styles.cardSubHeader, color: '#b45309' }}>⚠ Things to Consider</h4>
                  <ul style={styles.bulletList}>
                    {recommendedRoute.tradeoffs.map((to, tIdx) => (
                      <li key={tIdx} style={styles.tradeoffListItem}>
                        <span style={{ color: '#f59e0b', fontWeight: 800 }}>⚠</span> {to}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {/* 9. SECONDARY: SUPPORTING INDIVIDUAL DESTINATION RECOMMENDATIONS              */}
        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {!loadingRecs && hasSearched && recommendations.length > 0 && (
          <div style={{ marginTop: 44 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 18, color: '#2563eb' }}>✨</span>
                <h2 style={{ fontSize: 18, fontWeight: 800, color: '#0f172a', margin: 0 }}>
                  Supporting Destination Details ({recommendations.length})
                </h2>
              </div>
              <div style={{ fontSize: 12.5, color: '#64748b', fontWeight: 600 }}>
                Steps 1–6 Sub-component Evaluations
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {recommendations.map((rec, index) => {
                const defaults = getDestinationDefaults(rec.place, rec);

                const rank = rec.ai_recommendation?.rank || (index + 1);
                const rankBg = rank === 1 ? '#16a34a' : rank === 2 ? '#eab308' : rank === 3 ? '#f97316' : rank === 4 ? '#3b82f6' : '#64748b';

                const overallScore = rec.ai_recommendation?.overall_score || rec.score || defaults.scoreVal;

                const crowdText = rec.crowd_label || (rec.crowd < 110 ? 'Low' : rec.crowd < 200 ? 'Moderate' : 'High');
                const crowdColor = crowdText === 'Low' ? '#166534' : crowdText === 'Moderate' ? '#d97706' : '#dc2626';

                const weatherText = rec.weather && rec.weather !== 'Low' ? rec.weather : 'Good';

                const travelTransport = rec.travel_transport || {
                  estimated_travel_time: defaults.travelTimeStr,
                  distance_km: defaults.travelKm,
                  transport_score: 85,
                };

                const crowdSafety = rec.crowd_safety || {
                  crowd_score: 92,
                  crowd_level: crowdText,
                  safety_score: 90,
                  safety_level: "Safe"
                };

                const activityRecs = rec.activity_recommendations || {
                  top_activity: {
                    name: defaults.topActName,
                    score: 94,
                    category: defaults.topActCat,
                    duration_hours: defaults.topActDuration
                  }
                };

                const topAct = activityRecs.top_activity || {
                  name: defaults.topActName,
                  score: 90,
                  category: defaults.topActCat,
                  duration_hours: defaults.topActDuration
                };

                const eventTiming = rec.event_timing || {
                  best_activity_time: "06:30 - 10:30",
                  best_time_period: "early_morning",
                  timing_score: 95
                };

                const aiRec = rec.ai_recommendation || {
                  overall_score: overallScore,
                  rank: rank,
                  decision: defaults.decisionStr,
                  why_recommended: [
                    "Low crowd & very safe",
                    "Cool climate & good weather"
                  ],
                  tradeoffs: [`Long travel time`]
                };

                const decisionBadgeStr = aiRec.decision ? aiRec.decision.toUpperCase() : defaults.decisionStr;
                const decisionBg =
                  decisionBadgeStr.includes('HIGHLY') ? '#dcfce7' :
                  decisionBadgeStr.includes('RECOMMENDED') ? '#dcfce7' :
                  decisionBadgeStr.includes('SUITABLE') ? '#fef9c3' :
                  decisionBadgeStr.includes('CONSIDER') ? '#ffedd5' : '#fee2e2';

                const decisionColor =
                  decisionBadgeStr.includes('HIGHLY') ? '#15803d' :
                  decisionBadgeStr.includes('RECOMMENDED') ? '#166534' :
                  decisionBadgeStr.includes('SUITABLE') ? '#a16207' :
                  decisionBadgeStr.includes('CONSIDER') ? '#c2410c' : '#b91c1c';

                return (
                  <div key={index} style={styles.recItemCard}>
                    {/* Image Column */}
                    <div style={styles.recImageContainer}>
                      <img
                        src={getPlaceImage(rec.place, rec.image)}
                        alt={rec.place}
                        style={styles.recImage}
                      />
                      <div style={{ ...styles.rankBadge, background: rankBg }}>
                        #{rank}
                      </div>
                    </div>

                    {/* Content Column */}
                    <div style={styles.recInfoCol}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                        <h3 style={styles.recPlaceTitle}>{rec.place}</h3>
                        <span style={{
                          padding: '3px 10px',
                          borderRadius: '12px',
                          fontSize: '11px',
                          fontWeight: '800',
                          background: decisionBg,
                          color: decisionColor,
                        }}>
                          {decisionBadgeStr}
                        </span>
                      </div>

                      <p style={styles.recPlaceDesc}>
                        {rec.desc || `Top travel destination in Sri Lanka with optimal weather & crowd metrics.`}
                      </p>

                      <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                        <span style={styles.subPill}>🚗 {travelTransport.distance_km} km ({travelTransport.estimated_travel_time})</span>
                        <span style={styles.subPill}>👥 Crowd: {crowdSafety.crowd_level}</span>
                        <span style={styles.subPill}>🌤️ Weather: {weatherText}</span>
                        <span style={styles.subPill}>🎯 Top: {topAct.name} ({eventTiming.best_activity_time})</span>
                      </div>
                    </div>

                    {/* Score Box Column */}
                    <div style={styles.scoreCol}>
                      <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600 }}>Dest Score</div>
                      <div style={styles.scoreValue}>
                        {overallScore}<span style={styles.scoreMax}>/100</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Complete Component Styling Definitions ──
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
    margin: '28px auto',
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

  topControlCard: {
    background: '#ffffff',
    borderRadius: '20px',
    border: '1px solid #e2e8f0',
    padding: '22px 24px',
    boxShadow: '0 8px 24px rgba(0,0,0,0.03)',
  },

  controlLabel: {
    fontSize: '12px',
    fontWeight: '700',
    color: '#334155',
    display: 'block',
    marginBottom: '6px',
  },

  inputIconWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    background: '#f8fafc',
    border: '1.5px solid #cbd5e1',
    borderRadius: '10px',
    padding: '0 12px',
    height: '42px',
  },

  prefInputWithIcon: {
    width: '100%',
    border: 'none',
    background: 'transparent',
    fontSize: '13.5px',
    color: '#0f172a',
    outline: 'none',
  },

  selectControl: {
    width: '100%',
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

  dateInputControl: {
    width: '100%',
    boxSizing: 'border-box',
    height: '42px',
    padding: '0 10px',
    borderRadius: '10px',
    border: '1.5px solid #cbd5e1',
    background: '#f8fafc',
    fontSize: '13px',
    color: '#0f172a',
    outline: 'none',
    cursor: 'pointer',
  },

  mainActionBtn: {
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
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },

  controlChipBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '5px 12px',
    borderRadius: '16px',
    border: '1px solid #a7f3d0',
    background: '#ecfdf5',
    color: '#047857',
    fontSize: '12px',
    fontWeight: '600',
    cursor: 'pointer',
  },

  jsonToggleBtn: {
    background: 'rgba(15, 23, 42, 0.06)',
    border: 'none',
    color: '#64748b',
    fontSize: '12px',
    fontWeight: '600',
    padding: '4px 10px',
    borderRadius: '6px',
    cursor: 'pointer',
  },

  jsonPanelContainer: {
    marginTop: '12px',
    background: '#0f172a',
    borderRadius: '16px',
    border: '1px solid #1e293b',
    overflow: 'hidden',
  },

  codeBlock: {
    margin: 0,
    padding: '12px',
    background: '#040810',
    border: '1px solid #1e293b',
    borderRadius: '10px',
    fontFamily: "'Fira Code', 'Consolas', monospace",
    fontSize: '11.5px',
    color: '#38bdf8',
    maxHeight: '180px',
    overflowY: 'auto',
    lineHeight: 1.4,
  },

  loadingBox: {
    marginTop: '28px',
    padding: '48px 24px',
    textAlign: 'center',
    background: '#ffffff',
    borderRadius: '20px',
    border: '1px solid #e2e8f0',
  },

  emptyInitialCard: {
    marginTop: '28px',
    padding: '48px 24px',
    textAlign: 'center',
    background: '#ffffff',
    borderRadius: '20px',
    border: '1px dashed #cbd5e1',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },

  /* Primary Route Hero Card Styles */
  routeHeroCard: {
    marginTop: '28px',
    background: '#ffffff',
    borderRadius: '24px',
    border: '2px solid #10b981',
    padding: '30px',
    boxShadow: '0 20px 40px rgba(16,185,129,0.08)',
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
    marginBottom: '24px',
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
    margin: '0 0 14px 0',
  },

  timelineContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    overflowX: 'auto',
    padding: '14px 18px',
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

  segmentsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
    gap: '14px',
  },

  segmentCard: {
    background: '#f8fafc',
    borderRadius: '14px',
    border: '1px solid #e2e8f0',
    padding: '14px 16px',
  },

  segmentHeader: {
    fontSize: '14px',
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: '8px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  estimatedDistBadge: {
    fontSize: '10px',
    fontWeight: '600',
    background: '#fef3c7',
    color: '#b45309',
    padding: '2px 6px',
    borderRadius: '6px',
  },

  segmentMetricsRow: {
    display: 'flex',
    gap: '16px',
    fontSize: '12.5px',
    color: '#475569',
  },

  segmentWarningsBox: {
    marginTop: '8px',
    paddingTop: '6px',
    borderTop: '1px dashed #cbd5e1',
  },

  dailyPlanGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
    gap: '14px',
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

  /* Supporting Destination Cards */
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
    width: '150px',
    height: '95px',
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
    padding: '2px 8px',
    borderRadius: '10px',
    color: '#ffffff',
    fontSize: '11px',
    fontWeight: '800',
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
    margin: 0,
  },

  recPlaceDesc: {
    fontSize: '12.5px',
    color: '#64748b',
    margin: '4px 0 0 0',
    lineHeight: '1.4',
  },

  subPill: {
    fontSize: '11.5px',
    color: '#475569',
    background: '#f1f5f9',
    padding: '3px 8px',
    borderRadius: '6px',
    fontWeight: '500',
  },

  scoreCol: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-end',
    flexShrink: 0,
    paddingLeft: '16px',
    borderLeft: '1px solid #f1f5f9',
  },

  scoreValue: {
    fontSize: '24px',
    fontWeight: '900',
    color: '#059669',
  },

  scoreMax: {
    fontSize: '12px',
    fontWeight: '500',
    color: '#94a3b8',
  },
};
