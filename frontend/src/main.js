import { SafetyMap, isAccessibleWebUrl } from './map.js';

const API = 'http://localhost:8000/api/v1';

/* ── Auto-select current month ──────────────────────────── */
(function setCurrentMonth() {
  const sel = document.getElementById('adv-month');
  if (sel) sel.value = String(new Date().getMonth() + 1);
})();

/* ── Tab switching ──────────────────────────────────────── */
const tabs = document.querySelectorAll('.nav-tab');
const tabContents = document.querySelectorAll('.tab-content');

tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    const target = tab.dataset.tab;
    tabs.forEach(t => t.classList.remove('active'));
    tabContents.forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${target}`).classList.add('active');
    if (target === 'heatmap' && map && map.map) {
      setTimeout(() => map.map.invalidateSize(), 50);
    }
    if (target === 'admin') loadDashboard();
  });
});

/* ── Heatmap Tab ────────────────────────────────────────── */
const map        = new SafetyMap('map-container');
const demoSelect = document.getElementById('demographic-select');
const warnList   = document.getElementById('warnings-list');
const statZones  = document.getElementById('stat-zones');
const statReports= document.getElementById('stat-reports');
const lastUpdEl  = document.getElementById('last-updated');

// Risk filter chips
const chips = document.querySelectorAll('.chip');
const filters = { high: true, med: true };
chips.forEach(chip => {
  chip.addEventListener('click', () => {
    chip.classList.toggle('active');
    const key = chip.dataset.risk;
    filters[key] = chip.classList.contains('active');
    map.setFilters({ ...filters });
  });
});

/* ── District Choropleth (risk-per-district, replaces "everything red" clusters) ── */
async function fetchDistrictRiskMap() {
  try {
    const res = await fetch(`${API}/districts/risk-map`);
    if (!res.ok) throw new Error(res.statusText);
    const geojson = await res.json();
    map.renderDistrictChoropleth(geojson);
  } catch (err) {
    console.warn('[DistrictMap] Could not reach backend.', err);
  }
}

const choroplethToggle = document.getElementById('toggle-choropleth');
if (choroplethToggle) {
  choroplethToggle.addEventListener('change', () => {
    map.toggleDistrictChoropleth(choroplethToggle.checked);
  });
}

fetchDistrictRiskMap();

async function fetchHeatmap() {
  const demo = demoSelect.value;
  try {
    const res = await fetch(`${API}/safety/heatmap?demographic=${encodeURIComponent(demo)}`);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    map.updateHeatmap(data);
    renderWarnings(data);
    statZones.querySelector('.stat-num').textContent = data.length;
    lastUpdEl.textContent = 'Updated ' + new Date().toLocaleTimeString();
  } catch (err) {
    console.warn('[Heatmap] Could not reach backend.', err);
    warnList.innerHTML = '<li class="warnings-placeholder">Backend offline — no live data available.</li>';
    statZones.querySelector('.stat-num').textContent = '—';
    lastUpdEl.textContent = 'Offline';
  }
}

function renderWarnings(zones) {
  const high = zones.filter(z => z.risk_score >= 0.7);
  if (high.length === 0) {
    warnList.innerHTML = '<li class="warnings-placeholder">No high-risk warnings for your profile.</li>';
    return;
  }
  const LABELS = {
    gem_scam:'💎 Gem Scam', tuk_tuk_scam:'🛺 Tuk-Tuk Scam', overcharging:'💰 Overcharging',
    fake_guide:'🧑‍🦯 Fake Guide', transport_fraud:'🚕 Transport Fraud',
    harassment:'😨 Harassment', accommodation_scam:'🏨 Accommodation Scam',
    food_scam:'🍽️ Food Scam', unsafe_area:'⚠️ Unsafe Area',
  };
  warnList.innerHTML = high.map(z => `
    <li class="warning-card" onclick="window.map.zoomTo(${z.center_lat}, ${z.center_lon})">
      <div class="warning-title">${LABELS[z.primary_scam_type] || '⚠️ General Warning'}</div>
      <div>${z.report_count} incident${z.report_count !== 1 ? 's' : ''} reported — risk score ${(z.risk_score * 100).toFixed(0)}%</div>
    </li>
  `).join('');
}

demoSelect.addEventListener('change', fetchHeatmap);
document.getElementById('btn-refresh').addEventListener('click', fetchHeatmap);

// Auto-refresh every 5 minutes
fetchHeatmap();
setInterval(fetchHeatmap, 5 * 60 * 1000);

/* ── Address Autocomplete Search (Uber/PickMe style) ──────── */
const mapSearchInput = document.getElementById('map-search');
const suggestionsBox = document.getElementById('search-suggestions');
const intelPanel     = document.getElementById('intelligence-panel');
const intelContent   = document.getElementById('intel-content');
const warningsPanel  = document.getElementById('warnings-panel');
let searchDebounce, activeSuggestionIdx = -1;

// Nominatim (OpenStreetMap) geocoding — free, no API key needed
async function nominatimSearch(query) {
  const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query + ' Sri Lanka')}&countrycodes=lk&limit=6&addressdetails=1`;
  const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
  return res.json();
}

mapSearchInput.addEventListener('input', () => {
  clearTimeout(searchDebounce);
  const q = mapSearchInput.value.trim();
  if (q.length < 2) {
    suggestionsBox.classList.add('hidden');
    return;
  }
  suggestionsBox.innerHTML = '<div class="search-loading">🔍 Searching...</div>';
  suggestionsBox.classList.remove('hidden');

  searchDebounce = setTimeout(async () => {
    try {
      const results = await nominatimSearch(q);
      if (results.length === 0) {
        suggestionsBox.innerHTML = '<div class="search-loading">No results found</div>';
        return;
      }
      activeSuggestionIdx = -1;
      suggestionsBox.innerHTML = results.map((r, i) => {
        const icon = getPlaceIcon(r.type, r.class);
        const main = r.display_name.split(',')[0];
        const sub = r.display_name.split(',').slice(1, 3).join(',').trim();
        return `<div class="search-suggestion" data-idx="${i}" data-lat="${r.lat}" data-lng="${r.lon}" data-name="${main}">
          <div class="search-suggestion-icon">${icon}</div>
          <div class="search-suggestion-text">
            <div class="search-suggestion-main">${main}</div>
            <div class="search-suggestion-sub">${sub}</div>
          </div>
        </div>`;
      }).join('');

      // Click handlers
      suggestionsBox.querySelectorAll('.search-suggestion').forEach(el => {
        el.addEventListener('click', () => {
          const lat = parseFloat(el.dataset.lat);
          const lng = parseFloat(el.dataset.lng);
          const name = el.dataset.name;
          mapSearchInput.value = name;
          suggestionsBox.classList.add('hidden');
          map.zoomTo(lat, lng);
          assessLocation(lat, lng, name);
        });
      });
    } catch (err) {
      suggestionsBox.innerHTML = '<div class="search-loading">Search error — try again</div>';
    }
  }, 350);
});

// Keyboard navigation
mapSearchInput.addEventListener('keydown', (e) => {
  const items = suggestionsBox.querySelectorAll('.search-suggestion');
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    activeSuggestionIdx = Math.min(activeSuggestionIdx + 1, items.length - 1);
    items.forEach((el, i) => el.classList.toggle('active', i === activeSuggestionIdx));
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    activeSuggestionIdx = Math.max(activeSuggestionIdx - 1, 0);
    items.forEach((el, i) => el.classList.toggle('active', i === activeSuggestionIdx));
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (activeSuggestionIdx >= 0 && items[activeSuggestionIdx]) {
      items[activeSuggestionIdx].click();
    } else if (mapSearchInput.value.trim().length >= 2) {
      // Fallback: search the first result
      const first = items[0];
      if (first) first.click();
    }
  } else if (e.key === 'Escape') {
    suggestionsBox.classList.add('hidden');
  }
});

