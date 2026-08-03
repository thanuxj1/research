import L from 'leaflet';
import 'leaflet.heat';

export function isAccessibleWebUrl(url, source = '') {
  if (!url || typeof url !== 'string') return false;
  const trimmed = url.trim().toLowerCase();
  if (!trimmed || trimmed === '#' || trimmed === 'null' || trimmed === 'undefined') return false;
  if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) return false;

  const srcLower = (source || '').toLowerCase();
  const datasetKeywords = [
    'dataset', 'internal', 'kandypos', 'sl_police_db', 'synthetic', 
    'offline_archive', 'local_db', 'kaggle', 'benchmark', 'csv', 'json'
  ];
  if (datasetKeywords.some(kw => srcLower.includes(kw))) return false;
  if (trimmed.includes('localhost') || trimmed.includes('127.0.0.1')) return false;

  return true;
}

const RISK_COLOR = (score) => {
  if (score >= 0.7) return { color: '#ef4444', cls: 'badge-red',    label: 'High Risk' };
  if (score >= 0.4) return { color: '#f59e0b', cls: 'badge-yellow', label: 'Moderate Risk' };
  return               { color: '#fbbf24', cls: 'badge-yellow', label: 'Low-Moderate' };
};

const SCAM_LABELS = {
  gem_scam:           '💎 Gem Scam',
  tuk_tuk_scam:       '🛺 Tuk-Tuk Scam',
  overcharging:       '💰 Overcharging',
  fake_guide:         '🧑‍🦯 Fake Guide',
  transport_fraud:    '🚕 Transport Fraud',
  harassment:         '😨 Harassment',
  accommodation_scam: '🏨 Accommodation Scam',
  food_scam:          '🍽️ Food Scam',
  unsafe_area:        '⚠️ Unsafe Area',
};

export class SafetyMap {
  constructor(containerId) {
    const sriLankaBounds = [
      [5.8, 79.4], // SouthWest bound
      [9.9, 82.0]  // NorthEast bound
    ];

    this.map = L.map(containerId, { 
      zoomControl: true,
      maxBounds: sriLankaBounds,
      maxBoundsViscosity: 1.0,
      minZoom: 7
    });
    
    this.map.fitBounds(sriLankaBounds);

    // Dark tile layer using CartoDB dark tiles
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(this.map);

    this.heatLayer  = null;
    const hasClusterPlugin = typeof window !== 'undefined' && window.L && typeof window.L.markerClusterGroup === 'function';
    this.markerGroup = hasClusterPlugin
      ? window.L.markerClusterGroup({
          maxClusterRadius: 40,
          spiderfyOnMaxZoom: true,
          showCoverageOnHover: false,
          zoomToBoundsOnClick: true,
          disableClusteringAtZoom: 15,
        })
      : L.layerGroup();
    this.map.addLayer(this.markerGroup);

    this._allZones  = [];
    this._filters   = { high: true, med: true };
    window.map = this; // Global accessor for sidebar

    // Ensure map container size is recalculated once layout stabilizes
    setTimeout(() => {
      if (this.map) this.map.invalidateSize();
    }, 150);
  }

  setFilters(filters) {
    this._filters = filters;
    this._render(this._allZones);
  }

  updateHeatmap(zones) {
    this._allZones = zones;
    this._render(zones);
  }

