import React, { useState } from 'react';
import SafeTravelLK_Page1 from './SafeTravelLK_Page1.jsx';
import SafeTravelLK_Analytics from './SafeTravelLK_Analytics.jsx';

export default function App() {
  const [currentPage, setCurrentPage] = useState('page1'); // 'page1' | 'page2'

  return (
    <div style={{ minHeight: '100vh', background: '#0a0f1e' }}>
      {/* Global Top Page Navigation Header */}
      <div style={{
        background: 'rgba(10, 15, 30, 0.98)',
        borderBottom: '1px solid rgba(100, 116, 139, 0.15)',
        padding: '0 24px',
        height: '46px',
        display: 'flex',
        alignItems: 'center',
        justify: 'space-between',
        position: 'sticky',
        top: 0,
        zIndex: 1000,
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.4)'
      }}>
        {/* Left System Badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '16px' }}>🇱🇰</span>
          <span style={{ color: '#f1f5f9', fontWeight: 800, fontSize: '13px', letterSpacing: '-0.01em' }}>
            SafeTravel <span style={{ color: '#06b6d4' }}>LK</span>
          </span>
          <span style={{ color: '#334155', fontSize: '12px' }}>|</span>
          <span style={{ color: '#64748b', fontSize: '11px', fontFamily: 'monospace' }}>
            IT22629180 PhD Safety Intelligence System
          </span>
        </div>

        {/* Center Switcher Buttons */}
        <div style={{ display: 'flex', gap: '6px', background: 'rgba(15, 23, 42, 0.8)', padding: '3px', borderRadius: '8px', border: '1px solid rgba(100, 116, 139, 0.2)' }}>
          <button
            onClick={() => setCurrentPage('page1')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 14px',
              borderRadius: '6px',
              border: currentPage === 'page1' ? '1px solid rgba(6, 182, 212, 0.5)' : 'none',
              background: currentPage === 'page1' ? 'rgba(6, 182, 212, 0.18)' : 'transparent',
              color: currentPage === 'page1' ? '#38bdf8' : '#94a3b8',
              fontWeight: currentPage === 'page1' ? 700 : 500,
              fontSize: '12px',
              cursor: 'pointer',
              transition: 'all 0.15s ease'
            }}
          >
            <span>🗺️</span> Page 1: Safety Intelligence Map
          </button>

          <button
            onClick={() => setCurrentPage('page2')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 14px',
              borderRadius: '6px',
              border: currentPage === 'page2' ? '1px solid rgba(34, 211, 238, 0.5)' : 'none',
              background: currentPage === 'page2' ? 'rgba(34, 211, 238, 0.18)' : 'transparent',
              color: currentPage === 'page2' ? '#22d3ee' : '#94a3b8',
              fontWeight: currentPage === 'page2' ? 700 : 500,
              fontSize: '12px',
              cursor: 'pointer',
              transition: 'all 0.15s ease'
            }}
          >
            <span>📊</span> Page 2: Research Analytics & Signals
          </button>
        </div>

        {/* Right Status Indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', boxShadow: '0 0 8px #10b981' }}></span>
          <span style={{ color: '#94a3b8', fontSize: '11px', fontFamily: 'monospace' }}>
            Live Backend Pipeline Active
          </span>
        </div>
      </div>

      {/* Render Active Page */}
      {currentPage === 'page1' ? (
        <SafeTravelLK_Page1 onNavigateAnalytics={() => setCurrentPage('page2')} />
      ) : (
        <SafeTravelLK_Analytics onNavigateMap={() => setCurrentPage('page1')} />
      )}
    </div>
  );
}