// Close suggestions on outside click
document.addEventListener('click', (e) => {
  if (!e.target.closest('.search-autocomplete-wrap')) {
    suggestionsBox.classList.add('hidden');
  }
});

function getPlaceIcon(type, cls) {
  if (cls === 'tourism' || type === 'attraction') return '🏛️';
  if (cls === 'natural') return '🌿';
  if (type === 'beach') return '🏖️';
  if (cls === 'place' || type === 'city' || type === 'town') return '🏙️';
  if (type === 'village') return '🏘️';
  if (cls === 'highway' || type === 'road') return '🛣️';
  if (cls === 'amenity') return '📍';
  return '📍';
}

/* ── Click Anywhere on Map → Safety Assessment ───────────── */
let clickMarker = null;

map.map.on('click', (e) => {
  const { lat, lng } = e.latlng;
  assessLocation(lat, lng);
});

/* ── Safety Intelligence Assessment ──────────────────────── */
async function assessLocation(lat, lng, placeName) {
  // Ensure ONLY ONE panel/popup is visible: close any open map popup
  if (map && map.map) {
    map.map.closePopup();
  }

  // Show loading state
  intelPanel.classList.remove('hidden');
  warningsPanel.style.display = 'none';
  intelContent.innerHTML = `
    <div class="intel-header">
      <div>
        <div class="intel-location">📍 ${placeName || 'Assessing location...'}</div>
        <div class="intel-coords">${lat.toFixed(5)}, ${lng.toFixed(5)}</div>
      </div>
      <button class="intel-close" onclick="closeIntelPanel()">✕</button>
    </div>
    <div style="text-align:center; padding:30px 0; color:var(--muted);">
      <div class="spinner" style="margin:0 auto 12px;"></div>
      Analyzing ${placeName ? '"' + placeName + '"' : 'this location'}...<br>
      <span style="font-size:11px;">Cross-referencing 120,000+ reports</span>
    </div>`;

  // Place marker on map
  if (clickMarker) map.map.removeLayer(clickMarker);
  const L = await import('leaflet');
  clickMarker = L.circleMarker([lat, lng], {
    radius: 8, color: '#8b5cf6', fillColor: '#8b5cf6',
    fillOpacity: 0.4, weight: 3,
  }).addTo(map.map);
  map.map.setView([lat, lng], Math.max(map.map.getZoom(), 12));

  try {
    const res = await fetch(`${API}/safety/assess?lat=${lat}&lng=${lng}`);
    const data = await res.json();

    // Reverse geocode for place name if not provided
    if (!placeName) {
      try {
        const geoRes = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=16`, 
          { headers: { 'Accept-Language': 'en' } });
        const geoData = await geoRes.json();
        placeName = geoData.display_name?.split(',').slice(0, 2).join(',') || `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
      } catch (_) {
        placeName = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
      }
    }

    renderIntelligencePanel(data, placeName, lat, lng);
  } catch (err) {
    intelContent.innerHTML = `
      <div class="intel-header">
        <div><div class="intel-location">📍 ${placeName || 'Location'}</div></div>
        <button class="intel-close" onclick="closeIntelPanel()">✕</button>
      </div>
      <div class="intel-nodata">
        <div class="intel-nodata-icon">⚠️</div>
        Backend offline — cannot assess this location.
      </div>`;
  }
}

function closeIntelPanel() {
  intelPanel.classList.add('hidden');
  warningsPanel.classList.add('hidden');
  warningsPanel.style.display = 'none';
  if (clickMarker) { map.map.removeLayer(clickMarker); clickMarker = null; }
}
window.closeIntelPanel = closeIntelPanel;

