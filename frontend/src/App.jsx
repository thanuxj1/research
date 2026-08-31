import React, { useState } from 'react';
import Component2 from './Component2.jsx';
import DestinationRecommendations from './DestinationRecommendations.jsx';
import BudgetPlanner from './BudgetPlanner.jsx';
import CulturalAssistant from './CulturalAssistant.jsx';
import ReviewAnalyser from './ReviewAnalyser.jsx';
import LostInSriLanka from './LostInSriLanka.jsx';

const NAV_ITEMS = [
  { id: 'home',         label: 'Home',                 icon: '🏠',  color: '#10b981' },
  { id: 'destinations', label: 'Explore Destinations', icon: '🗺️',  color: '#10b981' },
  { id: 'budget',       label: 'Budget Planner',        icon: '💰',  color: '#2563eb' },
  { id: 'reviews',      label: 'Reviews',               icon: '⭐',  color: '#f59e0b' },
  { id: 'cultural',     label: 'Cultural Q&A',          icon: '🏛️',  color: '#8b5cf6' },
  { id: 'analyse',      label: 'Review Analyser',       icon: '🔍',  color: '#ec4899' },
];

export default function App() {
  const [page, setPage] = useState('home');
  const active = NAV_ITEMS.find(n => n.id === page);

  return (
    <div style={{ minHeight: '100vh', background: '#06101A', fontFamily: "'Inter', system-ui, sans-serif" }}>

      {/* ── Sticky Top Navigation Bar ── */}
      <nav style={NAV.bar}>
        <div style={NAV.inner}>

          {/* Brand */}
          <div style={NAV.brand}>
            <span style={NAV.brandText}>
              Travel<span style={NAV.brandAccent}>Lens</span>
            </span>
          </div>

          {/* Separator */}
          <div style={NAV.sep} />

          {/* Nav Pills */}
          <div style={NAV.pills}>
            {NAV_ITEMS.map(item => {
              const isActive = page === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setPage(item.id)}
                  style={{
                    ...NAV.pill,
                    color: isActive ? '#E8B84B' : 'rgba(239,247,242,0.48)',
                    borderBottomColor: isActive ? '#E8B84B' : 'transparent',
                    background: isActive ? 'rgba(232,184,75,0.07)' : 'transparent',
                    fontWeight: isActive ? 600 : 500,
                  }}
                >
                  <span style={{ fontSize: 13 }}>{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>

          {/* Live status dot */}
          <div style={NAV.statusGroup}>
            <span style={NAV.liveDot} />
            <span style={NAV.liveLabel}>live</span>
          </div>

        </div>
      </nav>

      {/* ── Page Content ── */}
      <main style={{ paddingTop: 0 }}>
        {page === 'home' && (
          <Component2
            onNavigateMap={undefined}
          />
        )}
        {page === 'destinations' && (
          <DestinationRecommendations
            onBack={() => setPage('home')}
          />
        )}
        {page === 'budget' && (
          <BudgetPlanner
            onBack={() => setPage('home')}
          />
        )}
        {page === 'reviews' && (
          <LostInSriLanka />
        )}
        {page === 'cultural' && (
          <CulturalAssistant
            onBack={() => setPage('home')}
          />
        )}
        {page === 'analyse' && (
          <ReviewAnalyser
            onBack={() => setPage('home')}
          />
        )}
      </main>
    </div>
  );
}

// ── Navigation styles ──────────────────────────────────────────────────────────
const NAV = {
  bar: {
    position: 'sticky',
    top: 0,
    zIndex: 1000,
    background: '#0D1B2A',
    borderBottom: '1px solid rgba(239,247,242,0.07)',
    boxShadow: '0 4px 20px rgba(0,0,0,0.35)',
  },
  inner: {
    maxWidth: 1400,
    margin: '0 auto',
    padding: '0 24px',
    height: 52,
    display: 'flex',
    alignItems: 'center',
    gap: 0,
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    flexShrink: 0,
    marginRight: 28,
  },
  brandText: {
    fontSize: 15.5,
    fontWeight: 800,
    color: '#EFF7F2',
    letterSpacing: '-0.025em',
    lineHeight: 1,
  },
  brandAccent: {
    color: '#E8B84B',
  },
  sep: {
    display: 'none',
  },
  pills: {
    flex: 1,
    display: 'flex',
    alignItems: 'stretch',
    gap: 0,
    height: '100%',
  },
  pill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '0 15px',
    border: 'none',
    borderBottom: '3px solid transparent',
    borderRadius: 0,
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    height: '100%',
    fontFamily: "'Inter', system-ui, sans-serif",
    color: 'rgba(239,247,242,0.48)',
    background: 'transparent',
    transition: 'color 0.13s, background 0.13s, border-color 0.13s',
  },
  statusGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    flexShrink: 0,
    marginLeft: 'auto',
    paddingLeft: 16,
  },
  liveDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: '#10b981',
    boxShadow: '0 0 0 2px rgba(16,185,129,0.2), 0 0 8px rgba(16,185,129,0.6)',
    display: 'inline-block',
  },
  liveLabel: {
    fontSize: 11,
    fontWeight: 600,
    color: '#10b981',
    letterSpacing: '0.10em',
    textTransform: 'uppercase',
  },
};

