import React, { useState } from 'react';
import DestinationRecommendations from './DestinationRecommendations.jsx';
import BudgetPlanner from './BudgetPlanner.jsx';

export default function Component2({ onNavigateMap }) {
  // Page view state: 'home' | 'explore_destinations' | 'budget_planner'
  const [subView, setSubView] = useState('home');

  // Selected item / Filter states
  const [favorites, setFavorites] = useState(['Ella', 'Sigiriya']);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  // Toggle favorite
  const toggleFavorite = (name, e) => {
    if (e) e.stopPropagation();
    setFavorites((prev) =>
      prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name]
    );
  };

  // Catalog for home page cards
  const homeDestinations = [
    {
      name: 'Ella',
      image: '/images/ella.png',
      tag: 'Nature & Hikes',
      weather: '22°C Clear',
      crowd: 'Moderate',
      budget: '$45 / day',
      desc: 'Famous for Nine Arch Bridge, Little Adam’s Peak, tea estates, and epic waterfall views.',
    },
    {
      name: 'Sigiriya',
      image: '/images/sigiriya_hero.png',
      tag: 'Heritage & History',
      weather: '29°C Sunny',
      crowd: 'High',
      budget: '$60 / day',
      desc: 'Ancient palace fortress on a giant 200m rock with 5th-century frescoes and water gardens.',
    },
    {
      name: 'Galle Fort',
      image: '/images/galle.png',
      tag: 'Colonial Architecture',
      weather: '28°C Tropical',
      crowd: 'Moderate',
      budget: '$70 / day',
      desc: 'UNESCO Portuguese & Dutch oceanfront fortress filled with cobblestone streets, boutiques & cafes.',
    },
    {
      name: 'Nuwara Eliya',
      image: '/images/nuwara_eliya.png',
      tag: 'Cool Highlands',
      weather: '16°C Misty',
      crowd: 'Low',
      budget: '$50 / day',
      desc: 'Sri Lanka’s "Little England" surrounded by waterfalls, colonial mansions, and tea plantations.',
    },
    {
      name: 'Mirissa Beach',
      image: '/images/mirissa.png',
      tag: 'Coastal & Surfing',
      weather: '30°C Sunny',
      crowd: 'Moderate',
      budget: '$40 / day',
      desc: 'Pristine golden beach famous for blue whale watching, Coconut Tree Hill, and sunset seafood.',
      overlayText: 'Estimated Total Budget: $280',
    },
  ];

  // ═══════════════════════════════════════════════════════════════════════════
  // SUB-PAGES ROUTING
  // ═══════════════════════════════════════════════════════════════════════════

  // Page 2: AI Destination Recommendations
  if (subView === 'explore_destinations') {
    return <DestinationRecommendations onBack={() => setSubView('home')} />;
  }

  // Page 3: Intelligent Budget Planner Page
  if (subView === 'budget_planner') {
    return <BudgetPlanner onBack={() => setSubView('home')} />;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // PAGE 1: Component 2 Main Screen
  // ═══════════════════════════════════════════════════════════════════════════
  return (
    <div style={styles.container}>
      {/* Top Banner & Sigiriya Hero Background Container */}
      <div style={styles.heroSection}>
        <div style={styles.heroOverlay} />

        {/* Header Bar */}
        <header style={styles.headerBar}>
          <div>
            <h1 style={styles.greetingTitle}>Hello, Traveler! 👋</h1>
            <p style={styles.greetingSubtitle}>
              Discover Sri Lanka with AI – Get smart recommendations, plan your trip and explore our culture.
            </p>
          </div>

          <div style={styles.userControls}>
            {/* Notification Bell */}
            <div style={{ position: 'relative' }}>
              <button
                onClick={() => setNotificationsOpen(!notificationsOpen)}
                style={styles.iconButton}
                title="Notifications"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#1e293b" strokeWidth="2">
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                  <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
                </svg>
                <span style={styles.notifBadge} />
              </button>

              {/* Notifications Dropdown */}
              {notificationsOpen && (
                <div style={styles.notifDropdown}>
                  <div style={styles.notifHeader}>
                    <strong>Notifications</strong>
                  </div>
                  <div style={styles.notifItem}>
                    <span style={{ fontSize: 16 }}>🌤️</span>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a' }}>Ideal weather in Sigiriya</div>
                      <div style={{ fontSize: 11, color: '#64748b' }}>Clear skies forecast for tomorrow morning</div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* User Profile Avatar */}
            <div style={styles.avatarWrapper}>
              <img
                src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=120&auto=format&fit=crop&q=80"
                alt="User Avatar"
                style={styles.avatarImg}
              />
            </div>
          </div>
        </header>

        {/* 3 Main AI Action Cards */}
        <div style={styles.cardsGrid}>
          {/* Card 1: AI Destination Recommendations */}
          <div style={styles.card}>
            <div style={{ ...styles.cardIconBadge, background: '#10b981' }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.2">
                <path d="M12 2a8 8 0 0 0-8 8c0 5.25 8 12 8 12s8-6.75 8-12a8 8 0 0 0-8-8z"></path>
                <circle cx="12" cy="10" r="3"></circle>
              </svg>
            </div>
            <h2 style={styles.cardTitle}>AI Destination Recommendations</h2>
            <p style={styles.cardDesc}>
              Get personalized destination recommendations based on live weather and crowd predictions.
            </p>
            <button
              onClick={() => setSubView('explore_destinations')}
              style={{ ...styles.cardButton, background: '#10b981' }}
            >
              Explore Destinations
            </button>
          </div>

          {/* Card 2: Intelligent Budget Planner */}
          <div style={styles.card}>
            <div style={{ ...styles.cardIconBadge, background: '#2563eb' }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.2">
                <rect x="4" y="2" width="16" height="20" rx="2"></rect>
                <line x1="8" y1="6" x2="16" y2="6"></line>
                <line x1="16" y1="14" x2="16" y2="18"></line>
              </svg>
            </div>
            <h2 style={styles.cardTitle}>Intelligent Budget Planner</h2>
            <p style={styles.cardDesc}>
              Plan your trip with AI-powered budget estimation, route planning and hotel suggestions.
            </p>
            <button
              onClick={() => setSubView('budget_planner')}
              style={{ ...styles.cardButton, background: '#2563eb' }}
            >
              Plan My Trip
            </button>
          </div>

          {/* Card 3: Cultural Q&A Assistant */}
          <div style={styles.card}>
            <div style={{ ...styles.cardIconBadge, background: '#8b5cf6' }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
            </div>
            <h2 style={styles.cardTitle}>Cultural Q&A Assistant</h2>
            <p style={styles.cardDesc}>
              Ask anything about Sri Lankan culture, traditions, places and get instant AI-powered answers.
            </p>
            <button
              onClick={() => setSubView('explore_destinations')}
              style={{ ...styles.cardButton, background: '#8b5cf6' }}
            >
              Ask a Question
            </button>
          </div>
        </div>
      </div>

      {/* Popular Destinations Section */}
      <section style={styles.popularSection}>
        <div style={styles.popularHeader}>
          <h3 style={styles.popularTitle}>Popular Destinations</h3>
          <button onClick={() => setSubView('explore_destinations')} style={styles.viewAllBtn}>
            View All ↗
          </button>
        </div>

        {/* Horizontal Row */}
        <div style={styles.destinationsRow}>
          {homeDestinations.map((dest, idx) => {
            const isFav = favorites.includes(dest.name);
            return (
              <div
                key={idx}
                onClick={() => setSubView('explore_destinations')}
                style={styles.destCard}
              >
                <img src={dest.image} alt={dest.name} style={styles.destCardImage} />

                <button
                  onClick={(e) => toggleFavorite(dest.name, e)}
                  style={styles.heartBtn}
                  title="Bookmark Destination"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill={isFav ? '#ef4444' : 'rgba(0,0,0,0.3)'}
                    stroke={isFav ? '#ef4444' : '#ffffff'}
                    strokeWidth="2"
                  >
                    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
                  </svg>
                </button>

                <div style={styles.destCardOverlay}>
                  {dest.overlayText && (
                    <span style={styles.estimatedBudgetBadge}>
                      {dest.overlayText}
                    </span>
                  )}
                  <span style={styles.destCardTitle}>{dest.name}</span>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}

// ── Styles strictly following the provided mockup reference ──
const styles = {
  container: {
    minHeight: '100vh',
    background: '#ffffff',
    fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
    color: '#0f172a',
    paddingBottom: '40px',
  },

  heroSection: {
    position: 'relative',
    backgroundImage: `url('/images/sigiriya_hero.png')`,
    backgroundSize: 'cover',
    backgroundPosition: 'center 35%',
    padding: '36px 40px 60px 40px',
    boxShadow: 'inset 0 -50px 40px #ffffff',
  },

  heroOverlay: {
    position: 'absolute',
    inset: 0,
    background: 'linear-gradient(180deg, rgba(255, 255, 255, 0.40) 0%, rgba(255, 255, 255, 0.15) 45%, rgba(255, 255, 255, 0.85) 100%)',
    zIndex: 1,
  },

  headerBar: {
    position: 'relative',
    zIndex: 2,
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    maxWidth: '1200px',
    margin: '0 auto 32px auto',
  },

  greetingTitle: {
    fontSize: '32px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 6px 0',
    letterSpacing: '-0.025em',
  },

  greetingSubtitle: {
    fontSize: '14.5px',
    color: '#475569',
    margin: 0,
    fontWeight: '400',
  },

  userControls: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },

  iconButton: {
    width: '42px',
    height: '42px',
    borderRadius: '50%',
    background: '#ffffff',
    border: '1px solid rgba(226, 232, 240, 0.8)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.05)',
  },

  notifBadge: {
    position: 'absolute',
    top: '10px',
    right: '10px',
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    background: '#ef4444',
  },

  notifDropdown: {
    position: 'absolute',
    top: '50px',
    right: 0,
    width: '280px',
    background: '#ffffff',
    borderRadius: '14px',
    boxShadow: '0 12px 32px rgba(0,0,0,0.12)',
    border: '1px solid #e2e8f0',
    zIndex: 100,
    padding: '12px',
  },

  notifHeader: {
    fontSize: '13px',
    paddingBottom: '8px',
    borderBottom: '1px solid #f1f5f9',
    marginBottom: '8px',
  },

  notifItem: {
    display: 'flex',
    gap: '10px',
    padding: '6px 0',
  },

  avatarWrapper: {
    width: '42px',
    height: '42px',
    borderRadius: '50%',
    overflow: 'hidden',
    border: '2px solid #ffffff',
    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
  },

  avatarImg: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  },

  cardsGrid: {
    position: 'relative',
    zIndex: 2,
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: '24px',
    maxWidth: '1200px',
    margin: '0 auto',
  },

  card: {
    background: 'rgba(255, 255, 255, 0.92)',
    backdropFilter: 'blur(16px)',
    border: '1px solid rgba(255, 255, 255, 0.8)',
    borderRadius: '20px',
    padding: '30px 26px',
    boxShadow: '0 16px 36px -10px rgba(0, 0, 0, 0.08)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
  },

  cardIconBadge: {
    width: '52px',
    height: '52px',
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: '20px',
    boxShadow: '0 8px 18px rgba(0,0,0,0.12)',
  },

  cardTitle: {
    fontSize: '18px',
    fontWeight: '700',
    color: '#0f172a',
    margin: '0 0 10px 0',
    lineHeight: '1.3',
  },

  cardDesc: {
    fontSize: '13.5px',
    color: '#475569',
    margin: '0 0 24px 0',
    lineHeight: '1.5',
    flex: 1,
  },

  cardButton: {
    width: '100%',
    padding: '12px 18px',
    borderRadius: '10px',
    border: 'none',
    color: '#ffffff',
    fontSize: '13.5px',
    fontWeight: '600',
    cursor: 'pointer',
    textAlign: 'center',
  },

  popularSection: {
    maxWidth: '1200px',
    margin: '10px auto 0 auto',
    padding: '0 40px',
  },

  popularHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
  },

  popularTitle: {
    fontSize: '20px',
    fontWeight: '700',
    color: '#0f172a',
    margin: 0,
  },

  viewAllBtn: {
    background: 'none',
    border: 'none',
    color: '#059669',
    fontWeight: '600',
    fontSize: '13px',
    cursor: 'pointer',
  },

  destinationsRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(5, 1fr)',
    gap: '16px',
  },

  destCard: {
    position: 'relative',
    height: '210px',
    borderRadius: '16px',
    overflow: 'hidden',
    cursor: 'pointer',
    boxShadow: '0 8px 20px rgba(0,0,0,0.08)',
  },

  destCardImage: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  },

  heartBtn: {
    position: 'absolute',
    top: '12px',
    right: '12px',
    width: '32px',
    height: '32px',
    borderRadius: '50%',
    background: 'rgba(255,255,255,0.4)',
    backdropFilter: 'blur(8px)',
    border: 'none',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
  },

  destCardOverlay: {
    position: 'absolute',
    inset: 0,
    background: 'linear-gradient(180deg, rgba(0,0,0,0) 50%, rgba(0,0,0,0.75) 100%)',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'flex-end',
    padding: '14px',
  },

  estimatedBudgetBadge: {
    fontSize: '10px',
    fontWeight: '600',
    color: 'rgba(255,255,255,0.9)',
    marginBottom: '4px',
  },

  destCardTitle: {
    fontSize: '15px',
    fontWeight: '700',
    color: '#ffffff',
  },
};