  _render(zones) {
    // Clear existing layers
    if (this.heatLayer) {
      try { this.map.removeLayer(this.heatLayer); } catch (_) {}
      this.heatLayer = null;
    }
    this.markerGroup.clearLayers();

    const filtered = zones.filter(z => {
      if (z.risk_score >= 0.7 && !this._filters.high) return false;
      if (z.risk_score >= 0.2 && z.risk_score < 0.7 && !this._filters.med) return false;
      return z.center_lat && z.center_lon;
    });

    // Invalidate size if container was rendered hidden or zero size
    const size = this.map.getSize();
    if (size.x <= 0 || size.y <= 0) {
      this.map.invalidateSize();
    }

    // Heatmap layer safely rendered only if heat data exists and container size > 0
    const heatData = filtered.map(z => [z.center_lat, z.center_lon, z.risk_score]);
    if (heatData.length > 0 && this.map.getSize().x > 0 && this.map.getSize().y > 0) {
      try {
        this.heatLayer = L.heatLayer(heatData, {
          radius: 40,
          blur:   25,
          maxZoom: 12,
          gradient: { 0.2: '#f59e0b', 1.0: '#ef4444' },
        }).addTo(this.map);
      } catch (err) {
        console.warn('[SafetyMap] Heatmap canvas render deferred:', err);
      }
    }

    // Circle markers
    filtered.forEach(zone => {
      const rc = RISK_COLOR(zone.risk_score);
      const radius = 6 + zone.risk_score * 14;

      const circle = L.circleMarker([zone.center_lat, zone.center_lon], {
        radius,
        color:       rc.color,
        fillColor:   rc.color,
        fillOpacity: 0.35,
        weight:      2,
      });

      const locationName = zone.location_name || `Cluster ${zone.cluster_id}`;
      const cleanSources = zone.sources 
        ? Object.entries(zone.sources).filter(([src]) => src && src.toLowerCase() !== 'unknown')
        : [];
      const sourcesHtml = cleanSources.length > 0
        ? cleanSources.slice(0, 3).map(([src, count]) => `${src.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: ${count}`).join(' · ')
        : 'Verified Safety Feeds';

      const cleanScams = zone.scam_types 
        ? Object.entries(zone.scam_types).filter(([t]) => t && t.toLowerCase() !== 'safe' && t.toLowerCase() !== 'none')
        : [];
      const scamTypesHtml = cleanScams.length > 0
        ? cleanScams.map(([type, count]) => `<li>${SCAM_LABELS[type] || type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: ${count}</li>`).join('') 
        : '<li>General Warning</li>';

      const titlesHtml = zone.sample_titles && zone.sample_titles.length > 0 
        ? `<ul class="popup-titles" style="margin-top:8px; padding-left:14px;">${zone.sample_titles.slice(0, 3).map(t => {
            const title = t.title || "Report";
            const url = t.url;
            const source = t.source || t.source_label || '';
            const validUrl = isAccessibleWebUrl(url, source);
            
            return `
              <li style="margin-bottom:6px;">
                ${validUrl ? `
                  <a href="${url}" target="_blank" rel="noopener noreferrer" 
                     style="color:#818cf8; text-decoration:underline; font-weight:500;"
                     title="Open original webpage">
                     "${title}" ↗
                  </a>` : `
                  <span style="color:#cbd5e1; font-weight:500;">
                    "${title}"
                  </span>`}
              </li>`;
          }).join('')}</ul>`
        : '';

      const popup = `
        <div class="popup-header">
          <div class="popup-title">📍 ${locationName}</div>
          <span class="popup-badge ${rc.cls}">${rc.label} — ${(zone.risk_score * 100).toFixed(0)}%</span>
        </div>
        <div class="popup-body">
          <div class="popup-section">
            <strong>📊 Safety Incident Signals:</strong> ${zone.scam_count || zone.report_count} Verified Incidents
          </div>
          <div class="popup-section">
            <strong>🚨 Incident Types:</strong>
            <ul class="popup-scams">${scamTypesHtml}</ul>
          </div>
          ${titlesHtml ? `<div class="popup-section"><strong>📝 Recent Incident Reports:</strong>${titlesHtml}</div>` : ''}
          <div class="popup-row" style="margin-top:8px;font-size:10px;color:#64748b;text-align:right;">
            Lat ${zone.center_lat?.toFixed(4)}, Lon ${zone.center_lon?.toFixed(4)}
          </div>
        </div>
      `;
      circle.bindPopup(popup, { minWidth: 260, maxWidth: 320 });
      circle.on('click', (e) => {
        if (e && e.originalEvent) L.DomEvent.stopPropagation(e.originalEvent);

        // Ensure ONLY ONE popup is open: close right panel when map popup opens
        const intelPanel = document.getElementById('intelligence-panel');
        const warningsPanel = document.getElementById('warnings-panel');
        if (intelPanel) intelPanel.classList.add('hidden');
        if (warningsPanel) warningsPanel.style.display = 'block';
      });

      // Pulse animation for high-risk
      if (zone.risk_score >= 0.7) {
        const pulse = L.circleMarker([zone.center_lat, zone.center_lon], {
          radius: radius + 6, color: rc.color,
          fillOpacity: 0, weight: 1.5, opacity: 0.4,
        });
        this.markerGroup.addLayer(pulse);
      }

      this.markerGroup.addLayer(circle);
    });
  }
  zoomTo(lat, lon) {
    this.map.setView([lat, lon], 14);
  }

  /* ────────────────────────────────────────────────────────────────
   * DISTRICT CHOROPLETH LAYER
   * Renders one filled polygon per district, coloured by risk_tier.
   * Independent of the point heatmap/circle-marker layer above, so
   * either can be shown alone or both together.
   * ──────────────────────────────────────────────────────────────── */
  renderDistrictChoropleth(geojson) {
    if (this.districtLayer) {
      try { this.map.removeLayer(this.districtLayer); } catch (_) {}
      this.districtLayer = null;
    }
    this._districtGeojson = geojson;

    this.districtLayer = L.geoJSON(geojson, {
      style: (feature) => this._districtStyle(feature.properties),
      onEachFeature: (feature, layer) => this._bindDistrictInteractions(feature, layer),
    });

    if (this._showChoropleth !== false) {
      this.districtLayer.addTo(this.map);
    }
    this._renderDistrictLegend(geojson.legend);
    return this.districtLayer;
  }