/* ── Render Intelligence Panel ────────────────────────────── */
function renderIntelligencePanel(data, placeName, lat, lng) {
  const SCAM_ICONS_INTEL = {
    'Overcharging': '💰', 'Price Gouging': '💰', 'overcharging': '💰',
    'General Scam': '⚠️', 'General Tourist Safety': '⚠️',
    'Fake Guide': '🧑‍🦯', 'Unlicensed Guide Scam': '🧑‍🦯', 'fake_guide': '🧑‍🦯',
    'Theft': '🔓', 'Theft / Robbery': '🔓', 'Theft & Robbery': '🔓', 'theft': '🔓',
    'Harassment': '😨', 'Tourist Harassment': '😨', 'harassment': '😨',
    'Physical Assault': '💥', 'Safety Hazard / Assault': '💥',
    'Unsafe Area': '🚫', 'High Risk Zone': '🚫', 'safe': '✅', 'Verified Safe Area': '✅',
    'commission_shop': '🏪', 'Commission Shop Trap': '🏪',
    'gem_scam': '💎', 'Gem & Jewelry Scam': '💎', 'Gem Scam': '💎',
    'tuk_tuk_scam': '🛺', 'Tuk-Tuk Overcharging': '🛺', 'Tuk Tuk Scam': '🛺',
    'Accommodation Fraud': '🏨', 'Accommodation Scam': '🏨',
    'Currency Exchange Scam': '𒒱', 'currency_scam': '𒒱',
    'Wildlife & Tour Exploitation': '🐘', 'wildlife_exploit': '🐘',
    'Road & Physical Hazard': '⚠️', 'Accident / Hazard': '⚠️',
    'Health & Sanitation Warning': '🏥', 'Health / Hygiene': '🏥',
  };

  const verdictClass = data.verdict === 'SAFE' ? 'safe' :
    data.verdict === 'LOW RISK' ? 'low' :
    data.verdict === 'MODERATE RISK' ? 'moderate' :
    data.verdict === 'HIGH RISK' ? 'high' : 'gray';

  const scoreColor = data.composite_score >= 0.6 ? 'var(--red)' :
    data.composite_score >= 0.35 ? 'var(--yellow)' :
    data.composite_score >= 0.15 ? '#86efac' : 'var(--green)';

  // Score breakdown metrics
  const bd = data.score_breakdown || {};
  const metrics = [
    { label: 'Scam Ratio', value: bd.scam_ratio, color: 'var(--red)' },
    { label: 'Severity', value: bd.severity_index, color: 'var(--yellow)' },
    { label: 'Diversity', value: bd.diversity_penalty, color: '#f97316' },
    { label: 'Credibility', value: bd.credibility_factor, color: 'var(--primary)' },
  ];

  // Scam types (filtered to exclude invalid/generic noise entries like nan, none, null, Unsafe Area)
  const scamHtml = (data.top_scam_types || [])
    .filter(s => s.type && !['nan', 'none', 'null', 'unsafe area', 'general scam', 'undefined'].includes(String(s.type).toLowerCase()))
    .map(s =>
      `<div class="intel-scam-item">
        <span class="intel-scam-icon">${SCAM_ICONS_INTEL[s.type] || '⚠️'}</span>
        <span class="intel-scam-name">${s.type}</span>
        <span class="intel-scam-count">${s.count}</span>
      </div>`
    ).join('');

  // Safety tips
  const tipsHtml = (data.safety_tips || []).map(tip =>
    `<div class="intel-tip">
      <span class="intel-tip-icon">💡</span>
      <span>${tip}</span>
    </div>`
  ).join('');

  // Store nearby incidents globally for dynamic client-side sorting
  window.currentNearbyIncidents = data.nearby_incidents || [];

  // Source breakdown (User-Friendly Credibility Badges)
  const sourcesHtml = (data.source_breakdown || []).map(s => {
    const tierTag = s.tier || '💬 Public Community Discussion';
    const score = s.credibility_score || 0.5;
    const cls = score >= 0.85 ? 't1' : score >= 0.60 ? 't2a' : 't3';
    return `<div class="intel-source-row">
      <span class="intel-source-tier ${cls}">${tierTag}</span>
      <span class="intel-source-name">${s.source}</span>
      <span class="intel-source-count">${s.count.toLocaleString()} reports</span>
    </div>`;
  }).join('');

  // Authority report
  const authHtml = data.authority_report ? `
    <div class="intel-authority">
      <div class="intel-authority-title">🚔 Authority Alert — Tourism Police Report</div>
      <div class="intel-authority-detail">📍 Location: ${lat.toFixed(5)}, ${lng.toFixed(5)}</div>
      <div class="intel-authority-detail">⚠️ Risk: ${data.authority_report.risk_level} (${data.authority_report.composite_score})</div>
      <div class="intel-authority-detail">📊 Incidents: ${data.authority_report.total_incidents} | Verified: ${data.authority_report.verified_sources}</div>
      <div class="intel-authority-detail">🏷️ Types: ${Object.keys(data.authority_report.scam_types || {}).join(', ')}</div>
      <div class="intel-authority-action">📋 ${data.authority_report.recommended_action}</div>
    </div>
  ` : '';

  // No data handling
  const noDataHtml = data.verdict === 'INSUFFICIENT DATA' ? `
    <div class="intel-nodata">
      <div class="intel-nodata-icon">📡</div>
      No incident data within 15km radius.
      ${data.message ? `<br><br>${data.message}` : ''}
      ${(data.nearest_known_places || []).length > 0 ? `
        <div class="intel-nearest">
          <div class="intel-nearest-title">Nearest Known Locations:</div>
          ${data.nearest_known_places.map(p =>
            `<div class="intel-nearest-item">📍 ${p.location_name} — ${p.distance_km}km away</div>`
          ).join('')}
        </div>
      ` : ''}
    </div>
  ` : '';

  const scoreDisplay = data.composite_score !== null && data.composite_score !== undefined 
    ? `${(data.composite_score * 100).toFixed(0)}%` 
    : 'N/A';

  const filterWarningHtml = (data.verdict === 'HIGH RISK' && !filters.high) ? `
    <div style="margin: 10px 0; padding: 8px 12px; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; font-size: 11px; color: #fca5a5;">
      💡 <strong>Map Filter Notice:</strong> "High Risk" toggle is currently OFF in the left panel. High-risk hotspot markers are hidden on the map.
    </div>
  ` : (data.verdict === 'MODERATE RISK' && !filters.med) ? `
    <div style="margin: 10px 0; padding: 8px 12px; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px; font-size: 11px; color: #fcd34d;">
      💡 <strong>Map Filter Notice:</strong> "Moderate" toggle is currently OFF in the left panel. Moderate-risk hotspot markers are hidden on the map.
    </div>
  ` : '';

  const dc = data.district_context;
  const tierFormatted = dc && dc.risk_tier ? (dc.risk_tier === 'insufficient_data' ? '⚪ Insufficient Data' : dc.risk_tier.toUpperCase() + ' RISK') : '';
  const districtContextHtml = dc ? `
    <div style="margin: 12px 0; padding: 10px 12px; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; font-size: 11px; color: #cbd5e1;">
      <div style="font-weight: 600; color: #93c5fd; margin-bottom: 3px; display: flex; align-items: center; justify-content: space-between;">
        <span>🏛️ District Level Context (${dc.district_name})</span>
        <span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(255, 255, 255, 0.1);">${tierFormatted}</span>
      </div>
      <div>
        District Total: <strong>${dc.report_count ?? 0} reports</strong> (${dc.scam_report_count ?? 0} scam-flagged).
        ${dc.exposure_status === 'unavailable' ? '<br><span style="color:#fcd34d;">⚠️ No SLTDA visitor footfall baseline — district score is density-based.</span>' : ''}
      </div>
    </div>
  ` : '';

  intelContent.innerHTML = `
    <div class="intel-header">
      <div>
        <div class="intel-location">📍 ${placeName}</div>
        <div style="font-size:11px; color:#94a3b8; font-weight:500; margin-top:2px;">🎯 Local Point Assessment (15km radius)</div>
        <div class="intel-coords">${lat.toFixed(5)}, ${lng.toFixed(5)}</div>
      </div>
      <button class="intel-close" onclick="closeIntelPanel()">✕</button>
    </div>

    <div class="intel-verdict ${verdictClass}">
      <div class="intel-verdict-label">${data.verdict}</div>
      <div class="intel-score-row">
        <div class="intel-score-big" style="color:${scoreColor}">${scoreDisplay}</div>
        <div class="intel-score-meta">
          <div class="intel-confidence">Confidence: ${data.confidence}</div>
          <div class="intel-data-count">${data.total_reports_analyzed.toLocaleString()} reports analyzed</div>
          <div class="intel-data-count">${data.scam_reports_found} scam reports found</div>
        </div>
      </div>
    </div>

    ${districtContextHtml}
    ${filterWarningHtml}
    ${noDataHtml}

    ${data.verdict !== 'INSUFFICIENT DATA' ? `
      <div class="intel-section">
        <div class="intel-section-title">📊 Score Breakdown</div>
        <div class="intel-breakdown">
          ${metrics.map(m => `
            <div class="intel-metric">
              <div class="intel-metric-label">${m.label}</div>
              <div class="intel-metric-bar"><div class="intel-metric-fill" style="width:${Math.round((m.value || 0) * 100)}%;background:${m.color}"></div></div>
              <div class="intel-metric-value" style="color:${m.color}">${((m.value || 0) * 100).toFixed(0)}%</div>
            </div>
          `).join('')}
        </div>
      </div>

      ${scamHtml ? `<div class="intel-section"><div class="intel-section-title">🚨 Detected Scam Patterns</div>${scamHtml}</div>` : ''}

      <div class="intel-section">
        <div class="intel-section-title">🛡️ Safety Tips</div>
        ${tipsHtml}
      </div>

      ${window.currentNearbyIncidents.length > 0 ? `
        <div class="intel-section">
          <div class="intel-section-header-row">
            <div class="intel-section-title" style="margin-bottom:0;">📝 Nearby Incidents</div>
            <div class="intel-sort-wrap">
              <span class="intel-sort-label">Sort:</span>
              <select id="intel-sort-select" onchange="window.sortNearbyIncidents(this.value)" class="intel-sort-select">
                <option value="credibility" selected>🛡️ Credibility</option>
                <option value="distance">📍 Nearest</option>
                <option value="risk">⚠️ Highest Risk</option>
              </select>
            </div>
          </div>
          <div id="intel-incidents-container">
            ${renderIncidentsListHtml(window.currentNearbyIncidents)}
          </div>
        </div>` : ''}

      <div class="intel-section">
        <div class="intel-section-title">📡 Verified Source Evidence</div>
        ${sourcesHtml}
      </div>

      ${authHtml}
    ` : ''}
  `;
}

