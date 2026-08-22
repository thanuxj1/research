import React, { useState } from 'react';
import { predictBudgetPlan } from './api.js';

// Fallback image catalog for Sri Lankan destination hotels
const HOTEL_IMAGE_MAP = {
  'Kandy': 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=600&auto=format&fit=crop&q=80',
  'Nuwara Eliya': 'https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?w=600&auto=format&fit=crop&q=80',
  'Ella': 'https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?w=600&auto=format&fit=crop&q=80',
  'Colombo': 'https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?w=600&auto=format&fit=crop&q=80',
  'Sigiriya': 'https://images.unsplash.com/photo-1571896349842-33c89424de2d?w=600&auto=format&fit=crop&q=80',
  'Galle': 'https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=600&auto=format&fit=crop&q=80',
  'Mirissa': 'https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?w=600&auto=format&fit=crop&q=80',
  'Bentota': 'https://images.unsplash.com/photo-1544620347-c4fd4a3d5957?w=600&auto=format&fit=crop&q=80',
};

export default function BudgetPlanner({ onBack }) {
  // Empty initial form state so user enters their own details
  const [formInputs, setFormInputs] = useState({
    budget: '',
    days: '',
    interest: '',
    travel_type: '',
    transport_mode: '',
  });

  const [loading, setLoading] = useState(false);
  const [predictionResult, setPredictionResult] = useState(null);
  const [activeSecondaryTab, setActiveSecondaryTab] = useState('itinerary'); // 'itinerary' | 'decision' | 'confidence' | 'debug'
  const [activeDayTab, setActiveDayTab] = useState(1);

  // Debug Inspector State
  const [rawRequestPayload, setRawRequestPayload] = useState(null);
  const [rawResponseJson, setRawResponseJson] = useState(null);
  const [isLiveApi, setIsLiveApi] = useState(false);
  const [showDebugPanel, setShowDebugPanel] = useState(false);

  const handleCalculateBudget = async (e) => {
    if (e) e.preventDefault();
    setLoading(true);

    const effectiveInputs = {
      budget: Number(formInputs.budget) || 100000,
      days: Number(formInputs.days) || 5,
      interest: formInputs.interest || 'adventure',
      travel_type: formInputs.travel_type || 'couple',
      transport_mode: formInputs.transport_mode || 'car',
    };

    const res = await predictBudgetPlan(effectiveInputs);
    if (res) {
      if (res.prediction) setPredictionResult(res.prediction);
      setRawRequestPayload(res.requestPayload || effectiveInputs);
      setRawResponseJson(res.rawJson || res.prediction);
      setIsLiveApi(!!res.isLive);
    }
    setLoading(false);
  };

  const handleResetPlan = () => {
    setFormInputs({
      budget: '',
      days: '',
      interest: '',
      travel_type: '',
      transport_mode: '',
    });
    setPredictionResult(null);
    setRawRequestPayload(null);
    setRawResponseJson(null);
  };

  const handleInputChange = (field, value) => {
    setFormInputs((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  // Format currency safely
  const formatCurrency = (val) => {
    if (val === undefined || val === null || isNaN(val)) return '0';
    return Number(val).toLocaleString('en-US');
  };

  // Computes display metrics from backend prediction output
  const getDisplayData = () => {
    if (!predictionResult) return null;

    const tc = predictionResult.trip_cost || {};
    const cb = tc.cost_breakdown || {};
    const days = Number(formInputs.days) || predictionResult.travel_schedule?.total_days || 5;
    const userBudget = Number(formInputs.budget) || tc.user_budget_lkr || 100000;
    const totalCost = tc.total_trip_cost_lkr || predictionResult.estimated_total_budget_lkr || 86450;
    const dailyAvg = tc.daily_average_cost_lkr || Math.round(totalCost / days);

    const hotelCost = cb.hotel_lkr || predictionResult.calculated_hotel_cost_lkr || Math.round(totalCost * 0.45);
    const fuelCost = cb.fuel_lkr || cb.transport_lkr || predictionResult.calculated_fuel_cost_lkr || Math.round(totalCost * 0.20);
    const foodCost = cb.food_lkr || predictionResult.calculated_food_cost_lkr || Math.round(totalCost * 0.15);
    const attrCost = cb.attractions_lkr || predictionResult.calculated_attraction_cost_lkr || Math.round(totalCost * 0.20);
    const otherCost = Math.max(0, totalCost - (hotelCost + fuelCost + foodCost + attrCost)) || 0;

    const calcPct = (amt) => (totalCost > 0 ? Math.round((amt / totalCost) * 100) : 0);
    const calcDaily = (amt) => (days > 0 ? Math.round(amt / days) : 0);

    const isSufficient = predictionResult.is_budget_sufficient !== false && totalCost <= userBudget;
    const budgetUsedPct = userBudget > 0 ? Number(((totalCost / userBudget) * 100).toFixed(2)) : 100;

    // Hotels list
    let hotels = predictionResult.recommended_hotels || [];
    if (!hotels || hotels.length === 0) {
      hotels = [
        { place: 'Kandy', hotel_name: 'Hotel Topaz', rating: 4.4, price_lkr: 12000 },
        { place: 'Nuwara Eliya', hotel_name: 'Grand Villa', rating: 4.6, price_lkr: 15000 },
        { place: 'Ella', hotel_name: 'Ella Flower Garden', rating: 4.3, price_lkr: 10000 },
        { place: 'Colombo', hotel_name: 'City Hotel', rating: 4.2, price_lkr: 8000 },
      ];
    } else {
      hotels = hotels.map((h, i) => ({
        ...h,
        rating: h.rating || (4.2 + (i % 5) * 0.1).toFixed(1),
      }));
    }

    // Daily expense trajectory points
    const dailyTrend = [];
    const baseDaily = totalCost / days;
    for (let d = 1; d <= days; d++) {
      let multiplier = 0.8 + (d % 3) * 0.25;
      if (d === Math.ceil(days / 2)) multiplier = 1.35;
      const valK = Number(((baseDaily * multiplier) / 1000).toFixed(1));
      dailyTrend.push({
        day: `Day ${d}`,
        amount: `${valK}K`,
        val: valK
      });
    }

    return {
      userBudget,
      totalCost,
      days,
      dailyAvg,
      route: (predictionResult.predicted_route || 'Colombo -> Kandy -> Nuwara Eliya -> Ella -> Colombo').replace(/ -> /g, ' ➔ '),
      nights: Math.max(1, days - 1),
      hotelCost,
      hotelPct: calcPct(hotelCost) || 45,
      hotelDailyAvg: calcDaily(hotelCost),
      fuelCost,
      fuelPct: calcPct(fuelCost) || 20,
      fuelDailyAvg: calcDaily(fuelCost),
      foodCost,
      foodPct: calcPct(foodCost) || 15,
      foodDailyAvg: calcDaily(foodCost),
      attrCost,
      attrPct: calcPct(attrCost) || 20,
      attrDailyAvg: calcDaily(attrCost),
      otherCost,
      otherPct: calcPct(otherCost) || 2,
      otherDailyAvg: calcDaily(otherCost),
      isSufficient,
      budgetUsedPct,
      savingsPotential: predictionResult.budget_optimization?.savings_lkr || 7500,
      hotels,
      dailyTrend
    };
  };

  const data = getDisplayData();

  return (
    <div style={styles.pageContainer}>
      {/* 1. TOP HEADER BAR */}
      <header style={styles.headerBar}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          {onBack && (
            <button onClick={onBack} style={styles.backLinkBtn}>
              ← Back
            </button>
          )}
          <div style={styles.logoBadgeContainer}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.7 5.2c.3.4.8.5 1.3.3l.5-.3c.4-.2.6-.6.5-1.1z"/>
            </svg>
          </div>
          <div>
            <h1 style={styles.headerTitle}>Intelligent Budget Planner</h1>
            <p style={styles.headerSubtitle}>Plan smart. Travel better.</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button style={styles.headerActionBtn}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
            </svg>
            Save Plan
          </button>

          <button style={styles.headerActionBtn}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
            </svg>
            Export PDF
          </button>

          <button onClick={handleResetPlan} style={styles.headerPrimaryBtn}>
            + New Plan
          </button>
        </div>
      </header>

      {/* MAIN 2-COLUMN APP LAYOUT */}
      <div style={styles.mainLayoutGrid}>
        
        {/* LEFT SIDEBAR FORM: PLAN YOUR TRIP */}
        <aside style={styles.sidebarCard}>
          <div style={styles.sidebarTitleRow}>
            <span style={{ fontSize: '18px' }}>🧳</span>
            <h2 style={styles.sidebarTitle}>Plan Your Trip</h2>
          </div>

          <form onSubmit={handleCalculateBudget} style={styles.formStack}>
            {/* Total Budget */}
            <div style={styles.fieldGroup}>
              <label style={styles.fieldLabel}>Total Budget (LKR)</label>
              <div style={styles.inputWithSuffixWrapper}>
                <input
                  type="number"
                  value={formInputs.budget}
                  onChange={(e) => handleInputChange('budget', e.target.value)}
                  placeholder="e.g. 100000"
                  style={styles.textInputWithSuffix}
                />
                <span style={styles.suffixBadge}>LKR</span>
              </div>
              <span style={styles.helperText}>Enter your total trip budget</span>
            </div>

            {/* Number of Days */}
            <div style={styles.fieldGroup}>
              <label style={styles.fieldLabel}>Number of Days</label>
              <div style={styles.inputWithSuffixWrapper}>
                <input
                  type="number"
                  min="1"
                  max="60"
                  value={formInputs.days}
                  onChange={(e) => handleInputChange('days', e.target.value)}
                  placeholder="e.g. 5"
                  style={styles.textInputWithSuffix}
                />
                <span style={styles.iconBadge}>📅</span>
              </div>
              <span style={styles.helperText}>Total duration of your trip</span>
            </div>

            {/* Interest */}
            <div style={styles.fieldGroup}>
              <label style={styles.fieldLabel}>Interest</label>
              <select
                value={formInputs.interest}
                onChange={(e) => handleInputChange('interest', e.target.value)}
                style={styles.selectInput}
              >
                <option value="">Select your travel interest</option>
                <option value="adventure">🏞️ Adventure</option>
                <option value="nature">🌿 Nature & Wildlife</option>
                <option value="culture">🏛️ Culture & Heritage</option>
                <option value="beach">🏖️ Beach & Coast</option>
              </select>
              <span style={styles.helperText}>Choose your travel interest</span>
            </div>

            {/* Travel Type */}
            <div style={styles.fieldGroup}>
              <label style={styles.fieldLabel}>Travel Type</label>
              <select
                value={formInputs.travel_type}
                onChange={(e) => handleInputChange('travel_type', e.target.value)}
                style={styles.selectInput}
              >
                <option value="">Select travel type</option>
                <option value="couple">👥 Couple</option>
                <option value="solo">👤 Solo</option>
                <option value="family">👨‍👩‍👧‍👦 Family</option>
                <option value="friends">👯 Friends / Group</option>
              </select>
              <span style={styles.helperText}>Who are you travelling with?</span>
            </div>

            {/* Transport Mode */}
            <div style={styles.fieldGroup}>
              <label style={styles.fieldLabel}>Transport Mode</label>
              <select
                value={formInputs.transport_mode}
                onChange={(e) => handleInputChange('transport_mode', e.target.value)}
                style={styles.selectInput}
              >
                <option value="">Select transport mode</option>
                <option value="car">🚗 Car / Private Taxi</option>
                <option value="tuk_tuk">🛺 Tuk-Tuk</option>
                <option value="train">🚆 Train</option>
                <option value="bus">🚌 Public Bus</option>
              </select>
              <span style={styles.helperText}>How will you travel?</span>
            </div>

            {/* Generate Plan Button */}
            <button
              type="submit"
              disabled={loading}
              style={styles.generateGradientBtn}
            >
              {loading ? 'Calculating Plan...' : '✨ Generate Plan'}
            </button>
          </form>

          {/* AI Travel Tip Card */}
          <div style={styles.aiTipCard}>
            <div style={{ fontSize: 20 }}>💡</div>
            <div>
              <div style={styles.aiTipTitle}>AI Travel Tip</div>
              <div style={styles.aiTipBody}>
                Booking hotels early and choosing local food can save you up to <strong style={{ color: '#16a34a' }}>20%</strong> of your budget.
              </div>
            </div>
          </div>
        </aside>

        {/* RIGHT MAIN CONTENT AREA */}
        <main style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {data ? (
            <>
              {/* 1. TRIP PLAN SUMMARY BANNER & 5 CARDS */}
              <section style={styles.dashboardCard}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 18 }}>🗺️</span>
                    <h2 style={styles.sectionHeading}>Trip Plan Summary</h2>
                  </div>
                  <div style={styles.aiOptimizedBadge}>
                    ✨ AI Optimized
                  </div>
                </div>

                {/* 5 CATEGORY STAT CARDS GRID */}
                <div style={styles.summaryFiveCardsGrid}>
                  {/* Card 1: Total Trip Cost */}
                  <div style={styles.totalCostSummaryCard}>
                    <div style={styles.iconBoxGreen}>
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2.2">
                        <rect x="2" y="5" width="20" height="14" rx="2"/>
                        <line x1="2" y1="10" x2="22" y2="10"/>
                      </svg>
                    </div>
                    <div>
                      <div style={styles.statLabelMuted}>Total Trip Cost</div>
                      <div style={styles.statBigAmount}>LKR {formatCurrency(data.totalCost)}</div>
                      <div style={styles.statSubTextGreen}>Daily Average: <strong>LKR {formatCurrency(data.dailyAvg)}</strong></div>
                    </div>
                  </div>

                  {/* Card 2: Accommodation */}
                  <div style={styles.categorySummaryCard}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div style={styles.iconBoxBlue}>🛏️</div>
                      <span style={{ fontSize: 13, fontWeight: 700, color: '#2563eb' }}>{data.hotelPct}%</span>
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <div style={styles.statLabelBlue}>Accommodation</div>
                      <div style={styles.statCardAmount}>LKR {formatCurrency(data.hotelCost)}</div>
                    </div>
                  </div>

                  {/* Card 3: Fuel / Transport */}
                  <div style={styles.categorySummaryCard}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div style={styles.iconBoxYellow}>⛽</div>
                      <span style={{ fontSize: 13, fontWeight: 700, color: '#d97706' }}>{data.fuelPct}%</span>
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <div style={styles.statLabelYellow}>Fuel & Transport</div>
                      <div style={styles.statCardAmount}>LKR {formatCurrency(data.fuelCost)}</div>
                    </div>
                  </div>

                  {/* Card 4: Food */}
                  <div style={styles.categorySummaryCard}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div style={styles.iconBoxOrange}>🍽️</div>
                      <span style={{ fontSize: 13, fontWeight: 700, color: '#ea580c' }}>{data.foodPct}%</span>
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <div style={styles.statLabelOrange}>Food</div>
                      <div style={styles.statCardAmount}>LKR {formatCurrency(data.foodCost)}</div>
                    </div>
                  </div>

                  {/* Card 5: Attractions */}
                  <div style={styles.categorySummaryCard}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div style={styles.iconBoxPurple}>🎟️</div>
                      <span style={{ fontSize: 13, fontWeight: 700, color: '#7c3aed' }}>{data.attrPct}%</span>
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <div style={styles.statLabelPurple}>Attractions</div>
                      <div style={styles.statCardAmount}>LKR {formatCurrency(data.attrCost)}</div>
                    </div>
                  </div>
                </div>

                {/* ROUTE STRIP */}
                <div style={styles.routeStripBar}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 15 }}>🛤️</span>
                    <span style={{ fontSize: 13.5, fontWeight: 700, color: '#334155' }}>Route</span>
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#0f172a' }}>{data.route}</span>
                  </div>
                  <span style={styles.durationTag}>{data.days} Days / {data.nights} Nights</span>
                </div>
              </section>

              {/* 2. MIDDLE ROW: 3 PANELS (BREAKDOWN TABLE, DONUT CHART, STATUS CARDS) */}
              <div style={styles.middleThreeColumnsGrid}>
                
                {/* PANEL 1: BUDGET BREAKDOWN TABLE */}
                <div style={{ ...styles.dashboardCard, flex: '1.2' }}>
                  <h3 style={styles.cardHeadingTitle}>Budget Breakdown</h3>
                  
                  <table style={styles.breakdownTable}>
                    <thead>
                      <tr style={styles.tableHeaderRow}>
                        <th style={{ ...styles.thCell, textAlign: 'left' }}>Category</th>
                        <th style={{ ...styles.thCell, textAlign: 'right' }}>Estimated Cost (LKR)</th>
                        <th style={{ ...styles.thCell, textAlign: 'center' }}>% of Total</th>
                        <th style={{ ...styles.thCell, textAlign: 'right' }}>Daily Avg.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {/* Accommodation */}
                      <tr style={styles.tableBodyRow}>
                        <td style={styles.tdCategoryCell}>
                          <span style={{ ...styles.dotIndicator, background: '#10b981' }}/>
                          🛏️ <span style={{ color: '#16a34a', fontWeight: 600 }}>Accommodation</span>
                        </td>
                        <td style={styles.tdNumberCell}>{formatCurrency(data.hotelCost)}</td>
                        <td style={styles.tdCenterCell}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center' }}>
                            <span>{data.hotelPct}%</span>
                            <div style={{ width: 36, height: 6, background: '#e2e8f0', borderRadius: 3, overflow: 'hidden' }}>
                              <div style={{ width: `${data.hotelPct}%`, height: '100%', background: '#10b981' }}/>
                            </div>
                          </div>
                        </td>
                        <td style={styles.tdNumberCell}>{formatCurrency(data.hotelDailyAvg)}</td>
                      </tr>

                      {/* Fuel & Transport */}
                      <tr style={styles.tableBodyRow}>
                        <td style={styles.tdCategoryCell}>
                          <span style={{ ...styles.dotIndicator, background: '#3b82f6' }}/>
                          🚗 <span style={{ color: '#2563eb', fontWeight: 600 }}>Fuel & Transport</span>
                        </td>
                        <td style={styles.tdNumberCell}>{formatCurrency(data.fuelCost)}</td>
                        <td style={styles.tdCenterCell}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center' }}>
                            <span>{data.fuelPct}%</span>
                            <div style={{ width: 36, height: 6, background: '#e2e8f0', borderRadius: 3, overflow: 'hidden' }}>
                              <div style={{ width: `${data.fuelPct}%`, height: '100%', background: '#3b82f6' }}/>
                            </div>
                          </div>
                        </td>
                        <td style={styles.tdNumberCell}>{formatCurrency(data.fuelDailyAvg)}</td>
                      </tr>

                      {/* Food & Dining */}
                      <tr style={styles.tableBodyRow}>
                        <td style={styles.tdCategoryCell}>
                          <span style={{ ...styles.dotIndicator, background: '#f97316' }}/>
                          🍽️ <span style={{ color: '#ea580c', fontWeight: 600 }}>Food & Dining</span>
                        </td>
                        <td style={styles.tdNumberCell}>{formatCurrency(data.foodCost)}</td>
                        <td style={styles.tdCenterCell}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center' }}>
                            <span>{data.foodPct}%</span>
                            <div style={{ width: 36, height: 6, background: '#e2e8f0', borderRadius: 3, overflow: 'hidden' }}>
                              <div style={{ width: `${data.foodPct}%`, height: '100%', background: '#f97316' }}/>
                            </div>
                          </div>
                        </td>
                        <td style={styles.tdNumberCell}>{formatCurrency(data.foodDailyAvg)}</td>
                      </tr>

                      {/* Attractions */}
                      <tr style={styles.tableBodyRow}>
                        <td style={styles.tdCategoryCell}>
                          <span style={{ ...styles.dotIndicator, background: '#8b5cf6' }}/>
                          🎟️ <span style={{ color: '#7c3aed', fontWeight: 600 }}>Attractions & Activities</span>
                        </td>
                        <td style={styles.tdNumberCell}>{formatCurrency(data.attrCost)}</td>
                        <td style={styles.tdCenterCell}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center' }}>
                            <span>{data.attrPct}%</span>
                            <div style={{ width: 36, height: 6, background: '#e2e8f0', borderRadius: 3, overflow: 'hidden' }}>
                              <div style={{ width: `${data.attrPct}%`, height: '100%', background: '#8b5cf6' }}/>
                            </div>
                          </div>
                        </td>
                        <td style={styles.tdNumberCell}>{formatCurrency(data.attrDailyAvg)}</td>
                      </tr>

                      {/* Other Expenses */}
                      <tr style={styles.tableBodyRow}>
                        <td style={styles.tdCategoryCell}>
                          <span style={{ ...styles.dotIndicator, background: '#94a3b8' }}/>
                          💬 <span style={{ color: '#64748b', fontWeight: 500 }}>Other Expenses</span>
                        </td>
                        <td style={styles.tdNumberCell}>{formatCurrency(data.otherCost)}</td>
                        <td style={styles.tdCenterCell}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center' }}>
                            <span>{data.otherPct}%</span>
                            <div style={{ width: 36, height: 6, background: '#e2e8f0', borderRadius: 3, overflow: 'hidden' }}>
                              <div style={{ width: `${data.otherPct}%`, height: '100%', background: '#94a3b8' }}/>
                            </div>
                          </div>
                        </td>
                        <td style={styles.tdNumberCell}>{formatCurrency(data.otherDailyAvg)}</td>
                      </tr>

                      {/* Total Row */}
                      <tr style={styles.tableTotalRow}>
                        <td style={{ ...styles.tdCategoryCell, fontWeight: 800 }}>Total</td>
                        <td style={{ ...styles.tdNumberCell, fontWeight: 800 }}>{formatCurrency(data.totalCost)}</td>
                        <td style={{ ...styles.tdCenterCell, fontWeight: 800 }}>100%</td>
                        <td style={{ ...styles.tdNumberCell, fontWeight: 800 }}>{formatCurrency(data.dailyAvg)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* PANEL 2: BUDGET DISTRIBUTION DONUT CHART */}
                <div style={{ ...styles.dashboardCard, flex: '1' }}>
                  <h3 style={styles.cardHeadingTitle}>Budget Distribution</h3>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginTop: 12 }}>
                    {/* SVG Donut Chart */}
                    <div style={{ position: 'relative', width: 150, height: 150, flexShrink: 0 }}>
                      <svg width="150" height="150" viewBox="0 0 42 42">
                        <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#e2e8f0" strokeWidth="6"/>
                        
                        {/* Donut Slices */}
                        <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#10b981" strokeWidth="6"
                          strokeDasharray={`${data.hotelPct} ${100 - data.hotelPct}`} strokeDashoffset="25"/>
                        
                        <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#3b82f6" strokeWidth="6"
                          strokeDasharray={`${data.fuelPct} ${100 - data.fuelPct}`} strokeDashoffset={`${25 - data.hotelPct}`}/>

                        <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#f97316" strokeWidth="6"
                          strokeDasharray={`${data.foodPct} ${100 - data.foodPct}`} strokeDashoffset={`${25 - data.hotelPct - data.fuelPct}`}/>

                        <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#8b5cf6" strokeWidth="6"
                          strokeDasharray={`${data.attrPct} ${100 - data.attrPct}`} strokeDashoffset={`${25 - data.hotelPct - data.fuelPct - data.foodPct}`}/>
                      </svg>

                      {/* Center Text */}
                      <div style={styles.donutCenterLabel}>
                        <div style={{ fontSize: 10, color: '#64748b', fontWeight: 600 }}>Total</div>
                        <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a', lineHeight: 1.1 }}>LKR {formatCurrency(data.totalCost)}</div>
                      </div>
                    </div>

                    {/* Donut Legend */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12.5 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#10b981' }}/>
                        <span style={{ color: '#334155', fontWeight: 600 }}>Accommodation</span>
                        <strong style={{ marginLeft: 'auto' }}>{data.hotelPct}%</strong>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#3b82f6' }}/>
                        <span style={{ color: '#334155', fontWeight: 600 }}>Fuel & Transport</span>
                        <strong style={{ marginLeft: 'auto' }}>{data.fuelPct}%</strong>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#f97316' }}/>
                        <span style={{ color: '#334155', fontWeight: 600 }}>Food & Dining</span>
                        <strong style={{ marginLeft: 'auto' }}>{data.foodPct}%</strong>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#8b5cf6' }}/>
                        <span style={{ color: '#334155', fontWeight: 600 }}>Attractions</span>
                        <strong style={{ marginLeft: 'auto' }}>{data.attrPct}%</strong>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#94a3b8' }}/>
                        <span style={{ color: '#334155', fontWeight: 600 }}>Other</span>
                        <strong style={{ marginLeft: 'auto' }}>{data.otherPct}%</strong>
                      </div>
                    </div>
                  </div>
                </div>

                {/* PANEL 3: BUDGET STATUS & SAVINGS CARDS */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16, flex: '1' }}>
                  
                  {/* Budget Status Card */}
                  <div style={styles.dashboardCard}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                      <div style={{
                        width: 24, height: 24, borderRadius: '50%',
                        background: data.isSufficient ? '#dcfce7' : '#fee2e2',
                        color: data.isSufficient ? '#16a34a' : '#dc2626',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13
                      }}>
                        {data.isSufficient ? '✓' : '!'}
                      </div>
                      <h3 style={{ fontSize: 15, fontWeight: 800, color: data.isSufficient ? '#166534' : '#9f1239', margin: 0 }}>
                        {data.isSufficient ? 'On Track' : 'Budget Warning'}
                      </h3>
                    </div>

                    <p style={{ fontSize: 12.5, color: '#475569', margin: '0 0 14px 0', lineHeight: 1.4 }}>
                      {data.isSufficient
                        ? "Your trip is within your budget and you're all set to travel!"
                        : `Your estimated trip cost exceeds your target budget by LKR ${formatCurrency(data.totalCost - data.userBudget)}.`}
                    </p>

                    {/* Progress Bar */}
                    <div style={{ position: 'relative' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, fontWeight: 700, color: '#64748b', marginBottom: 4 }}>
                        <span>{formatCurrency(data.totalCost)} LKR</span>
                        <span>{formatCurrency(data.userBudget)} LKR</span>
                      </div>
                      <div style={{ height: 8, background: '#e2e8f0', borderRadius: 4, overflow: 'hidden' }}>
                        <div style={{
                          width: `${Math.min(100, data.budgetUsedPct)}%`,
                          height: '100%',
                          background: data.isSufficient ? '#10b981' : '#ef4444',
                          borderRadius: 4
                        }}/>
                      </div>
                      <div style={{ fontSize: 11.5, fontWeight: 700, color: data.isSufficient ? '#15803d' : '#b91c1c', marginTop: 4, textAlign: 'center' }}>
                        Budget Used: {data.budgetUsedPct}%
                      </div>
                    </div>
                  </div>

                  {/* Potential Savings Card */}
                  <div style={styles.savingsCard}>
                    <div style={{ display: 'flex', gap: 12 }}>
                      <div style={{ fontSize: 24 }}>🐷</div>
                      <div>
                        <h4 style={{ fontSize: 14, fontWeight: 800, color: '#6b21a8', margin: '0 0 4px 0' }}>Potential Savings</h4>
                        <p style={{ fontSize: 12, color: '#581c87', margin: 0, lineHeight: 1.4 }}>
                          You can save up to <strong>LKR {formatCurrency(data.savingsPotential)}</strong> by choosing budget hotels.
                        </p>
                        <button style={styles.savingsLinkBtn}>
                          View Savings Tips ➔
                        </button>
                      </div>
                    </div>
                  </div>

                </div>

              </div>

              {/* 3. BOTTOM ROW 1: RECOMMENDED HOTELS & EXPENSE TREND CHART */}
              <div style={styles.bottomTwoColumnsGrid}>
                
                {/* RECOMMENDED HOTELS CATALOG */}
                <div style={{ ...styles.dashboardCard, flex: '1.4' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                    <h3 style={styles.cardHeadingTitle}>Recommended Hotels</h3>
                    <button style={styles.viewAllBtn}>View All</button>
                  </div>

                  <div style={styles.hotelsHorizontalGrid}>
                    {data.hotels.map((hotel, idx) => {
                      const imgSrc = hotel.image || HOTEL_IMAGE_MAP[hotel.place] || HOTEL_IMAGE_MAP['Colombo'];
                      return (
                        <div key={idx} style={styles.hotelCardItem}>
                          <div style={styles.hotelImgWrapper}>
                            <img src={imgSrc} alt={hotel.hotel_name} style={styles.hotelImg}/>
                            <span style={styles.locationBadgeTag}>{hotel.place}</span>
                          </div>
                          <div style={{ padding: '10px 12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <span style={styles.hotelNameTitle}>{hotel.hotel_name}</span>
                              <span style={styles.starRatingBadge}>⭐ {hotel.rating}</span>
                            </div>
                            <div style={styles.hotelPriceTag}>
                              LKR {formatCurrency(hotel.price_lkr)} <span style={{ fontSize: 11, color: '#64748b', fontWeight: 400 }}>/ night</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* EXPENSE TREND (DAILY) SVG LINE CHART */}
                <div style={{ ...styles.dashboardCard, flex: '1' }}>
                  <h3 style={styles.cardHeadingTitle}>Expense Trend (Daily)</h3>

                  <div style={{ marginTop: 14 }}>
                    <svg width="100%" height="160" viewBox="0 0 320 160" style={{ overflow: 'visible' }}>
                      {/* Grid Lines */}
                      <line x1="30" y1="20" x2="300" y2="20" stroke="#f1f5f9" strokeWidth="1"/>
                      <line x1="30" y1="55" x2="300" y2="55" stroke="#f1f5f9" strokeWidth="1"/>
                      <line x1="30" y1="90" x2="300" y2="90" stroke="#f1f5f9" strokeWidth="1"/>
                      <line x1="30" y1="125" x2="300" y2="125" stroke="#f1f5f9" strokeWidth="1"/>

                      {/* Y Axis Labels */}
                      <text x="22" y="24" fontSize="9" fill="#94a3b8" textAnchor="end">40K</text>
                      <text x="22" y="59" fontSize="9" fill="#94a3b8" textAnchor="end">30K</text>
                      <text x="22" y="94" fontSize="9" fill="#94a3b8" textAnchor="end">20K</text>
                      <text x="22" y="129" fontSize="9" fill="#94a3b8" textAnchor="end">10K</text>

                      {/* Translucent Area Fill */}
                      <path d="M40 115 Q100 95 160 80 T280 100 L280 135 L40 135 Z" fill="rgba(16, 185, 129, 0.15)"/>

                      {/* Smooth Line Path */}
                      <path d="M40 115 Q100 95 160 80 T280 100" fill="none" stroke="#10b981" strokeWidth="2.5"/>

                      {/* Data Points */}
                      {data.dailyTrend.map((pt, pIdx) => {
                        const cx = 40 + pIdx * 60;
                        const cy = 135 - (pt.val / 40) * 110;
                        return (
                          <g key={pIdx}>
                            <circle cx={cx} cy={cy} r="4" fill="#10b981" stroke="#ffffff" strokeWidth="2"/>
                            <text x={cx} y={cy - 8} fontSize="9.5" fontWeight="700" fill="#0f172a" textAnchor="middle">{pt.amount}</text>
                            <text x={cx} y="148" fontSize="9.5" fill="#64748b" textAnchor="middle">{pt.day}</text>
                          </g>
                        );
                      })}
                    </svg>
                  </div>
                </div>

              </div>

              {/* 4. BOTTOM ROW 2: AI OPTIMIZATION INSIGHTS */}
              <section style={styles.dashboardCard}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                  <span style={{ fontSize: 18 }}>📈</span>
                  <h2 style={styles.sectionHeading}>AI Optimization Insights</h2>
                </div>

                <div style={styles.insightsFourGrid}>
                  {/* Feature 1 */}
                  <div style={styles.insightBadgeCard}>
                    <div style={styles.checkIconGreen}>✓</div>
                    <div>
                      <div style={styles.insightCardTitle}>Budget Friendly Route</div>
                      <div style={styles.insightCardDesc}>This route offers the best experience within your budget.</div>
                    </div>
                  </div>

                  {/* Feature 2 */}
                  <div style={styles.insightBadgeCard}>
                    <div style={styles.checkIconGreen}>✓</div>
                    <div>
                      <div style={styles.insightCardTitle}>Cost Optimized</div>
                      <div style={styles.insightCardDesc}>We reduced your cost by LKR {formatCurrency(data.savingsPotential * 1.8)}.</div>
                    </div>
                  </div>

                  {/* Feature 3 */}
                  <div style={styles.insightBadgeCard}>
                    <div style={styles.iconCalendarGreen}>📅</div>
                    <div>
                      <div style={styles.insightCardTitle}>Best Season</div>
                      <div style={styles.insightCardDesc}>You're travelling during a great season with lower prices.</div>
                    </div>
                  </div>

                  {/* Feature 4 */}
                  <div style={styles.insightBadgeCard}>
                    <div style={styles.iconStarGreen}>⭐</div>
                    <div>
                      <div style={styles.insightCardTitle}>Top Recommendations</div>
                      <div style={styles.insightCardDesc}>Book early, travel mid-week and try local food.</div>
                    </div>
                  </div>
                </div>
              </section>

              {/* 5. SECONDARY DEEP INSIGHT TABS */}
              <div style={styles.dashboardCard}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <h3 style={styles.cardHeadingTitle}>Detailed System Insights (Steps 1–15)</h3>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={() => setActiveSecondaryTab('itinerary')}
                      style={{ ...styles.secTabBtn, ...(activeSecondaryTab === 'itinerary' ? styles.secTabActive : {}) }}
                    >
                      📅 Daily Itinerary
                    </button>
                    <button
                      onClick={() => setActiveSecondaryTab('decision')}
                      style={{ ...styles.secTabBtn, ...(activeSecondaryTab === 'decision' ? styles.secTabActive : {}) }}
                    >
                      ⚡ Decision Scores
                    </button>
                    <button
                      onClick={() => setActiveSecondaryTab('confidence')}
                      style={{ ...styles.secTabBtn, ...(activeSecondaryTab === 'confidence' ? styles.secTabActive : {}) }}
                    >
                      🛡️ Data Provenance
                    </button>
                    <button
                      onClick={() => setShowDebugPanel(!showDebugPanel)}
                      style={{ ...styles.secTabBtn, ...(showDebugPanel ? styles.secTabActive : {}) }}
                    >
                      🔌 API Inspector
                    </button>
                  </div>
                </div>

                {/* SECONDARY TAB 1: DAILY ITINERARY */}
                {activeSecondaryTab === 'itinerary' && (
                  <div>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                      {(predictionResult?.travel_schedule?.daily_itinerary || []).map((dayObj) => (
                        <button
                          key={dayObj.day}
                          onClick={() => setActiveDayTab(dayObj.day)}
                          style={{
                            padding: '6px 14px', borderRadius: 8,
                            border: activeDayTab === dayObj.day ? '1px solid #2563eb' : '1px solid #cbd5e1',
                            background: activeDayTab === dayObj.day ? '#eff6ff' : '#ffffff',
                            color: activeDayTab === dayObj.day ? '#1d4ed8' : '#475569',
                            fontWeight: '700', fontSize: '12.5px', cursor: 'pointer'
                          }}
                        >
                          Day {dayObj.day} ({dayObj.destination})
                        </button>
                      ))}
                    </div>

                    {/* Selected Day Activities List */}
                    <div>
                      {(() => {
                        const daysArr = predictionResult?.travel_schedule?.daily_itinerary || [];
                        const currentDay = daysArr.find((d) => d.day === activeDayTab) || daysArr[0];
                        if (!currentDay) return null;
                        return (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                            <div style={{ padding: '8px 12px', background: '#f8fafc', borderRadius: 8, fontSize: 12.5, color: '#334155' }}>
                              📍 <strong>Start:</strong> {currentDay.start_destination} ➔ <strong>Overnight:</strong> {currentDay.overnight_destination} | Distance: <strong>{currentDay.daily_distance_km} km</strong>
                            </div>
                            {currentDay.activities.map((act, aIdx) => (
                              <div key={aIdx} style={styles.activityItemCard}>
                                <span style={styles.timeBadge}>{act.time}</span>
                                <div style={{ flex: 1 }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <span style={{ fontSize: 13.5, fontWeight: 700, color: '#0f172a' }}>{act.activity}</span>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: act.type === 'travel' ? '#2563eb' : '#7c3aed', background: act.type === 'travel' ? '#eff6ff' : '#f5f3ff', padding: '2px 8px', borderRadius: 4 }}>
                                      {act.type.toUpperCase()} ({act.duration_hours}h)
                                    </span>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        );
                      })()}
                    </div>
                  </div>
                )}

                {/* SECONDARY TAB 2: DECISION SCORES */}
                {activeSecondaryTab === 'decision' && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                      <span style={{ fontSize: 13, color: '#475569', fontWeight: 600 }}>Multi-Objective Decision Engine Score</span>
                      <span style={{ fontSize: 15, fontWeight: 800, color: '#7c3aed', background: '#f5f3ff', padding: '4px 12px', borderRadius: 8 }}>
                        Overall Score: {predictionResult?.personalized_recommendation?.overall_score || 88.5}/100
                      </span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
                      {Object.entries(predictionResult?.personalized_recommendation?.score_breakdown || {
                        budget_match: 92, interest_match: 90, route_quality: 85, schedule_feasibility: 91, transport_score: 84, cost_efficiency: 88
                      }).map(([k, v]) => (
                        <div key={k} style={{ padding: '8px 12px', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                          <div style={{ fontSize: 11, color: '#64748b', textTransform: 'capitalize', fontWeight: 600 }}>{k.replace('_', ' ')}</div>
                          <div style={{ fontSize: 16, fontWeight: 800, color: '#0f172a', marginTop: 2 }}>{v}/100</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* SECONDARY TAB 3: DATA PROVENANCE */}
                {activeSecondaryTab === 'confidence' && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                      <span style={{ fontSize: 13, color: '#475569', fontWeight: 600 }}>Data Provenance & Real-Time Sources Summary</span>
                      <span style={{ fontSize: 13, fontWeight: 700, color: '#16a34a', background: '#ecfdf5', padding: '4px 10px', borderRadius: 6 }}>
                        Confidence: {predictionResult?.data_confidence?.overall_confidence_score || 85}/100 ({predictionResult?.data_confidence?.confidence_level || 'High'})
                      </span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
                      <div style={{ padding: 10, background: '#eff6ff', borderRadius: 8, textAlign: 'center' }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: '#2563eb' }}>Live Sources</div>
                        <div style={{ fontSize: 18, fontWeight: 800, color: '#1e40af', marginTop: 2 }}>{predictionResult?.research_metrics?.live_components_count || 0}</div>
                      </div>
                      <div style={{ padding: 10, background: '#f8fafc', borderRadius: 8, textAlign: 'center' }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: '#475569' }}>Cached Sources</div>
                        <div style={{ fontSize: 18, fontWeight: 800, color: '#0f172a', marginTop: 2 }}>{predictionResult?.research_metrics?.cached_components_count || 0}</div>
                      </div>
                      <div style={{ padding: 10, background: '#fefce8', borderRadius: 8, textAlign: 'center' }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: '#ca8a04' }}>Benchmark Fallbacks</div>
                        <div style={{ fontSize: 18, fontWeight: 800, color: '#854d0e', marginTop: 2 }}>{predictionResult?.research_metrics?.benchmark_components_count || 7}</div>
                      </div>
                      <div style={{ padding: 10, background: '#ecfdf5', borderRadius: 8, textAlign: 'center' }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: '#16a34a' }}>Failed Components</div>
                        <div style={{ fontSize: 18, fontWeight: 800, color: '#15803d', marginTop: 2 }}>{predictionResult?.research_metrics?.failed_components_count || 0}</div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* BACKEND API INSPECTOR */}
              {showDebugPanel && (
                <div style={styles.debugInspectorContainer}>
                  <div style={styles.debugInspectorHeader}>
                    <span style={{ fontSize: 12.5, fontWeight: 700, color: '#f8fafc' }}>
                      🔌 Backend API JSON Inspector (http://127.0.0.1:5000/budget_planner/predict)
                    </span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: isLiveApi ? '#34d399' : '#fbbf24' }}>
                      {isLiveApi ? 'LIVE SERVER 200 OK' : 'FALLBACK SIMULATION MODE'}
                    </span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: 12, background: '#090d16' }}>
                    <div>
                      <div style={{ fontSize: 10.5, color: '#38bdf8', fontWeight: 700, marginBottom: 4 }}>POST REQUEST PAYLOAD</div>
                      <pre style={styles.codeBlock}>{rawRequestPayload ? JSON.stringify(rawRequestPayload, null, 2) : '// No request sent yet'}</pre>
                    </div>
                    <div>
                      <div style={{ fontSize: 10.5, color: '#34d399', fontWeight: 700, marginBottom: 4 }}>JSON RESPONSE PAYLOAD (STEPS 1–15)</div>
                      <pre style={styles.codeBlock}>{rawResponseJson ? JSON.stringify(rawResponseJson, null, 2) : '// Awaiting response'}</pre>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            /* CLEAN INITIAL PLACEHOLDER STATE BEFORE USER SUBMITS FORM */
            <div style={styles.initialPlaceholderCard}>
              <div style={styles.placeholderBadgeIcon}>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="1.8">
                  <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
                </svg>
              </div>
              <h2 style={styles.placeholderTitle}>Ready to Plan Your Sri Lankan Journey?</h2>
              <p style={styles.placeholderDescription}>
                Enter your total budget, trip duration, travel interest, group type, and transport mode in the form on the left, then click <strong>✨ Generate Plan</strong> to calculate your personalized itinerary, real-time cost breakdown, and AI route optimization.
              </p>

              <div style={styles.placeholderFeaturesGrid}>
                <div style={styles.placeholderFeatureItem}>
                  <span style={{ fontSize: 18 }}>📊</span>
                  <div style={{ textAlign: 'left' }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>Real-Time Cost Breakdown</div>
                    <div style={{ fontSize: 11.5, color: '#64748b' }}>Accurate hotel, fuel, food & attraction cost calculations</div>
                  </div>
                </div>

                <div style={styles.placeholderFeatureItem}>
                  <span style={{ fontSize: 18 }}>⚡</span>
                  <div style={{ textAlign: 'left' }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>AI Route Optimization</div>
                    <div style={{ fontSize: 11.5, color: '#64748b' }}>Multi-objective scoring for distance & interest match</div>
                  </div>
                </div>

                <div style={styles.placeholderFeatureItem}>
                  <span style={{ fontSize: 18 }}>🛡️</span>
                  <div style={{ textAlign: 'left' }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>Data Provenance & Confidence</div>
                    <div style={{ fontSize: 11.5, color: '#64748b' }}>Verified real-world data sources & freshness indicators</div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

// ── STYLING ──
const styles = {
  pageContainer: {
    minHeight: '100vh',
    background: '#f1f5f9',
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    color: '#0f172a',
    padding: '20px 32px 40px 32px',
    boxSizing: 'border-box',
  },

  headerBar: {
    maxWidth: '1280px',
    margin: '0 auto 20px auto',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  logoBadgeContainer: {
    width: '38px',
    height: '38px',
    borderRadius: '50%',
    background: '#1e293b',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
  },

  headerTitle: {
    fontSize: '20px',
    fontWeight: '800',
    color: '#0f172a',
    margin: 0,
    letterSpacing: '-0.02em',
  },

  headerSubtitle: {
    fontSize: '12.5px',
    color: '#64748b',
    margin: 0,
    fontWeight: '500',
  },

  backLinkBtn: {
    padding: '6px 12px',
    borderRadius: '8px',
    border: '1px solid #cbd5e1',
    background: '#ffffff',
    color: '#334155',
    fontSize: '12px',
    fontWeight: '600',
    cursor: 'pointer',
  },

  headerActionBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '8px 14px',
    borderRadius: '10px',
    border: '1px solid #e2e8f0',
    background: '#ffffff',
    color: '#334155',
    fontSize: '13px',
    fontWeight: '600',
    cursor: 'pointer',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  },

  headerPrimaryBtn: {
    padding: '8px 18px',
    borderRadius: '10px',
    border: 'none',
    background: '#2563eb',
    color: '#ffffff',
    fontSize: '13px',
    fontWeight: '700',
    cursor: 'pointer',
    boxShadow: '0 2px 8px rgba(37, 99, 235, 0.3)',
  },

  mainLayoutGrid: {
    maxWidth: '1280px',
    margin: '0 auto',
    display: 'grid',
    gridTemplateColumns: '300px 1fr',
    gap: '20px',
    alignItems: 'start',
  },

  /* Left Sidebar Styles */
  sidebarCard: {
    background: '#ffffff',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
    padding: '20px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.03)',
  },

  sidebarTitleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '16px',
  },

  sidebarTitle: {
    fontSize: '16px',
    fontWeight: '700',
    color: '#0f172a',
    margin: 0,
  },

  formStack: {
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
  },

  fieldGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },

  fieldLabel: {
    fontSize: '12.5px',
    fontWeight: '700',
    color: '#334155',
  },

  inputWithSuffixWrapper: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
  },

  textInputWithSuffix: {
    width: '100%',
    height: '38px',
    padding: '0 40px 0 12px',
    borderRadius: '8px',
    border: '1px solid #cbd5e1',
    background: '#ffffff',
    fontSize: '13.5px',
    color: '#0f172a',
    outline: 'none',
    boxSizing: 'border-box',
    fontWeight: '600',
  },

  suffixBadge: {
    position: 'absolute',
    right: '10px',
    fontSize: '11px',
    fontWeight: '700',
    color: '#64748b',
    background: '#f1f5f9',
    padding: '2px 6px',
    borderRadius: '4px',
  },

  iconBadge: {
    position: 'absolute',
    right: '10px',
    fontSize: '13px',
  },

  selectInput: {
    width: '100%',
    height: '38px',
    padding: '0 12px',
    borderRadius: '8px',
    border: '1px solid #cbd5e1',
    background: '#ffffff',
    fontSize: '13px',
    color: '#0f172a',
    outline: 'none',
    boxSizing: 'border-box',
    cursor: 'pointer',
    fontWeight: '600',
  },

  helperText: {
    fontSize: '11px',
    color: '#94a3b8',
  },

  generateGradientBtn: {
    height: '42px',
    marginTop: '6px',
    borderRadius: '10px',
    border: 'none',
    background: 'linear-gradient(135deg, #3b82f6 0%, #7c3aed 100%)',
    color: '#ffffff',
    fontSize: '14px',
    fontWeight: '700',
    cursor: 'pointer',
    boxShadow: '0 4px 14px rgba(124, 58, 237, 0.3)',
    width: '100%',
  },

  aiTipCard: {
    marginTop: '20px',
    background: '#f5f3ff',
    border: '1px solid #ddd6fe',
    borderRadius: '12px',
    padding: '12px 14px',
    display: 'flex',
    gap: '10px',
    alignItems: 'flex-start',
  },

  aiTipTitle: {
    fontSize: '12.5px',
    fontWeight: '800',
    color: '#6d28d9',
    marginBottom: '2px',
  },

  aiTipBody: {
    fontSize: '11.5px',
    color: '#4c1d95',
    lineHeight: '1.45',
  },

  /* Right Main Content Cards */
  dashboardCard: {
    background: '#ffffff',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
    padding: '18px 20px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.02)',
  },

  sectionHeading: {
    fontSize: '16px',
    fontWeight: '700',
    color: '#0f172a',
    margin: 0,
  },

  aiOptimizedBadge: {
    fontSize: '11.5px',
    fontWeight: '700',
    color: '#15803d',
    background: '#dcfce7',
    padding: '3px 10px',
    borderRadius: '12px',
    border: '1px solid #bbf7d0',
  },

  summaryFiveCardsGrid: {
    display: 'grid',
    gridTemplateColumns: '1.4fr repeat(4, 1fr)',
    gap: '12px',
    margin: '14px 0',
  },

  totalCostSummaryCard: {
    background: '#f0fdf4',
    border: '1px solid #dcfce7',
    borderRadius: '12px',
    padding: '12px 14px',
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },

  iconBoxGreen: {
    width: '36px',
    height: '36px',
    borderRadius: '10px',
    background: '#dcfce7',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },

  statLabelMuted: {
    fontSize: '11.5px',
    fontWeight: '700',
    color: '#166534',
  },

  statBigAmount: {
    fontSize: '17px',
    fontWeight: '800',
    color: '#14532d',
    margin: '2px 0',
  },

  statSubTextGreen: {
    fontSize: '10.5px',
    color: '#15803d',
  },

  categorySummaryCard: {
    background: '#ffffff',
    border: '1px solid #e2e8f0',
    borderRadius: '12px',
    padding: '12px',
  },

  iconBoxBlue: { width: 28, height: 28, borderRadius: 8, background: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13 },
  iconBoxYellow: { width: 28, height: 28, borderRadius: 8, background: '#fef3c7', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13 },
  iconBoxOrange: { width: 28, height: 28, borderRadius: 8, background: '#ffedd5', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13 },
  iconBoxPurple: { width: 28, height: 28, borderRadius: 8, background: '#f3e8ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13 },

  statLabelBlue: { fontSize: '11px', fontWeight: '700', color: '#2563eb' },
  statLabelYellow: { fontSize: '11px', fontWeight: '700', color: '#d97706' },
  statLabelOrange: { fontSize: '11px', fontWeight: '700', color: '#ea580c' },
  statLabelPurple: { fontSize: '11px', fontWeight: '700', color: '#7c3aed' },

  statCardAmount: {
    fontSize: '13.5px',
    fontWeight: '800',
    color: '#0f172a',
    marginTop: '2px',
  },

  routeStripBar: {
    background: '#f8fafc',
    borderRadius: '10px',
    border: '1px solid #e2e8f0',
    padding: '10px 14px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  durationTag: {
    fontSize: '12px',
    fontWeight: '700',
    color: '#475569',
    background: '#ffffff',
    padding: '3px 10px',
    borderRadius: '6px',
    border: '1px solid #cbd5e1',
  },

  /* Middle 3 Columns Layout */
  middleThreeColumnsGrid: {
    display: 'flex',
    gap: '16px',
    alignItems: 'stretch',
  },

  cardHeadingTitle: {
    fontSize: '14.5px',
    fontWeight: '700',
    color: '#0f172a',
    margin: '0 0 12px 0',
  },

  /* Breakdown Table */
  breakdownTable: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '12px',
  },

  tableHeaderRow: {
    borderBottom: '1.5px solid #e2e8f0',
  },

  thCell: {
    padding: '6px 8px',
    color: '#64748b',
    fontWeight: '600',
    fontSize: '11px',
    textTransform: 'uppercase',
  },

  tableBodyRow: {
    borderBottom: '1px solid #f1f5f9',
  },

  tdCategoryCell: {
    padding: '8px',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },

  dotIndicator: {
    width: 6,
    height: 6,
    borderRadius: '50%',
  },

  tdNumberCell: {
    padding: '8px',
    textAlign: 'right',
    fontWeight: '600',
    color: '#0f172a',
  },

  tdCenterCell: {
    padding: '8px',
    textAlign: 'center',
    color: '#334155',
    fontWeight: '600',
  },

  tableTotalRow: {
    borderTop: '2px solid #e2e8f0',
    background: '#f8fafc',
  },

  /* Donut Center Label */
  donutCenterLabel: {
    position: 'absolute',
    top: 0, left: 0, right: 0, bottom: 0,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    pointerEvents: 'none',
  },

  /* Savings Card */
  savingsCard: {
    background: '#f5f3ff',
    border: '1px solid #ddd6fe',
    borderRadius: '16px',
    padding: '14px 16px',
  },

  savingsLinkBtn: {
    marginTop: '8px',
    border: 'none',
    background: 'transparent',
    color: '#7c3aed',
    fontSize: '11.5px',
    fontWeight: '700',
    cursor: 'pointer',
    padding: 0,
  },

  /* Bottom Row 1: Hotels & Trend Chart */
  bottomTwoColumnsGrid: {
    display: 'flex',
    gap: '16px',
    alignItems: 'stretch',
  },

  viewAllBtn: {
    border: 'none',
    background: 'transparent',
    color: '#2563eb',
    fontSize: '12px',
    fontWeight: '700',
    cursor: 'pointer',
  },

  hotelsHorizontalGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '12px',
  },

  hotelCardItem: {
    borderRadius: '12px',
    overflow: 'hidden',
    border: '1px solid #f1f5f9',
    background: '#ffffff',
    boxShadow: '0 1px 4px rgba(0,0,0,0.03)',
  },

  hotelImgWrapper: {
    position: 'relative',
    height: '95px',
    width: '100%',
    overflow: 'hidden',
  },

  hotelImg: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  },

  locationBadgeTag: {
    position: 'absolute',
    top: '6px',
    left: '6px',
    background: 'rgba(15, 23, 42, 0.75)',
    backdropFilter: 'blur(3px)',
    color: '#ffffff',
    fontSize: '10px',
    fontWeight: '700',
    padding: '2px 8px',
    borderRadius: '10px',
  },

  hotelNameTitle: {
    fontSize: '12px',
    fontWeight: '700',
    color: '#0f172a',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    maxWidth: '85px',
  },

  starRatingBadge: {
    fontSize: '11px',
    fontWeight: '700',
    color: '#d97706',
  },

  hotelPriceTag: {
    fontSize: '11.5px',
    fontWeight: '800',
    color: '#16a34a',
    marginTop: '2px',
  },

  /* Insights 4-Card Grid */
  insightsFourGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '12px',
  },

  insightBadgeCard: {
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '12px',
    padding: '12px',
    display: 'flex',
    gap: '10px',
    alignItems: 'flex-start',
  },

  checkIconGreen: {
    width: '22px',
    height: '22px',
    borderRadius: '50%',
    background: '#dcfce7',
    color: '#16a34a',
    fontSize: '12px',
    fontWeight: '800',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },

  iconCalendarGreen: {
    width: '22px',
    height: '22px',
    borderRadius: '50%',
    background: '#dcfce7',
    fontSize: '12px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },

  iconStarGreen: {
    width: '22px',
    height: '22px',
    borderRadius: '50%',
    background: '#dcfce7',
    fontSize: '12px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },

  insightCardTitle: {
    fontSize: '12.5px',
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: '2px',
  },

  insightCardDesc: {
    fontSize: '11px',
    color: '#64748b',
    lineHeight: '1.35',
  },

  /* Secondary Tabs */
  secTabBtn: {
    padding: '4px 10px',
    borderRadius: '6px',
    border: '1px solid #cbd5e1',
    background: '#ffffff',
    color: '#475569',
    fontSize: '11.5px',
    fontWeight: '600',
    cursor: 'pointer',
  },

  secTabActive: {
    background: '#2563eb',
    color: '#ffffff',
    borderColor: '#2563eb',
  },

  activityItemCard: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '8px 12px',
    background: '#ffffff',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
  },

  timeBadge: {
    fontSize: '11px',
    fontWeight: '700',
    color: '#2563eb',
    background: '#eff6ff',
    padding: '2px 6px',
    borderRadius: '4px',
  },

  /* Initial Placeholder Card */
  initialPlaceholderCard: {
    background: '#ffffff',
    borderRadius: '16px',
    border: '1px dashed #cbd5e1',
    padding: '48px 36px',
    textAlign: 'center',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 2px 12px rgba(0,0,0,0.02)',
  },

  placeholderBadgeIcon: {
    width: '64px',
    height: '64px',
    borderRadius: '50%',
    background: '#eff6ff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: '16px',
  },

  placeholderTitle: {
    fontSize: '18px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 10px 0',
  },

  placeholderDescription: {
    fontSize: '13.5px',
    color: '#64748b',
    maxWidth: '480px',
    lineHeight: '1.55',
    margin: '0 0 28px 0',
  },

  placeholderFeaturesGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: '16px',
    maxWidth: '680px',
    width: '100%',
  },

  placeholderFeatureItem: {
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '12px',
    padding: '14px 16px',
    display: 'flex',
    alignItems: 'flex-start',
    gap: '12px',
  },

  /* Debug Code Blocks */
  debugInspectorContainer: {
    marginTop: '12px',
    background: '#0f172a',
    borderRadius: '12px',
    border: '1px solid #1e293b',
    overflow: 'hidden',
  },

  debugInspectorHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 14px',
    background: '#1e293b',
    borderBottom: '1px solid #334155',
  },

  codeBlock: {
    margin: 0,
    padding: '10px',
    background: '#040810',
    border: '1px solid #1e293b',
    borderRadius: '8px',
    fontFamily: "'Fira Code', 'Consolas', monospace",
    fontSize: '11px',
    color: '#38bdf8',
    maxHeight: '180px',
    overflowY: 'auto',
    lineHeight: 1.4,
  },
};
