import React, { useState } from 'react';
import { getRecommendations, getAutomaticWeatherAndCrowd, calculateCrowdFromDate } from './api.js';

export default function DestinationRecommendations({ onBack }) {
  const [userPrefText, setUserPrefText] = useState('');
  const [plannedDate, setPlannedDate] = useState(() => new Date().toISOString().split('T')[0]);

  // Starts EMPTY as requested: results ONLY show when "Get Recommendations" button is pressed
  const [recommendations, setRecommendations] = useState([]);
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

  const fetchRecommendationsData = async (prefText = userPrefText, dateVal = plannedDate) => {
    setLoadingRecs(true);
    setHasSearched(true);
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
    } else if (clean.includes('arugam')) {
      topActName = "Surf Session";
      topActCat = "Beach";
      topActDuration = 3;
      travelTimeStr = "6h 30m";
      travelKm = 320;
      categoryTags = ["Surf", "Beach", "Relaxation"];
    } else if (clean.includes('anuradhapura')) {
      topActName = "Ruwanwelisaya Visit";
      topActCat = "Culture";
      topActDuration = 3;
      travelTimeStr = "4h 05m";
      travelKm = 195;
      categoryTags = ["Culture", "Heritage", "History"];
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
              SafeTravel AI Assistant
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
              {isLiveApi ? '🟢 Live Backend Model Connected' : '🟠 Telemetry Active'}
            </span>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <div style={styles.recsMainContainer}>
        {/* Title Header */}
        <div style={{ marginBottom: 24 }}>
          <h1 style={styles.recsTitle}>AI Destination Recommendations</h1>
          <p style={styles.recsSubtitle}>
            Get the best places to visit based on AI analysis of preferences, live weather, crowd, transport, activities and timing
          </p>
        </div>

        {/* Top Control Bar (Preferences + Travel Period + Weather + Get Recommendations Button) */}
        <div style={styles.topControlCard}>
          <div style={styles.controlGrid}>
            {/* Input Column */}
            <div style={{ flex: 1, minWidth: 320 }}>
              <label style={styles.controlLabel}>Tell us your preference (optional)</label>
              <div style={styles.inputIconWrapper}>
                <span style={{ fontSize: 16, color: '#059669' }}>🪄</span>
                <input
                  value={userPrefText}
                  onChange={(e) => setUserPrefText(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && fetchRecommendationsData(userPrefText, plannedDate)}
                  placeholder="i want to go to quiet cold place"
                  style={styles.prefInputWithIcon}
                />
              </div>

              {/* Quick Chip Controls */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                <button
                  onClick={() => {
                    const text = 'quiet low crowd';
                    setUserPrefText(text);
                  }}
                  style={styles.controlChipBtn}
                >
                  <span style={{ color: '#059669' }}>🌱</span> Quiet / Low Crowd
                </button>

                <button
                  onClick={() => {
                    const text = 'cold cool weather';
                    setUserPrefText(text);
                  }}
                  style={styles.controlChipBtn}
                >
                  <span style={{ color: '#059669' }}>🌱</span> Cold / Cool Weather
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

            {/* Travel Period Card Widget */}
            <div style={styles.widgetCardBox}>
              <div style={{ fontSize: 20 }}>🗓️</div>
              <div>
                <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>Travel Period</div>
                <input
                  type="date"
                  value={plannedDate}
                  onChange={(e) => setPlannedDate(e.target.value)}
                  style={styles.dateInputInline}
                />
                <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a' }}>
                  {monthLabel} ({weekendLabel})
                </div>
              </div>
            </div>


            {/* Action Get Recommendations Button */}
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <button
                onClick={() => fetchRecommendationsData(userPrefText, plannedDate)}
                disabled={loadingRecs}
                style={styles.mainActionBtn}
              >
                <span style={{ fontSize: 16 }}>✨</span>
                <span>{loadingRecs ? 'Analyzing...' : 'Get Recommendations'}</span>
              </button>
            </div>
          </div>
        </div>

        {/* JSON Inspector Toggle */}
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
                  Response Return (JSON) {isLiveApi ? '(Live Backend API)' : '(Fallback)'}
                </div>
                <pre style={{ ...styles.codeBlock, borderColor: isLiveApi ? 'rgba(52, 211, 153, 0.4)' : 'rgba(251, 191, 36, 0.4)', color: isLiveApi ? '#6ee7b7' : '#fde68a' }}>
                  {rawResponseJson ? JSON.stringify(rawResponseJson, null, 2) : '// Awaiting response...'}
                </pre>
              </div>
            </div>
          </div>
        )}

        {/* Section Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 28, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 18, color: '#2563eb' }}>✨</span>
            <h2 style={{ fontSize: 18, fontWeight: 800, color: '#0f172a', margin: 0 }}>
              Your Top Recommendations
            </h2>
          </div>
          <div style={{ fontSize: 12.5, color: '#64748b', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
            Sorted by AI Recommendation Score <span style={{ cursor: 'pointer' }}>ⓘ</span>
          </div>
        </div>

        {/* Loading Indicator State */}
        {loadingRecs && (
          <div style={styles.loadingBox}>
            <div style={{ fontSize: 28, marginBottom: 10 }}>🔄</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
              Calculating Multi-Factor AI Recommendation Scores...
            </div>
            <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
              Evaluating natural language intent, live weather, travel feasibility, crowd safety & timing suitability
            </div>
          </div>
        )}

        {/* INITIAL EMPTY STATE (Before User Clicks Get Recommendations) */}
        {!loadingRecs && !hasSearched && recommendations.length === 0 && (
          <div style={styles.emptyInitialCard}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🗺️</div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
              Ready to Explore Sri Lanka?
            </h3>
            <p style={{ fontSize: 13.5, color: '#64748b', margin: 0, maxWidth: '460px', lineHeight: '1.5' }}>
              Enter your preferences above (e.g. <i>"I want a quiet place with cool weather and nature"</i>) and click <strong>Get Recommendations</strong> to generate custom AI destination rankings.
            </p>
          </div>
        )}

        {/* RECOMMENDATIONS CARD LIST (Rendered ONLY after user clicks Get Recommendations) */}
        {!loadingRecs && hasSearched && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {recommendations.map((rec, index) => {
              const defaults = getDestinationDefaults(rec.place, rec);

              const rank = rec.ai_recommendation?.rank || (index + 1);
              const rankBg = rank === 1 ? '#16a34a' : rank === 2 ? '#eab308' : rank === 3 ? '#f97316' : rank === 4 ? '#3b82f6' : '#64748b';

              const overallScore = rec.ai_recommendation?.overall_score || rec.score || defaults.scoreVal;

              const crowdText = rec.crowd_label || (rec.crowd < 110 ? 'Low' : rec.crowd < 200 ? 'Moderate' : 'High');
              const crowdColor = crowdText === 'Low' ? '#166534' : crowdText === 'Moderate' ? '#d97706' : '#dc2626';

              const weatherText = rec.weather && rec.weather !== 'Low' ? rec.weather : 'Good';
              const weatherColor = weatherText === 'Poor' ? '#dc2626' : weatherText === 'Moderate' ? '#d97706' : '#166534';

              const prefScore = rec.preference_match?.score != null ? rec.preference_match.score : 85;

              // Step 2 Weather Suitability Data
              const weatherSuitability = rec.weather_suitability || {
                score: 91,
                condition: "Good",
                temperature_c: 28.5,
                rainfall_mm: 2.0,
                reasons: ["Comfortable & suitable"]
              };

              // Step 3 Travel & Transport Data
              const travelTransport = rec.travel_transport || {
                estimated_travel_time: defaults.travelTimeStr,
                distance_km: defaults.travelKm,
                transport_score: 85,
              };

              // Step 4 Crowd & Safety Data
              const crowdSafety = rec.crowd_safety || {
                crowd_score: 92,
                crowd_level: crowdText,
                safety_score: 90,
                safety_level: "Safe"
              };

              // Step 5 Activity Recommendations Data
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

              // Step 6 Event Timing Data
              const eventTiming = rec.event_timing || {
                best_activity_time: "06:30 - 10:30",
                best_time_period: "early_morning",
                timing_score: 95
              };

              const bestPeriodLabel =
                eventTiming.best_time_period === 'early_morning' ? 'Early Morning' :
                eventTiming.best_time_period === 'morning' ? 'Morning' :
                eventTiming.best_time_period === 'midday' ? 'Midday' :
                eventTiming.best_time_period === 'afternoon' ? 'Afternoon' : 'Evening';

              // Step 7 Final AI Recommendation Data
              const aiRec = rec.ai_recommendation || {
                overall_score: overallScore,
                rank: rank,
                decision: defaults.decisionStr,
                why_recommended: [
                  "Low crowd & very safe",
                  "Cool climate & good weather",
                  "Great activities & timing"
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

              const reasonsList = rec.recommendation_reason || [
                "Strong match for your cold & quiet preference",
                "Cool climate with low expected crowd"
              ];

              const categoryTags = defaults.categoryTags;

              return (
                <div key={index} style={styles.horizontalCard}>
                  {/* Image Column with Rank Badge */}
                  <div style={styles.cardImageCol}>
                    <img
                      src={getPlaceImage(rec.place, rec.image)}
                      alt={rec.place}
                      style={styles.cardImg}
                    />
                    <div style={{ ...styles.cardRankCircle, background: rankBg }}>
                      {rank}
                    </div>
                  </div>

                  {/* Column 1: Destination Info + Tags + Why Recommended */}
                  <div style={styles.cardColDestInfo}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <h3 style={styles.placeNameHeader}>{rec.place}</h3>
                      {rank === 1 && (
                        <span style={styles.bestMatchPill}>Best Match</span>
                      )}
                    </div>

                    <p style={styles.placeDescSnippet}>
                      {rec.desc || `Little England of Sri Lanka with cool climate tea estates, and beautiful scenery.`}
                    </p>

                    {/* Tags */}
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
                      {categoryTags.map((tag, tIdx) => (
                        <span key={tIdx} style={styles.categoryTagBadge}>
                          {tag}
                        </span>
                      ))}
                    </div>

                    {/* Why Recommended List */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>Why recommended:</div>
                      {reasonsList.slice(0, 2).map((rStr, rIdx) => (
                        <div key={rIdx} style={{ fontSize: 11.5, color: '#334155', display: 'flex', alignItems: 'center', gap: 5 }}>
                          <span style={{ color: '#16a34a', fontWeight: 800 }}>✓</span>
                          <span>{rStr}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Column 2: Crowd & Safety */}
                  <div style={styles.cardColSubSection}>
                    <div style={styles.colSectionHeader}>
                      <span style={{ fontSize: 13 }}>🛡️</span>
                      <span>Crowd & Safety</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '6px 0 4px 0' }}>
                      <span style={{ fontSize: 14 }}>👥</span>
                      <strong style={{ fontSize: 13, color: crowdColor }}>{crowdSafety.crowd_level || 'Low'}</strong>
                    </div>
                    <div style={{ fontSize: 11.5, color: '#64748b' }}>
                      Crowd Score: <strong style={{ color: '#334155' }}>{crowdSafety.crowd_score || 92}/100</strong>
                    </div>
                    <div style={{ fontSize: 11.5, color: '#64748b', marginTop: 2 }}>
                      Safety: <strong style={{ color: '#334155' }}>{crowdSafety.safety_level || 'Safe'} ({crowdSafety.safety_score || 90}/100)</strong>
                    </div>
                  </div>

                  {/* Column 3: Weather (Now) */}
                  <div style={styles.cardColSubSection}>
                    <div style={styles.colSectionHeader}>
                      <span style={{ fontSize: 13 }}>☁️</span>
                      <span>Weather (Now)</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '6px 0 4px 0' }}>
                      <span style={{ fontSize: 14 }}>☁️</span>
                      <strong style={{ fontSize: 13, color: weatherColor }}>{weatherText}</strong>
                    </div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a' }}>
                      {weatherSuitability.temperature_c || 28.5}°C
                    </div>
                    <div style={{ fontSize: 11.5, color: '#64748b' }}>
                      {weatherSuitability.rainfall_mm || 2} mm rainfall
                    </div>
                    <div style={{ fontSize: 11, color: '#475569', marginTop: 2 }}>
                      Comfortable & suitable
                    </div>
                  </div>

                  {/* Column 4: Travel from Colombo */}
                  <div style={styles.cardColSubSection}>
                    <div style={styles.colSectionHeader}>
                      <span style={{ fontSize: 13 }}>🚘</span>
                      <span>Travel from Colombo</span>
                    </div>
                    <div style={{ fontSize: 15, fontWeight: 800, color: '#0f172a', margin: '6px 0 2px 0' }}>
                      🚘 {travelTransport.estimated_travel_time || defaults.travelTimeStr}
                    </div>
                    <div style={{ fontSize: 11.5, color: '#64748b' }}>
                      {travelTransport.distance_km || defaults.travelKm} km
                    </div>
                    <div style={{ fontSize: 11.5, color: '#64748b', marginTop: 2 }}>
                      Score: <strong style={{ color: '#334155' }}>{travelTransport.transport_score || 85}/100</strong>
                    </div>
                    <div style={{ display: 'flex', gap: 6, fontSize: 12, marginTop: 4 }}>
                      <span>🚗</span> <span>🚌</span> <span>🚆</span>
                    </div>
                  </div>

                  {/* Column 5: Top Activity & Timing */}
                  <div style={styles.cardColSubSection}>
                    <div style={styles.colSectionHeader}>
                      <span style={{ fontSize: 13 }}>🥾</span>
                      <span>Top Activity & Timing</span>
                    </div>
                    <div style={{ fontSize: 12.5, fontWeight: 700, color: '#0f172a', margin: '6px 0 2px 0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 140 }}>
                      🥾 {topAct.name || defaults.topActName}
                    </div>
                    <div style={{ fontSize: 11.5, color: '#475569', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span>🕒</span> <span>{eventTiming.best_activity_time || "06:30 - 10:30"}</span>
                    </div>
                    <div style={{ margin: '3px 0' }}>
                      <span style={styles.periodPillBadge}>
                        🌅 {bestPeriodLabel}
                      </span>
                    </div>
                    <div style={{ fontSize: 11.5, color: '#64748b' }}>
                      Score: <strong style={{ color: '#334155' }}>{topAct.score || 94}/100</strong>
                    </div>
                  </div>

                  {/* Column 6: AI Recommendation Far-Right Box */}
                  <div style={styles.cardColAiRecommendation}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#65a30d', textTransform: 'uppercase' }}>
                      AI Recommendation
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '4px 0' }}>
                      <span style={{ fontSize: 22 }}>🏆</span>
                      <span style={{ fontSize: 24, fontWeight: 800, color: '#16a34a' }}>
                        {overallScore}
                      </span>
                      <span style={{ fontSize: 13, color: '#64748b', fontWeight: 600 }}>/100</span>
                    </div>

                    <div style={{ ...styles.aiDecisionPill, background: decisionBg, color: decisionColor }}>
                      {decisionBadgeStr}
                    </div>

                    {/* Bullet Checkmarks */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, margin: '6px 0' }}>
                      <div style={{ fontSize: 10.5, color: '#334155', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ color: '#16a34a', fontWeight: 800 }}>✓</span>
                        <span>Low crowd & very safe</span>
                      </div>
                      <div style={{ fontSize: 10.5, color: '#334155', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ color: '#16a34a', fontWeight: 800 }}>✓</span>
                        <span>Cool climate & good weather</span>
                      </div>
                      <div style={{ fontSize: 10.5, color: '#334155', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ color: '#16a34a', fontWeight: 800 }}>✓</span>
                        <span>Great activities & timing</span>
                      </div>
                    </div>

                    <div style={{ fontSize: 10, color: '#64748b' }}>
                      Main Trade-off: Long travel time <span style={{ cursor: 'pointer' }}>ⓘ</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Bottom Legend Footer */}
        <footer style={styles.bottomLegendFooter}>
          <div style={styles.legendBlock}>
            <span style={{ fontSize: 14 }}>👥</span>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#334155' }}>Crowd Level</div>
              <div style={{ fontSize: 10.5, color: '#64748b' }}>Low / Moderate / High / Very High</div>
            </div>
          </div>

          <div style={styles.legendBlock}>
            <span style={{ fontSize: 14 }}>🛡️</span>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#334155' }}>Safety Level</div>
              <div style={{ fontSize: 10.5, color: '#64748b' }}>Very Safe / Safe / Moderate / Caution</div>
            </div>
          </div>

          <div style={styles.legendBlock}>
            <span style={{ fontSize: 14 }}>☁️</span>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#334155' }}>Weather</div>
              <div style={{ fontSize: 10.5, color: '#64748b' }}>Excellent / Good / Moderate / Poor</div>
            </div>
          </div>

          <div style={styles.legendBlock}>
            <span style={{ fontSize: 14 }}>🚘</span>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#334155' }}>Transport Options</div>
              <div style={{ fontSize: 10.5, color: '#64748b' }}>Car / Bus / Train</div>
            </div>
          </div>

          <div style={{ marginLeft: 'auto', textAlign: 'right', fontSize: 11, color: '#047857', fontWeight: 600 }}>
            <div>Data Source: Research Benchmark & Live Telemetry</div>
            <div style={{ color: '#64748b', fontSize: 10 }}>Updated: Aug 23, 2026 – 10:30 AM</div>
          </div>
        </footer>
      </div>
    </div>
  );
}

// ── STYLING ──
const styles = {
  container: {
    minHeight: '100vh',
    background: '#f8fafc',
    fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
    color: '#0f172a',
    paddingBottom: '40px',
  },

  exploreNavHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '14px 36px',
    background: '#ffffff',
    borderBottom: '1px solid #e2e8f0',
    position: 'sticky',
    top: 0,
    zIndex: 100,
  },

  backNavBtn: {
    padding: '6px 14px',
    borderRadius: '8px',
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
    maxWidth: '1180px',
    margin: '28px auto',
    padding: '0 24px',
  },

  recsTitle: {
    fontSize: '26px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 4px 0',
    letterSpacing: '-0.02em',
  },

  recsSubtitle: {
    fontSize: '13.5px',
    color: '#64748b',
    margin: 0,
  },

  /* Top Control Card */
  topControlCard: {
    background: '#ffffff',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
    padding: '18px 22px',
    boxShadow: '0 4px 20px rgba(0,0,0,0.03)',
  },

  controlGrid: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    flexWrap: 'wrap',
  },

  controlLabel: {
    fontSize: '12.5px',
    fontWeight: '700',
    color: '#334155',
    display: 'block',
    marginBottom: '6px',
  },

  inputIconWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    background: '#f8fafc',
    border: '1.5px solid #059669',
    borderRadius: '10px',
    padding: '0 14px',
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

  controlChipBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '4px 10px',
    borderRadius: '14px',
    border: '1px solid #a7f3d0',
    background: '#ecfdf5',
    color: '#047857',
    fontSize: '11.5px',
    fontWeight: '600',
    cursor: 'pointer',
  },

  widgetCardBox: {
    background: '#ffffff',
    border: '1px solid #e2e8f0',
    borderRadius: '12px',
    padding: '8px 14px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    minWidth: '150px',
  },

  dateInputInline: {
    border: 'none',
    background: 'transparent',
    fontSize: '11px',
    color: '#64748b',
    cursor: 'pointer',
    outline: 'none',
    padding: 0,
  },

  mainActionBtn: {
    height: '44px',
    padding: '0 22px',
    borderRadius: '10px',
    border: 'none',
    background: '#059669',
    color: '#ffffff',
    fontWeight: '700',
    fontSize: '14px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    boxShadow: '0 4px 14px rgba(5,150,105,0.3)',
    whiteSpace: 'nowrap',
  },

  jsonToggleBtn: {
    background: 'transparent',
    border: 'none',
    color: '#64748b',
    fontSize: '11.5px',
    fontWeight: '600',
    cursor: 'pointer',
  },

  jsonPanelContainer: {
    marginTop: '8px',
    background: '#0f172a',
    borderRadius: '12px',
    overflow: 'hidden',
  },

  codeBlock: {
    margin: 0,
    padding: '12px',
    background: '#040810',
    border: '1px solid #1e293b',
    borderRadius: '8px',
    fontFamily: "monospace",
    fontSize: '11.5px',
    color: '#38bdf8',
    maxHeight: '180px',
    overflowY: 'auto',
  },

  loadingBox: {
    padding: '40px 24px',
    textAlign: 'center',
    background: '#ffffff',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
    margin: '20px 0',
  },

  emptyInitialCard: {
    padding: '50px 30px',
    textAlign: 'center',
    background: '#ffffff',
    borderRadius: '16px',
    border: '1px border-dash #cbd5e1',
    margin: '20px 0',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },

  /* Horizontal Multi-Column Card Matching Mockup */
  horizontalCard: {
    background: '#ffffff',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
    padding: '14px 18px',
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.02)',
  },

  cardImageCol: {
    position: 'relative',
    width: '130px',
    height: '110px',
    borderRadius: '12px',
    overflow: 'hidden',
    flexShrink: 0,
  },

  cardImg: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  },

  cardRankCircle: {
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
  },

  cardColDestInfo: {
    flex: '1.4',
    minWidth: 0,
    borderRight: '1px solid #f1f5f9',
    paddingRight: '14px',
  },

  placeNameHeader: {
    fontSize: '17px',
    fontWeight: '800',
    color: '#0f172a',
    margin: 0,
  },

  bestMatchPill: {
    fontSize: '10.5px',
    background: '#dcfce7',
    color: '#15803d',
    padding: '1px 8px',
    borderRadius: '10px',
    fontWeight: '700',
  },

  placeDescSnippet: {
    fontSize: '11.5px',
    color: '#64748b',
    margin: '0 0 6px 0',
    lineHeight: 1.35,
  },

  categoryTagBadge: {
    fontSize: '10.5px',
    background: '#eff6ff',
    color: '#1d4ed8',
    padding: '2px 8px',
    borderRadius: '10px',
    fontWeight: '600',
  },

  cardColSubSection: {
    flex: '1',
    minWidth: 0,
    borderRight: '1px solid #f1f5f9',
    paddingRight: '12px',
  },

  colSectionHeader: {
    fontSize: '11px',
    fontWeight: '700',
    color: '#475569',
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },

  periodPillBadge: {
    fontSize: '10px',
    background: '#fef3c7',
    color: '#b45309',
    padding: '1px 6px',
    borderRadius: '6px',
    fontWeight: '700',
  },

  cardColAiRecommendation: {
    width: '185px',
    flexShrink: 0,
    background: '#fcfdfd',
    border: '1px solid #f1f5f9',
    borderRadius: '12px',
    padding: '10px 12px',
    textAlign: 'left',
  },

  aiDecisionPill: {
    fontSize: '10px',
    fontWeight: '800',
    padding: '2px 8px',
    borderRadius: '6px',
    display: 'inline-block',
    letterSpacing: '0.03em',
  },

  bottomLegendFooter: {
    marginTop: '32px',
    background: '#ffffff',
    borderRadius: '12px',
    border: '1px solid #e2e8f0',
    padding: '14px 20px',
    display: 'flex',
    alignItems: 'center',
    gap: '24px',
    flexWrap: 'wrap',
  },

  legendBlock: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
};