/* ── Incident List Renderer & Sorting Handler ──────────────── */
function renderIncidentsListHtml(incidents) {
  if (!incidents || incidents.length === 0) {
    return '<div class="intel-nodata" style="padding:15px; text-align:center;">No incidents reported in this area.</div>';
  }
  const SCAM_ICONS_INTEL = {
    'Overcharging': '💰', 'Price Gouging': '💰', 'General Scam': '⚠️', 'General Tourist Safety': '⚠️',
    'Fake Guide': '🧑‍🦯', 'Unlicensed Guide Scam': '🧑‍🦯', 'fake_guide': '🧑‍🦯',
    'Theft': '🔓', 'Theft & Robbery': '🔓', 'Theft / Robbery': '🔓', 'theft': '🔓',
    'Harassment': '😨', 'Tourist Harassment': '😨', 'harassment': '😨',
    'Physical Assault': '💥', 'Unsafe Area': '🚫', 'safe': '✅', 'Verified Safe Area': '✅',
    'commission_shop': '🏪', 'Commission Shop Trap': '🏪',
    'gem_scam': '💎', 'Gem & Jewelry Scam': '💎',
    'tuk_tuk_scam': '🛺', 'Tuk-Tuk Overcharging': '🛺',
  };

  return incidents.map((inc, index) => {
    const credBadge = inc.credibility_label || '💬 Public Community Discussion';
    const sourceTitle = inc.source_display || inc.source || '';
    const isVerified = (inc.credibility_score || 0) >= 0.85;
    const scamLabel = inc.scam_type_display || inc.scam_type || 'Safety Incident';
    const validUrl = isAccessibleWebUrl(inc.url, inc.source);

    // Detect source type for badge & button styling
    const srcLower = (inc.source || '').toLowerCase();
    const urlLower = (inc.url || '').toLowerCase();
    const isYouTube = srcLower.includes('youtube') || urlLower.includes('youtube.com') || urlLower.includes('youtu.be');
    const isTier1News = isVerified || srcLower.includes('mirror') || srcLower.includes('derana') || srcLower.includes('news') || srcLower.includes('times') || srcLower.includes('ceylon') || srcLower.includes('hiru');

    let btnText = '🔗 View Source';
    let btnStyle = 'background: rgba(139, 92, 246, 0.15); color: var(--primary); border: 1px solid rgba(139, 92, 246, 0.4);';
    let badgeHtml = `<span class="intel-incident-cred ${isVerified ? 'verified' : ''}">${credBadge}</span>`;

    if (isYouTube) {
      btnText = '▶️ Watch Video ↗';
      btnStyle = 'background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.5); font-weight: 700;';
      badgeHtml = `<span class="intel-incident-cred" style="background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); font-weight: 700;">🎥 YouTube Video</span>`;
    } else if (isTier1News) {
      btnText = '📰 News Article ↗';
      btnStyle = 'background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.5); font-weight: 700;';
      badgeHtml = `<span class="intel-incident-cred verified" style="background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); font-weight: 700;">🏛️ Tier 1 Verified News</span>`;
    } else if (srcLower.includes('tripadvisor') || srcLower.includes('maps') || srcLower.includes('reviews')) {
      btnText = '⭐ Review Source ↗';
    }

    const titleText = inc.title ? `"${inc.title}"` : '';

    return `<div class="intel-incident clickable-card" onclick="window.openIncidentModal(${index})" title="Click to view full details & report source">
      <div class="intel-incident-header">
        <span class="intel-incident-type" style="color:${inc.risk_level === 3 ? 'var(--red)' : 'var(--yellow)'}">
          ${SCAM_ICONS_INTEL[inc.scam_type_display] || SCAM_ICONS_INTEL[inc.scam_type] || '⚠️'} ${scamLabel}
        </span>
        ${badgeHtml}
      </div>
      ${titleText ? `<div class="intel-incident-headline" style="font-weight:700; font-size:13.5px; margin:7px 0 4px 0; color:#f8fafc; line-height:1.35;">${titleText}</div>` : ''}
      <div class="intel-incident-text" style="color: #94a3b8; font-size:12.5px; line-height:1.45;">${inc.content_snippet || ''}</div>
      <div class="intel-incident-footer">
        <span class="intel-incident-source">📍 ${inc.location_name} · ${sourceTitle}</span>
        <span class="intel-incident-action-wrap">
          ${validUrl ? `<a href="${inc.url}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation();" class="intel-card-link" style="${btnStyle}" title="Open source webpage">${btnText}</a>` : '<span class="intel-card-expand">🔍 View Details</span>'}
          <span class="intel-incident-dist">📏 ${inc.distance_km}km away</span>
        </span>
      </div>
    </div>`;
  }).join('');
}

window.sortNearbyIncidents = function(sortBy) {
  const container = document.getElementById('intel-incidents-container');
  if (!container || !window.currentNearbyIncidents) return;

  let items = [...window.currentNearbyIncidents];

  if (sortBy === 'distance') {
    items.sort((a, b) => (a.distance_km || 0) - (b.distance_km || 0) || (b.credibility_score || 0) - (a.credibility_score || 0));
  } else if (sortBy === 'risk') {
    items.sort((a, b) => (b.risk_level || 0) - (a.risk_level || 0) || (b.credibility_score || 0) - (a.credibility_score || 0));
  } else { // default: credibility
    items.sort((a, b) => (b.credibility_score || 0) - (a.credibility_score || 0) || (a.distance_km || 0) - (b.distance_km || 0));
  }

  container.innerHTML = renderIncidentsListHtml(items);
};

window.openIncidentModal = function(index) {
  if (!window.currentNearbyIncidents || !window.currentNearbyIncidents[index]) return;
  const inc = window.currentNearbyIncidents[index];
  const modal = document.getElementById('incident-modal');
  if (!modal) return;

  document.getElementById('modal-incident-title').innerText = inc.title || 'Safety Incident Report';
  document.getElementById('modal-scam-badge').innerText = `⚠️ ${inc.scam_type_display || inc.scam_type || 'Scam Alert'}`;
  
  const credBadgeEl = document.getElementById('modal-cred-badge');
  const srcLower = (inc.source || '').toLowerCase();
  const urlLower = (inc.url || '').toLowerCase();
  const isYouTube = srcLower.includes('youtube') || urlLower.includes('youtube.com') || urlLower.includes('youtu.be');
  const isTier1News = (inc.credibility_score || 0) >= 0.85 || srcLower.includes('mirror') || srcLower.includes('derana') || srcLower.includes('news') || srcLower.includes('times') || srcLower.includes('ceylon') || srcLower.includes('hiru');

  if (isYouTube) {
    credBadgeEl.innerText = '🎥 YouTube Video Evidence';
    credBadgeEl.className = 'intel-incident-cred';
    credBadgeEl.style.cssText = 'background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); font-weight: 700;';
  } else if (isTier1News) {
    credBadgeEl.innerText = '🏛️ Tier 1 Verified News';
    credBadgeEl.className = 'intel-incident-cred verified';
    credBadgeEl.style.cssText = 'background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); font-weight: 700;';
  } else {
    credBadgeEl.innerText = inc.credibility_label || '💬 Public Community Discussion';
    credBadgeEl.className = (inc.credibility_score || 0) >= 0.85 ? 'intel-incident-cred verified' : 'intel-incident-cred';
    credBadgeEl.style.cssText = '';
  }

  document.getElementById('modal-location').innerText = `📍 ${inc.location_name || 'Sri Lanka'}`;
  document.getElementById('modal-distance').innerText = `📏 ${inc.distance_km}km away`;
  document.getElementById('modal-source').innerText = `📰 ${inc.source_display || inc.source}`;

  document.getElementById('modal-summary-text').innerText = inc.full_summary || inc.content_snippet || 'Detailed report documented by safety intelligence monitoring.';

  const sourceLinkBtn = document.getElementById('modal-source-link');
  const validUrl = isAccessibleWebUrl(inc.url, inc.source);
  if (validUrl) {
    sourceLinkBtn.href = inc.url;
    let btnText = '🔗 View Source ↗';
    if (isYouTube) {
      btnText = '▶️ Watch YouTube Video ↗';
      sourceLinkBtn.style.cssText = 'background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.5); font-weight: 700;';
    } else if (isTier1News) {
      btnText = '📰 Read News Article ↗';
      sourceLinkBtn.style.cssText = 'background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.5); font-weight: 700;';
    } else if (srcLower.includes('tripadvisor') || srcLower.includes('maps') || srcLower.includes('reviews')) {
      btnText = '⭐ Read Review ↗';
      sourceLinkBtn.style.cssText = '';
    } else {
      sourceLinkBtn.style.cssText = '';
    }
    sourceLinkBtn.innerText = btnText;
    sourceLinkBtn.classList.remove('hidden');
  } else {
    sourceLinkBtn.classList.add('hidden');
  }

  modal.classList.remove('hidden');
};

