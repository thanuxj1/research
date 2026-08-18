import React, { useState, useEffect } from 'react';
import { predictBudgetPlan } from './api.js';

export default function BudgetPlanner({ onBack }) {
  // Input Form State matching backend schema
  const [formInputs, setFormInputs] = useState({
    budget: 120000,
    days: 5,
    interest: 'nature',
    travel_type: 'family',
    transport_mode: 'car',
  });

  const [loading, setLoading] = useState(false);
  const [isLiveApi, setIsLiveApi] = useState(false);
  const [predictionResult, setPredictionResult] = useState(null);

  // Debug JSON Viewer state
  const [rawResponseJson, setRawResponseJson] = useState(null);
  const [rawRequestPayload, setRawRequestPayload] = useState(null);
  const [showJsonViewer, setShowJsonViewer] = useState(true);

  // Auto calculate on mount
  useEffect(() => {
    handleCalculateBudget();
  }, []);

  const handleCalculateBudget = async (customInputs = formInputs) => {
    setLoading(true);
    const res = await predictBudgetPlan(customInputs);
    setPredictionResult(res.prediction || null);
    setIsLiveApi(res.isLive);
    setRawResponseJson(res.rawJson || null);
    setRawRequestPayload(res.requestPayload || null);
    setLoading(false);
  };

  const handleInputChange = (field, value) => {
    setFormInputs((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  return (
    <div style={styles.container}>
      {/* Navigation Header */}
      <header style={styles.navHeader}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button onClick={onBack} style={styles.backNavBtn}>
            ← Back
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ ...styles.iconBadge, background: '#2563eb' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.2">
                <rect x="4" y="2" width="16" height="20" rx="2"></rect>
                <line x1="8" y1="6" x2="16" y2="6"></line>
                <line x1="16" y1="14" x2="16" y2="18"></line>
              </svg>
            </div>
            <span style={{ fontSize: 16, fontWeight: 700, color: '#0f172a' }}>
              SafeTravel Budget AI
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
            {isLiveApi ? '🟢 Live Budget API Connected (http://127.0.0.1:5000)' : '🟠 Prediction Simulation'}
          </span>
        </div>
      </header>

      {/* Main Content Area */}
      <div style={styles.mainContainer}>
        {/* Title Header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={styles.pageTitle}>Intelligent Budget Planner</h1>
          <p style={styles.pageSubtitle}>
            Plan your trip with AI-powered budget estimation, route prediction, and hotel suggestions
          </p>
        </div>

        {/* Form Input Card */}
        <div style={styles.formCard}>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: '#0f172a', margin: '0 0 16px 0' }}>
            Trip Planning Parameters
          </h2>

          <div style={styles.formGrid}>
            {/* 1. Total Budget */}
            <div>
              <label style={styles.fieldLabel}>Total Budget (LKR)</label>
              <input
                type="number"
                value={formInputs.budget}
                onChange={(e) => handleInputChange('budget', e.target.value)}
                placeholder="120000"
                style={styles.fieldInput}
              />
            </div>

            {/* 2. Days */}
            <div>
              <label style={styles.fieldLabel}>Duration (Days)</label>
              <input
                type="number"
                min="1"
                max="30"
                value={formInputs.days}
                onChange={(e) => handleInputChange('days', e.target.value)}
                placeholder="5"
                style={styles.fieldInput}
              />
            </div>

            {/* 3. Interest */}
            <div>
              <label style={styles.fieldLabel}>Primary Interest</label>
              <select
                value={formInputs.interest}
                onChange={(e) => handleInputChange('interest', e.target.value)}
                style={styles.fieldSelect}
              >
                <option value="nature">🌿 Nature & Wildlife</option>
                <option value="beach">🏖️ Beaches & Coast</option>
                <option value="culture">🏛️ Culture & Heritage</option>
                <option value="adventure">🧗 Adventure & Hikes</option>
              </select>
            </div>

            {/* 4. Travel Type */}
            <div>
              <label style={styles.fieldLabel}>Travel Group Type</label>
              <select
                value={formInputs.travel_type}
                onChange={(e) => handleInputChange('travel_type', e.target.value)}
                style={styles.fieldSelect}
              >
                <option value="family">👨‍👩‍👧‍👦 Family Trip</option>
                <option value="solo">👨 Solo Traveler</option>
                <option value="couple">💑 Couple</option>
                <option value="friends">👥 Group / Friends</option>
              </select>
            </div>

            {/* 5. Transport Mode */}
            <div>
              <label style={styles.fieldLabel}>Transport Mode</label>
              <select
                value={formInputs.transport_mode}
                onChange={(e) => handleInputChange('transport_mode', e.target.value)}
                style={styles.fieldSelect}
              >
                <option value="car">🚗 Private Car / Taxi</option>
                <option value="tuk_tuk">🛺 Tuk-Tuk</option>
                <option value="train">🚆 Scenic Train</option>
                <option value="bus">🚌 Public Bus</option>
              </select>
            </div>
          </div>

          <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={() => handleCalculateBudget()}
              disabled={loading}
              style={styles.submitBtn}
            >
              {loading ? 'Calculating Route & Budget...' : 'Calculate Route & Budget'}
            </button>
          </div>
        </div>

        {/* ── BACKEND JSON RETURN VIEWER PANEL ── */}
        <div style={styles.jsonPanelContainer}>
          <div style={styles.jsonPanelHeader}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 16 }}>🔌</span>
              <strong style={{ fontSize: 13, color: '#f8fafc' }}>
                Backend JSON Return (POST http://127.0.0.1:5000/budget_planner/predict)
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
                  {rawResponseJson ? JSON.stringify(rawResponseJson, null, 2) : '// Awaiting response...'}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* Prediction Results Section */}
        {predictionResult && (
          <div style={{ marginTop: 32 }}>
            <h2 style={{ fontSize: 20, fontWeight: 700, color: '#0f172a', marginBottom: 16 }}>
              AI Predicted Route & Budget Breakdown
            </h2>

            {/* 1. Predicted Route Banner */}
            <div style={styles.routeBanner}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#1d4ed8', textTransform: 'uppercase', marginBottom: 8 }}>
                🗺️ Predicted Itinerary Route
              </div>
              <div style={styles.routePillContainer}>
                {predictionResult.predicted_route.split(' -> ').map((stop, i, arr) => (
                  <React.Fragment key={i}>
                    <span style={styles.routeStopPill}>📍 {stop}</span>
                    {i < arr.length - 1 && <span style={styles.routeArrow}>➔</span>}
                  </React.Fragment>
                ))}
              </div>
            </div>

            {/* 2. Budget Metrics Summary */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 20 }}>
              <div style={styles.metricCard}>
                <div style={{ fontSize: 12, color: '#64748b', fontWeight: 600 }}>Estimated Total Budget</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#2563eb', marginTop: 4 }}>
                  Rs. {Number(predictionResult.estimated_total_budget_lkr).toLocaleString('en-US')} <span style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>LKR</span>
                </div>
              </div>

              <div style={styles.metricCard}>
                <div style={{ fontSize: 12, color: '#64748b', fontWeight: 600 }}>Daily Budget Rate</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#059669', marginTop: 4 }}>
                  Rs. {Number(predictionResult.estimated_daily_budget_lkr).toLocaleString('en-US')} <span style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>LKR / day</span>
                </div>
              </div>
            </div>

            {/* 3. Category Cost Breakdown Grid */}
            <div style={{ marginTop: 24 }}>
              <h3 style={{ fontSize: 16, fontWeight: 700, color: '#0f172a', marginBottom: 12 }}>
                Estimated Cost Breakdown
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
                <div style={styles.categoryCostBox}>
                  <span style={{ fontSize: 20 }}>🏨</span>
                  <div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>Hotel Accommodations</div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
                      Rs. {Number(predictionResult.estimated_hotel_cost_lkr).toLocaleString('en-US')} LKR
                    </div>
                  </div>
                </div>

                <div style={styles.categoryCostBox}>
                  <span style={{ fontSize: 20 }}>🚗</span>
                  <div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>Fuel & Transport</div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
                      Rs. {Number(predictionResult.estimated_fuel_cost_lkr).toLocaleString('en-US')} LKR
                    </div>
                  </div>
                </div>

                <div style={styles.categoryCostBox}>
                  <span style={{ fontSize: 20 }}>🍽️</span>
                  <div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>Food & Dining</div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
                      Rs. {Number(predictionResult.estimated_food_cost_lkr).toLocaleString('en-US')} LKR
                    </div>
                  </div>
                </div>

                <div style={styles.categoryCostBox}>
                  <span style={{ fontSize: 20 }}>🎟️</span>
                  <div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>Attractions & Tickets</div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
                      Rs. {Number(predictionResult.estimated_attraction_cost_lkr).toLocaleString('en-US')} LKR
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 4. Recommended Hotels */}
            {predictionResult.recommended_hotels && predictionResult.recommended_hotels.length > 0 && (
              <div style={{ marginTop: 28 }}>
                <h3 style={{ fontSize: 16, fontWeight: 700, color: '#0f172a', marginBottom: 14 }}>
                  Recommended Lodging & Hotels
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
                  {predictionResult.recommended_hotels.map((hotel, idx) => (
                    <div key={idx} style={styles.hotelCard}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <span style={styles.hotelPlaceBadge}>📍 {hotel.place}</span>
                        <span style={{ fontSize: 13, fontWeight: 700, color: '#2563eb' }}>
                          Rs. {Number(hotel.price_lkr).toLocaleString('en-US')} LKR
                        </span>
                      </div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
                        {hotel.hotel_name}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Styles strictly following app design standards ──
const styles = {
  container: {
    minHeight: '100vh',
    background: '#ffffff',
    fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
    color: '#0f172a',
    paddingBottom: '40px',
  },

  navHeader: {
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

  iconBadge: {
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },

  mainContainer: {
    maxWidth: '1080px',
    margin: '36px auto',
    padding: '0 32px',
  },

  pageTitle: {
    fontSize: '28px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 6px 0',
    letterSpacing: '-0.02em',
  },

  pageSubtitle: {
    fontSize: '14.5px',
    color: '#64748b',
    margin: 0,
  },

  formCard: {
    background: '#ffffff',
    borderRadius: '20px',
    border: '1px solid #e2e8f0',
    padding: '24px 28px',
    boxShadow: '0 10px 30px rgba(0,0,0,0.03)',
  },

  formGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: '16px',
  },

  fieldLabel: {
    fontSize: '13px',
    fontWeight: '700',
    color: '#334155',
    display: 'block',
    marginBottom: '8px',
  },

  fieldInput: {
    width: '100%',
    boxSizing: 'border-box',
    height: '44px',
    padding: '0 14px',
    borderRadius: '10px',
    border: '1.5px solid #cbd5e1',
    background: '#f8fafc',
    fontSize: '14px',
    color: '#0f172a',
    outline: 'none',
  },

  fieldSelect: {
    width: '100%',
    boxSizing: 'border-box',
    height: '44px',
    padding: '0 14px',
    borderRadius: '10px',
    border: '1.5px solid #cbd5e1',
    background: '#f8fafc',
    fontSize: '14px',
    color: '#0f172a',
    outline: 'none',
    cursor: 'pointer',
  },

  submitBtn: {
    height: '46px',
    padding: '0 28px',
    borderRadius: '12px',
    border: 'none',
    background: '#2563eb',
    color: '#ffffff',
    fontWeight: '700',
    fontSize: '14px',
    cursor: 'pointer',
    boxShadow: '0 4px 14px rgba(37,99,235,0.25)',
  },

  /* JSON Viewer Styles */
  jsonPanelContainer: {
    marginTop: '20px',
    background: '#0f172a',
    borderRadius: '16px',
    border: '1px solid #1e293b',
    overflow: 'hidden',
  },

  jsonPanelHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 20px',
    background: '#1e293b',
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

  /* Prediction Results Styles */
  routeBanner: {
    background: '#eff6ff',
    border: '1.5px solid #bfdbfe',
    borderRadius: '16px',
    padding: '20px 24px',
  },

  routePillContainer: {
    display: 'flex',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '10px',
  },

  routeStopPill: {
    background: '#ffffff',
    border: '1px solid #93c5fd',
    padding: '8px 16px',
    borderRadius: '20px',
    fontSize: '14px',
    fontWeight: '700',
    color: '#1e40af',
    boxShadow: '0 2px 6px rgba(37,99,235,0.08)',
  },

  routeArrow: {
    color: '#3b82f6',
    fontSize: '16px',
    fontWeight: '800',
  },

  metricCard: {
    background: '#ffffff',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
    padding: '20px 24px',
    boxShadow: '0 4px 14px rgba(0,0,0,0.03)',
  },

  categoryCostBox: {
    background: '#f8fafc',
    borderRadius: '14px',
    border: '1px solid #e2e8f0',
    padding: '16px',
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },

  hotelCard: {
    background: '#ffffff',
    borderRadius: '14px',
    border: '1px solid #e2e8f0',
    padding: '16px',
    boxShadow: '0 4px 14px rgba(0,0,0,0.03)',
  },

  hotelPlaceBadge: {
    fontSize: '11px',
    fontWeight: '700',
    color: '#475569',
    background: '#f1f5f9',
    padding: '3px 8px',
    borderRadius: '8px',
  },
};
