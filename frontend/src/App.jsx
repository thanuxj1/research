import React, { useState } from 'react';
import SafeTravelLK_Page1 from './SafeTravelLK_Page1.jsx';
import SafeTravelLK_Analytics from './SafeTravelLK_Analytics.jsx';
import Component2 from './Component2.jsx';

export default function App() {
  const [currentPage, setCurrentPage] = useState('page1');

  return (
    <div style={{ minHeight: '100vh', background: currentPage === 'component2' ? '#ffffff' : '#0a0f1e' }}>

      {/* ── Global Top Navigation Bar (hidden on Component 2) ── */}
      {currentPage !== 'component2' && (
        <div style={{
          background: 'rgba(6, 10, 22, 0.97)',
          backdropFilter: 'blur(24px)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
          height: '48px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px',
          position: 'sticky',
          top: 0,
          zIndex: 1000,
        }}>

          {/* Left — Brand */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexShrink: 0 }}>
            <span style={{ fontSize: 17, lineHeight: 1 }}>🇱🇰</span>
            <span style={{
              color: '#f1f5f9', fontWeight: 700, fontSize: 14,
              letterSpacing: '-0.02em', whiteSpace: 'nowrap',
              fontFamily: "'Inter', system-ui, sans-serif",
            }}>
              SafeTravel <span style={{ color: '#06b6d4' }}>LK</span>
            </span>
          </div>

          {/* Center — Page Switcher Pill */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 2,
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 10,
            padding: '3px',
          }}>
            {[
              { id: 'page1', icon: '🗺️', label: 'Map' },
              { id: 'page2', icon: '📊', label: 'Analytics' },
              { id: 'component2', icon: '📑', label: 'Component 2' },
            ].map(({ id, icon, label }) => {
              const active = currentPage === id;
              return (
                <button
                  key={id}
                  onClick={() => setCurrentPage(id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '5px 16px',
                    borderRadius: 7,
                    border: 'none',
                    background: active ? 'rgba(6, 182, 212, 0.14)' : 'transparent',
                    color: active ? '#38bdf8' : '#64748b',
                    fontWeight: active ? 600 : 400,
                    fontSize: 12.5,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    whiteSpace: 'nowrap',
                    fontFamily: "'Inter', system-ui, sans-serif",
                    letterSpacing: '-0.01em',
                  }}
                >
                  <span style={{ fontSize: 13 }}>{icon}</span> {label}
                </button>
              );
            })}
          </div>

          {/* Right — Minimal live indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              background: '#10b981',
              boxShadow: '0 0 0 2px rgba(16,185,129,0.2), 0 0 7px rgba(16,185,129,0.55)',
              display: 'inline-block',
              flexShrink: 0,
            }} />
            <span style={{
              color: '#334155', fontSize: 11,
              fontFamily: 'monospace',
              letterSpacing: '0.04em',
            }}>
              live
            </span>
          </div>

        </div>
      )}

      {/* Render Active Page */}
      {currentPage === 'page1' ? (
        <SafeTravelLK_Page1
          onNavigateAnalytics={() => setCurrentPage('page2')}
          onNavigateComponent2={() => setCurrentPage('component2')}
        />
      ) : currentPage === 'page2' ? (
        <SafeTravelLK_Analytics
          onNavigateMap={() => setCurrentPage('page1')}
        />
      ) : (
        <Component2
          onNavigateMap={() => setCurrentPage('page1')}
        />
      )}
    </div>
  );
}