window.closeIncidentModal = function() {
  const modal = document.getElementById('incident-modal');
  if (modal) modal.classList.add('hidden');
};


/* ══════════════════════════════════════════════════════════
   CHAT BOT — AI SAFETY ADVISOR
   ══════════════════════════════════════════════════════════ */

const chatMessages  = document.getElementById('chat-messages');
const chatInput     = document.getElementById('chat-input');
const chatSendBtn   = document.getElementById('chat-send-btn');
const chatClearBtn  = document.getElementById('chat-clear-btn');
const chatProfile   = document.getElementById('chat-profile');
const chatMonth     = document.getElementById('chat-month');

// Set current month
chatMonth.value = String(new Date().getMonth() + 1);

const SCAM_ICONS = {
  'Gem Scam': '💎', 'Tuk Tuk Scam': '🛺', 'Overcharging': '💰',
  'Fake Guide': '🧑‍🦯', 'Transport Fraud': '🚕', 'Harassment': '😨',
  'Accommodation Scam': '🏨', 'Health / Hygiene': '🏥',
  'Theft / Robbery': '🔓', 'Physical Assault': '⚠️', 'Unsafe Area': '🚫',
  'Food/Menu Scam': '🍽️',
};

const CITIES = [
  'colombo','kandy','galle','ella','sigiriya','nuwara eliya','mirissa',
  'hikkaduwa','jaffna','trincomalee','negombo','arugam bay','habarana',
  'polonnaruwa','anuradhapura','bentota','unawatuna','weligama','matara',
  'dambulla','pinnawala','ratnapura','badulla','tangalle',
];

const MONTHS_MAP = {
  january:1,february:2,march:3,april:4,may:5,june:6,
  july:7,august:8,september:9,october:10,november:11,december:12,
};

function extractCity(text) {
  const t = text.toLowerCase();
  return CITIES.find(c => t.includes(c)) || null;
}

function extractMonth(text) {
  const t = text.toLowerCase();
  for (const [name, num] of Object.entries(MONTHS_MAP)) {
    if (t.includes(name)) return num;
  }
  return null;
}

/* ── Message rendering ─────────────────────────────────── */
function appendUserMsg(text) {
  const div = document.createElement('div');
  div.className = 'chat-bubble user-bubble';
  div.innerHTML = `<div class="bubble-content user-content">${escHtml(text)}</div>`;
  chatMessages.appendChild(div);
  scrollChat();
}

function appendBotTyping() {
  const div = document.createElement('div');
  div.className = 'chat-bubble bot-bubble';
  div.id = 'bot-typing';
  div.innerHTML = `
    <div class="bot-avatar">🤖</div>
    <div class="bubble-content bot-content typing-dots">
      <span></span><span></span><span></span>
    </div>`;
  chatMessages.appendChild(div);
  scrollChat();
}

function removeBotTyping() {
  document.getElementById('bot-typing')?.remove();
}

function appendBotMsg(html, chips = []) {
  removeBotTyping();
  const div = document.createElement('div');
  div.className = 'chat-bubble bot-bubble';
  const chipsHtml = chips.length
    ? `<div class="reply-chips">${chips.map(c =>
        `<button class="reply-chip" data-msg="${escAttr(c)}">${c}</button>`
      ).join('')}</div>`
    : '';
  div.innerHTML = `
    <div class="bot-avatar">🤖</div>
    <div class="bubble-content bot-content">
      ${html}
      ${chipsHtml}
    </div>`;
  chatMessages.appendChild(div);
  // wire up reply chips
  div.querySelectorAll('.reply-chip').forEach(btn => {
    btn.addEventListener('click', () => sendMessage(btn.dataset.msg));
  });
  scrollChat();
  // Draw radar if any canvas was added
  const canvas = div.querySelector('.radar-canvas-inline');
  if (canvas) {
    try {
      const radarData = JSON.parse(canvas.dataset.radar);
      requestAnimationFrame(() => drawRadarInline(canvas, radarData));
    } catch {}
  }
}

