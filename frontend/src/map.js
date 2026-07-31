import L from 'leaflet';
import 'leaflet.heat';

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
    this.markerGroup = L.layerGroup().addTo(this.map);
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
      const sourcesHtml = zone.sources ? Object.entries(zone.sources).map(([src, count]) => `${src}: ${count}`).join(' | ') : 'N/A';
      const scamTypesHtml = zone.scam_types 
        ? Object.entries(zone.scam_types).map(([type, count]) => `<li>${SCAM_LABELS[type] || type}: ${count}</li>`).join('') 
        : '<li>None</li>';
      const titlesHtml = zone.sample_titles && zone.sample_titles.length > 0 
        ? `<ul class="popup-titles" style="margin-top:8px; padding-left:14px;">${zone.sample_titles.map(t => {
            const title = t.title || "Report";
            const url = t.url || "#";
            
            return `
              <li style="margin-bottom:6px;">
                <a href="${url}" target="_blank" rel="noopener noreferrer" 
                   style="color:#6366f1; text-decoration:underline; font-weight:500; font-style:normal; display:inline-block;"
                   title="Open Original Source / Search">
                   "${title}" ↗
                </a>
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
            <strong>📊 Stats:</strong> ${zone.report_count} Reports (${zone.scam_count || 0} Scams)
          </div>
          <div class="popup-section">
            <strong>📡 Sources:</strong> ${sourcesHtml}
          </div>
          <div class="popup-section">
            <strong>🚨 Scam Types:</strong>
            <ul class="popup-scams">${scamTypesHtml}</ul>
          </div>
          ${titlesHtml ? `<div class="popup-section"><strong>📝 Recent Reports:</strong>${titlesHtml}</div>` : ''}
          <div class="popup-row" style="margin-top:8px;font-size:10px;color:#64748b;text-align:right;">
            Lat ${zone.center_lat?.toFixed(4)}, Lon ${zone.center_lon?.toFixed(4)}
          </div>
        </div>
      `;
      circle.bindPopup(popup, { minWidth: 260, maxWidth: 320 });

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
}