  toggleDistrictChoropleth(show) {
    this._showChoropleth = show;
    const legendEl = document.getElementById('district-legend');
    const pointLegendEl = document.getElementById('point-legend');
    if (!this.districtLayer) return;
    if (show) {
      if (!this.map.hasLayer(this.districtLayer)) this.districtLayer.addTo(this.map);
      if (legendEl) legendEl.style.display = 'block';
      if (pointLegendEl) pointLegendEl.style.display = 'none';
    } else {
      if (this.map.hasLayer(this.districtLayer)) this.map.removeLayer(this.districtLayer);
      if (legendEl) legendEl.style.display = 'none';
      if (pointLegendEl) pointLegendEl.style.display = 'flex';
    }
  }

  _districtStyle(props) {
    const TIER_COLORS = {
      insufficient_data: '#6b7280',
      low:                '#22c55e',
      moderate:           '#eab308',
      high:               '#f97316',
      severe:             '#ef4444',
    };
    const isInsufficient = props.risk_tier === 'insufficient_data' || props.risk_score_0_1 == null || (props.report_count != null && props.report_count < 3);
    const color = isInsufficient ? '#6b7280' : (TIER_COLORS[props.risk_tier] || '#6b7280');
    return {
      color: '#0f172a',
      weight: 1,
      fillColor: color,
      fillOpacity: isInsufficient ? 0.18 : 0.55,
      dashArray: isInsufficient ? '4 3' : null,
    };
  }

  _bindDistrictInteractions(feature, layer) {
    const p = feature.properties;
    const TIER_LABELS = {
      insufficient_data: '⚪ Insufficient Data',
      low:                '🟢 Low Risk',
      moderate:           '🟡 Moderate Risk',
      high:               '🟠 High Risk',
      severe:             '🔴 Severe Risk',
    };
    const isInsufficient = p.risk_tier === 'insufficient_data' || p.risk_score_0_1 == null || (p.report_count != null && p.report_count < 3);
    const tierLabel = isInsufficient ? '⚪ Insufficient Data' : (TIER_LABELS[p.risk_tier] || p.risk_tier || '⚪ Insufficient Data');
    const confStr = (p.confidence || 'insufficient_data').replace('_', ' ');

    // ── Hover tooltip: quick-glance summary ──
    const tooltipHtml = `
      <div class="district-tooltip">
        <div class="dt-title">${p.district} District (${tierLabel})</div>
        <div class="dt-row">${p.report_count ?? 0} reports analysed (${p.scam_report_count ?? 0} scam-flagged)</div>
        <div class="dt-row dt-conf">Confidence: <b>${confStr}</b></div>
        ${isInsufficient
          ? `<div class="dt-row dt-warn">⚪ Insufficient evidence — district receives no risk claim</div>`
          : p.incident_rate_per_100k_visitors != null
            ? `<div class="dt-row">${p.incident_rate_per_100k_visitors.toFixed(2)} incidents / 100k visitors (SLTDA-normalised)</div>`
            : `<div class="dt-row dt-warn">No SLTDA visitor baseline for this district — score is density-based</div>`}
        <div style="font-size:10px; color:#cbd5e1; margin-top:4px; border-top:1px solid rgba(255,255,255,0.1); padding-top:4px;">💡 Click anywhere on map to assess a specific location</div>
      </div>`;
    layer.bindTooltip(tooltipHtml, { sticky: true, direction: 'top', className: 'district-tooltip-wrap' });
  }

  _renderDistrictLegend(legend) {
    if (!legend) return;
    let el = document.getElementById('district-legend');
    if (!el) {
      el = document.createElement('div');
      el.id = 'district-legend';
      el.className = 'district-legend glass';
      document.body.appendChild(el);
    }
    el.innerHTML = `
      <div class="dl-title">District Risk Legend</div>
      ${Object.entries(legend).map(([key, v]) => `
        <div class="dl-row">
          <span class="dl-swatch" style="background:${v.color}"></span>
          <span>${v.label}</span>
        </div>`).join('')}
      <div class="dl-note">Tiers recalculated relative to current evidence. Insufficient data districts receive no colour claim.</div>
    `;
    if (this._showChoropleth === false) {
      el.style.display = 'none';
    } else {
      el.style.display = 'block';
    }
  }
}