function scrollChat() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function escAttr(s) {
  return String(s).replace(/"/g,'&quot;');
}

/* ── Intent Parser ─────────────────────────────────────── */
function parseIntent(text) {
  const t = text.toLowerCase();
  const city  = extractCity(t);
  const month = extractMonth(t);
  const profile = chatProfile.value;

  if (t.includes('scam') || t.includes('fraud') || t.includes('cheat')) {
    return { type: 'scams', city, month, profile };
  }
  if (t.includes('safe') || t.includes('risk') || t.includes('danger')) {
    return { type: 'safety', city, month, profile };
  }
  if (t.includes('transport') || t.includes('tuk') || t.includes('taxi') || t.includes('bus')) {
    return { type: 'transport', city, month, profile };
  }
  if (t.includes('solo female') || t.includes('woman') || t.includes('female')) {
    return { type: 'safety', city, month, profile: 'Solo Female' };
  }
  if (t.includes('family') || t.includes('children') || t.includes('kids')) {
    return { type: 'safety', city, month, profile: 'Family' };
  }
  if (t.includes('weather') || t.includes('monsoon') || t.includes('rain') || t.includes('season')) {
    return { type: 'season', city, month, profile };
  }
  if (t.includes('tip') || t.includes('advice') || t.includes('should')) {
    return { type: 'tips', city, month, profile };
  }
  if (city) {
    return { type: 'safety', city, month, profile };
  }
  return { type: 'general', city: null, month, profile };
}

/* ── Main send handler ─────────────────────────────────── */
async function sendMessage(text) {
  text = (text || chatInput.value).trim();
  if (!text) return;
  chatInput.value = '';

  appendUserMsg(text);
  appendBotTyping();

  const intent = parseIntent(text);
  const city   = intent.city;
  const profile= intent.profile || chatProfile.value;
  const month  = intent.month  || parseInt(chatMonth.value);

  try {
    if (intent.type === 'general' && !city) {
      await replyGeneral(text);
      return;
    }

    const params = new URLSearchParams({ profile, month });
    if (city) params.set('city', city);

    const fetchList = [
      fetch(`${API}/advisor/profile-report?${params}`),
    ];
    if (city) {
      fetchList.push(
        fetch(`${API}/advisor/real-reports?city=${encodeURIComponent(city)}&limit=5`)
      );
    }

    const [reportRes, realRes] = await Promise.all(fetchList);
    if (!reportRes.ok) throw new Error('API error');

    const report = await reportRes.json();
    const realReports = (city && realRes?.ok) ? await realRes.json() : null;

    buildChatResponse(intent, report, realReports, city, profile);
  } catch (err) {
    removeBotTyping();
    appendBotMsg(`<p style="color:var(--red)">⚠️ Could not reach the backend. Make sure the FastAPI server is running on port 8000.</p>`);
    console.error('[Chat]', err);
  }
}

/* ── Response builder ──────────────────────────────────── */
function buildChatResponse(intent, report, realReports, city, profile) {
  const score       = report.overall_safety_score ?? 70;
  const riskLabel   = report.risk_label ?? 'Moderate Risk';
  const scoreColor  = score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444';
  const radar       = report.radar ?? {};
  const threats     = report.top_threats ?? [];
  const tips        = report.safety_tips ?? [];
  const checklist   = report.checklist ?? [];
  const season      = report.season ?? {};
  const cityStats   = report.city_stats;
  const profIcon    = report.profile_icon ?? '🌍';
  const monthName   = report.month_name ?? '';

  // ── Score pill ──
  const scorePill = `
    <div class="chat-score-row">
      <div class="chat-score-ring" style="--score-color:${scoreColor}">
        <svg width="70" height="70" viewBox="0 0 70 70">
          <circle cx="35" cy="35" r="28" fill="none" stroke="#ffffff10" stroke-width="6"/>
          <circle cx="35" cy="35" r="28" fill="none" stroke="${scoreColor}" stroke-width="6"
            stroke-dasharray="${(2*Math.PI*28).toFixed(1)}"
            stroke-dashoffset="${((1 - score/100)*2*Math.PI*28).toFixed(1)}"
            stroke-linecap="round" transform="rotate(-90 35 35)"/>
        </svg>
        <div class="chat-score-num" style="color:${scoreColor}">${score}</div>
      </div>
      <div class="chat-score-info">
        <div class="chat-score-label" style="color:${scoreColor}">${riskLabel}</div>
        <div class="chat-score-sub">${profIcon} ${profile}${city ? ' · ' + city.charAt(0).toUpperCase()+city.slice(1) : ''}</div>
        <div class="chat-score-sub">${season.icon ?? '📅'} ${season.label ?? ''} — ${monthName}</div>
      </div>
    </div>`;

  // ── Season warning ──
  let seasonHtml = '';
  if (season.warning || report.seasonal_risk?.is_high_season) {
    seasonHtml = `
      <div class="chat-alert warn">
        ${season.icon ?? '🌧️'} <strong>${season.label ?? 'Seasonal Alert'}</strong><br>
        <span style="font-size:12px">${season.warning ?? 'Adverse conditions this month.'}</span>
      </div>`;
  }

  // ── Top threats ──
  let threatsHtml = '';
  if (threats.length) {
    threatsHtml = `<div class="chat-section-title">⚠️ Top Threats for ${profile}${city ? ' in '+city.charAt(0).toUpperCase()+city.slice(1) : ''}</div>`;
    threatsHtml += threats.slice(0,5).map(t => {
      const c = t.likelihood_label === 'High' ? '#ef4444' : t.likelihood_label === 'Moderate' ? '#f59e0b' : '#10b981';
      const icon = SCAM_ICONS[t.scam_type] || '⚠️';
      return `<div class="chat-threat-row">
        <span class="chat-threat-name">${icon} ${t.scam_type}</span>
        <div class="chat-threat-track"><div class="chat-threat-fill" style="width:${Math.round(t.score*100)}%;background:${c}"></div></div>
        <span style="font-size:11px;color:${c};font-weight:700;min-width:34px;text-align:right">${Math.round(t.score*100)}%</span>
      </div>`;
    }).join('');
  }

  // ── Radar ──
  const radarJson = JSON.stringify(radar);
  const radarHtml = Object.keys(radar).length ? `
    <div class="chat-section-title">📊 Risk Breakdown</div>
    <canvas class="radar-canvas-inline" width="220" height="190" data-radar='${radarJson}'></canvas>` : '';

  // ── City stats ──
  let statsHtml = '';
  if (cityStats) {
    const negRate = cityStats.total_reviews > 0
      ? Math.round(cityStats.negative_reviews / cityStats.total_reviews * 100) : 0;
    const peakBadge = cityStats.is_peak_complaint_month
      ? `<span style="color:#f59e0b;font-size:11px;font-weight:700">⚠️ Peak complaint month!</span>` : '';
    statsHtml = `
      <div class="chat-section-title">📈 ${cityStats.city} Data Intelligence</div>
      <div class="chat-stats-row">
        <div class="chat-stat"><div class="chat-stat-num">${cityStats.total_reviews.toLocaleString()}</div><div class="chat-stat-lbl">Reviews</div></div>
        <div class="chat-stat"><div class="chat-stat-num" style="color:${negRate>20?'#ef4444':'#22c55e'}">${negRate}%</div><div class="chat-stat-lbl">Negative</div></div>
        <div class="chat-stat"><div class="chat-stat-num" style="color:#f59e0b">${cityStats.scam_mentions}</div><div class="chat-stat-lbl">Scam Mentions</div></div>
        <div class="chat-stat"><div class="chat-stat-num">${cityStats.avg_rating?.toFixed(1) ?? '—'}</div><div class="chat-stat-lbl">Avg Rating</div></div>
      </div>
      ${peakBadge}`;
  }

  // ── Tips ──
  let tipsHtml = '';
  if (tips.length && (intent.type === 'tips' || intent.type === 'general')) {
    tipsHtml = `<div class="chat-section-title">💡 Personalised Safety Tips</div>`;
    tipsHtml += tips.slice(0,3).map(t => `
      <div class="chat-tip-row">
        <span class="chat-tip-icon">${t.icon}</span>
        <div><strong style="font-size:13px">${t.title}</strong><br><span style="font-size:12px;color:var(--muted)">${t.body}</span></div>
      </div>`).join('');
  }

  // ── Checklist excerpt ──
  let checkHtml = '';
  if (checklist.length) {
    checkHtml = `<div class="chat-section-title">✅ Quick Pre-Trip Checklist</div>`;
    checkHtml += checklist.slice(0,4).map((item,i) => `
      <div class="chat-check-item" id="cchk-${i}" onclick="this.classList.toggle('checked')">
        <div class="chat-check-box"></div>
        <span style="font-size:13px">${item.icon} ${item.task}</span>
        <span class="check-priority ${item.priority}" style="margin-left:auto">${item.priority}</span>
      </div>`).join('');
  }

  // ── Real reports ──
  let realHtml = '';
  if (realReports && realReports.total_found > 0) {
    realHtml = `<div class="chat-section-title">📰 What Tourists Actually Reported (${realReports.total_found} incidents)</div>`;
    realHtml += realReports.reports.slice(0,4).map(r => {
      const riskColor = r.risk_level === 3 ? '#ef4444' : r.risk_level === 2 ? '#f59e0b' : '#10b981';
      const icon = SCAM_ICONS[r.scam_type] || '📋';
      const vBadge = r.is_verified_source
        ? `<span class="verified-badge">✔ Verified</span>` : '';
      return `<div class="chat-report-card" style="border-color:${riskColor}40">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap">
          ${vBadge}
          <span style="font-size:11px;color:${riskColor};font-weight:700">${icon} ${r.scam_type || 'Incident'}</span>
          <span style="font-size:10px;color:var(--muted);margin-left:auto">${r.source_label}</span>
        </div>
        ${r.url
          ? `<a href="${r.url}" target="_blank" rel="noopener" style="font-size:12px;color:#a5b4fc;text-decoration:underline;line-height:1.4;display:block">${r.title}</a>`
          : `<div style="font-size:12px;color:var(--text);line-height:1.4">${r.title}</div>`}
        ${r.date ? `<div style="font-size:10px;color:var(--muted);margin-top:3px">📅 ${r.date}</div>` : ''}
      </div>`;
    }).join('');
  }

  // ── Reply chips ──
  const chips = [];
  if (city) {
    chips.push(`What transport scams happen in ${city.charAt(0).toUpperCase()+city.slice(1)}?`);
    chips.push(`Any accommodation scams in ${city.charAt(0).toUpperCase()+city.slice(1)}?`);
  }
  chips.push('Give me a pre-trip safety checklist');
  chips.push('Is it monsoon season now?');

  const fullHtml = [scorePill, seasonHtml, threatsHtml, radarHtml, statsHtml, tipsHtml, checkHtml, realHtml]
    .filter(Boolean).join('<div class="chat-divider"></div>');

  appendBotMsg(fullHtml, chips);
}

/* ── General fallback ──────────────────────────────────── */
async function replyGeneral(text) {
  const t = text.toLowerCase();

  if (t.includes('hello') || t.includes('hi') || t.includes('hey')) {
    appendBotMsg(
      `<p>👋 Hello! I'm SafeTravel AI, your personal safety guide for Sri Lanka.</p>
       <p style="font-size:13px;color:var(--muted)">I can help you with scam alerts, risk assessments, transport safety, seasonal warnings, and personalised travel advice. Just ask!</p>`,
      ['Is Kandy safe?', 'What are common scams?', 'Is July a good time to visit?', 'Tips for solo females']
    );
    return;
  }

  if (t.includes('checklist') || t.includes('what to do')) {
    const profile = chatProfile.value;
    const month = parseInt(chatMonth.value);
    try {
      const res = await fetch(`${API}/advisor/profile-report?profile=${encodeURIComponent(profile)}&month=${month}`);
      const report = await res.json();
      const checklist = report.checklist ?? [];
      const tips = report.safety_tips ?? [];
      let html = `<p>Here's your personalised checklist for <strong>${profile}</strong>:</p>`;
      html += checklist.map((item,i) => `
        <div class="chat-check-item" id="cchk-g${i}" onclick="this.classList.toggle('checked')">
          <div class="chat-check-box"></div>
          <span style="font-size:13px">${item.icon} ${item.task}</span>
          <span class="check-priority ${item.priority}" style="margin-left:auto">${item.priority}</span>
        </div>`).join('');
      if (tips.length) {
        html += `<div class="chat-divider"></div><div class="chat-section-title">💡 Key Tips</div>`;
        html += tips.slice(0,3).map(t => `
          <div class="chat-tip-row">
            <span class="chat-tip-icon">${t.icon}</span>
            <div><strong style="font-size:13px">${t.title}</strong><br><span style="font-size:12px;color:var(--muted)">${t.body}</span></div>
          </div>`).join('');
      }
      appendBotMsg(html, ['Tell me about scams in Kandy', 'Is July safe?']);
    } catch {
      appendBotMsg(`<p>⚠️ Could not load checklist — backend might be offline.</p>`);
    }
    return;
  }

  removeBotTyping();
  appendBotMsg(
    `<p>I can give you detailed safety analysis for any Sri Lankan city. Try asking something like:</p>
     <p style="font-size:12px;color:var(--muted)">"Is Kandy safe for solo females?" or "What scams happen in Colombo?"</p>`,
    ['Tell me about Kandy', 'What scams are in Colombo?', 'Is it safe in July?', 'Family safety tips']
  );
}

/* ── Radar draw (inline canvas) ────────────────────────── */
function drawRadarInline(canvas, radar) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const cx = W / 2, cy = H / 2 + 5;
  const R = Math.min(W, H) / 2 - 28;
  const labels = Object.keys(radar);
  const values = Object.values(radar);
  const N = labels.length;
  const angle = i => (i / N) * Math.PI * 2 - Math.PI / 2;

  ctx.clearRect(0, 0, W, H);
  for (let r = 1; r <= 4; r++) {
    ctx.beginPath();
    for (let i = 0; i < N; i++) {
      const a = angle(i), rr = (r / 4) * R;
      i === 0 ? ctx.moveTo(cx + Math.cos(a)*rr, cy + Math.sin(a)*rr)
              : ctx.lineTo(cx + Math.cos(a)*rr, cy + Math.sin(a)*rr);
    }
    ctx.closePath();
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 1; ctx.stroke();
  }
  for (let i = 0; i < N; i++) {
    const a = angle(i);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(a)*R, cy + Math.sin(a)*R);
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.stroke();
  }
  ctx.beginPath();
  for (let i = 0; i < N; i++) {
    const a = angle(i), v = values[i] * R;
    i === 0 ? ctx.moveTo(cx + Math.cos(a)*v, cy + Math.sin(a)*v)
            : ctx.lineTo(cx + Math.cos(a)*v, cy + Math.sin(a)*v);
  }
  ctx.closePath();
  ctx.fillStyle = 'rgba(212,175,55,0.15)'; ctx.fill();
  ctx.strokeStyle = '#d4af37'; ctx.lineWidth = 2; ctx.stroke();
  for (let i = 0; i < N; i++) {
    const a = angle(i), v = values[i] * R;
    const dx = Math.cos(a), dy = Math.sin(a);
    ctx.beginPath();
    ctx.arc(cx + dx*v, cy + dy*v, 3.5, 0, Math.PI*2);
    const val = values[i];
    ctx.fillStyle = val > 0.6 ? '#ef4444' : val > 0.35 ? '#f59e0b' : '#22c55e';
    ctx.fill();
    ctx.font = 'bold 9px Inter,sans-serif';
    ctx.fillStyle = 'rgba(255,255,255,0.75)';
    const lx = cx + dx*(R+16), ly = cy + dy*(R+16);
    ctx.textAlign = lx < cx-2 ? 'right' : lx > cx+2 ? 'left' : 'center';
    ctx.textBaseline = ly < cy-2 ? 'bottom' : ly > cy+2 ? 'top' : 'middle';
    ctx.fillText(labels[i], lx, ly);
  }
}

function radarColor(val) {
  if (val > 0.6) return '#ef4444';
  if (val > 0.35) return '#f59e0b';
  return '#22c55e';
}

/* ── Event wiring ──────────────────────────────────────── */
chatSendBtn.addEventListener('click', () => sendMessage());
chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
chatClearBtn.addEventListener('click', () => {
  chatMessages.innerHTML = '';
  initChatGreeting();
});

document.querySelectorAll('.quick-ask-btn').forEach(btn => {
  btn.addEventListener('click', () => sendMessage(btn.dataset.msg));
});

// Profile/month change resets context message
chatProfile.addEventListener('change', () => {
  const label = chatProfile.options[chatProfile.selectedIndex].text;
  appendBotMsg(`<p>Got it! I'll tailor all advice for a <strong>${label}</strong>. What would you like to know?</p>`,
    ['What are the biggest risks?', 'Give me a safety checklist', 'Best cities to visit safely?']);
});

/* ── Greeting on load ──────────────────────────────────── */
function initChatGreeting() {
  appendBotMsg(
    `<p style="font-size:15px;font-weight:600;margin-bottom:6px">👋 Hello! I'm SafeTravel AI</p>
     <p style="font-size:13px;color:var(--muted)">I provide <strong>real-time, data-driven safety intelligence</strong> for Sri Lanka, powered by 16,000+ traveller reviews and live incident reports.</p>
     <p style="font-size:13px;margin-top:8px">Ask me anything — scam alerts, destination safety scores, seasonal warnings, or personalised tips for your travel style.</p>`,
    ['Is Kandy safe?', 'Scams in Colombo?', 'Solo female travel tips', 'Is July safe to visit?']
  );
}

// Initialise on tab switch
document.querySelector('[data-tab="advisor"]').addEventListener('click', () => {
  if (chatMessages.children.length === 0) initChatGreeting();
});

window.toggleCheck = function(i) {
  const el = document.getElementById(`chk-${i}`);
  if (el) el.classList.toggle('checked');
};

/* ── Dashboard (Tab 3) ─────────────────────────────────── */
async function loadDashboard() {
  try {
    const [statsRes, reportsRes, patternsRes] = await Promise.all([
      fetch(`${API}/admin/stats`),
      fetch(`${API}/admin/reports?per_page=50`),
      fetch(`${API}/admin/patterns`),
    ]);

    const stats = await statsRes.json();
    const reports = await reportsRes.json();
    const patterns = await patternsRes.json();

    document.getElementById('d-total').textContent = (stats.total_reports || 0).toLocaleString();
    document.getElementById('d-scams').textContent = (stats.scam_reports || 0).toLocaleString();
    document.getElementById('d-zones').textContent = (stats.total_zones || 0).toLocaleString();
    document.getElementById('d-highrisk').textContent = (stats.high_risk_zones || 0).toLocaleString();

    // Aggregate scam types from patterns
    const scamCounts = {};
    if (Array.isArray(patterns)) {
      patterns.forEach(p => {
        if (p.scam_type) {
          scamCounts[p.scam_type] = (scamCounts[p.scam_type] || 0) + (p.count || 1);
        }
      });
    }
    const scamTypes = Object.entries(scamCounts)
      .map(([k, v]) => ({ scam_type: k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()), count: v }))
      .sort((a, b) => b.count - a.count);
    
    const topLoc = Array.isArray(patterns) ? patterns.slice(0, 10).map(p => ({
      location: p.location,
      report_count: p.count
    })) : [];

    renderBarChart('chart-scam-types', scamTypes, 'scam_type', 'count');
    renderBarChart('chart-locations', topLoc, 'location', 'report_count');

    const tbody = document.getElementById('reports-tbody');
    const items = reports.items || (Array.isArray(reports) ? reports : []);
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="loading-row">No reports yet.</td></tr>';
    } else {
      tbody.innerHTML = items.map(r => {
        const hasUrl = r.url && r.url.startsWith('http');
        const trustedSources = ['adaderana', 'sundaytimes', 'daily_mirror', 'google_news', 'colombo_gazette', 'newsfirst', 'ceylon_today', 'themorning_lk', 'hirunews_lk', 'theisland_lk', 'economynext_lk', 'newswire_lk'];
        const isVerified = trustedSources.includes(r.source?.toLowerCase());
        const sourceLabel = (r.source || 'Verified Feed') + (isVerified ? ' <span title="Verified News Source" style="color: #1da1f2; font-size: 14px;">✔</span>' : '');
        
        const scamLabel = r.scam_type
          ? r.scam_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
          : '<span style="color:#64748b;font-style:italic;">Safety Incident</span>';
        const locationLabel = r.location_name || r.location
          ? (r.location_name || r.location)
          : '<span style="color:#64748b;font-style:italic;">Sri Lanka</span>';
        return `<tr>
          <td>#${r.id}</td>
          <td>${sourceLabel}${hasUrl ? `<a href="${r.url}" target="_blank" rel="noopener noreferrer" class="source-link" style="margin-left:5px" title="View Source">&#x1F517;</a>` : ''}</td>
          <td>${scamLabel}</td>
          <td><span class="risk-badge risk-${r.risk_level || 2}">${['', 'Low', 'Moderate', 'High'][r.risk_level || 2]}</span></td>
          <td>${locationLabel}</td>
          <td>${r.created_at ? new Date(r.created_at).toLocaleDateString() : 'Recent'}</td>
        </tr>`;
      }).join('');
    }

    const ptbody = document.getElementById('patterns-tbody');
    if (!patterns?.length) {
      ptbody.innerHTML = '<tr><td colspan="4" class="loading-row">No recurring patterns detected yet.</td></tr>';
    } else {
      ptbody.innerHTML = patterns.slice(0, 15).map(p => {
        const scamLabel = (p.scam_type || 'Incident').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        const avgRisk = Math.min(3, Math.max(1, Math.ceil(p.avg_risk || 2)));
        return `<tr>
          <td style="font-weight:600; color:var(--text);">${p.location}</td>
          <td>${scamLabel}</td>
          <td><span class="risk-badge" style="background:var(--accent-glow); color:var(--accent);">${p.count} incidents</span></td>
          <td><span class="risk-badge risk-${avgRisk}">${['', 'Low', 'Moderate', 'High'][avgRisk]}</span></td>
        </tr>`;
      }).join('');
    }
  } catch (err) {
    console.warn('[Dashboard] Error fetching admin statistics:', err);
    ['d-total','d-scams','d-zones','d-highrisk'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '—';
    });
  }
}

function renderBarChart(containerId, data, labelKey, valueKey) {
  const el = document.getElementById(containerId);
  if (!el || !data.length) return;
  const max = Math.max(...data.map(d => d[valueKey]));
  el.innerHTML = data.slice(0, 6).map(d => {
    const pct = max > 0 ? (d[valueKey] / max * 100).toFixed(1) : 0;
    const lbl = (d[labelKey] || '').replace(/_/g, ' ');
    return `<div class="bar-item">
      <span class="bar-label" title="${lbl}">${lbl}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <span class="bar-count">${d[valueKey]}</span>
    </div>`;
  }).join('');
}

/* ── Pipeline controls ──────────────────────────────────── */
document.getElementById('btn-run-pipeline').addEventListener('click', async () => {
  const el = document.getElementById('pipeline-status');
  el.textContent = 'Status: starting...';
  try {
    const res = await fetch(`${API}/pipeline/run`, { method: 'POST' });
    const d = await res.json();
    el.textContent = `Status: ${d.message}`;
    pollPipelineStatus(el);
  } catch { el.textContent = 'Status: backend offline'; }
});

document.getElementById('btn-recluster').addEventListener('click', async () => {
  const el = document.getElementById('pipeline-status');
  el.textContent = 'Status: clustering...';
  try {
    await fetch(`${API}/safety/recluster`, { method: 'POST' });
    el.textContent = 'Status: re-clustering started';
  } catch { el.textContent = 'Status: backend offline'; }
});

async function pollPipelineStatus(el) {
  const interval = setInterval(async () => {
    try {
      const res = await fetch(`${API}/pipeline/status`);
      const d = await res.json();
      el.textContent = `Status: ${d.status}`;
      if (d.status !== 'running') clearInterval(interval);
    } catch { clearInterval(interval); }
  }, 3000);
}
