import React, { useState } from 'react';

const DISTRICTS = [
  'Ampara', 'Anuradhapura', 'Badulla', 'Batticaloa', 'Colombo', 'Galle',
  'Gampaha', 'Hambantota', 'Jaffna', 'Kalutara', 'Kandy', 'Kegalle',
  'Kilinochchi', 'Kurunegala', 'Mannar', 'Matale', 'Matara', 'Monaragala',
  'Mullaitivu', 'Nuwara Eliya', 'Polonnaruwa', 'Puttalam', 'Ratnapura',
  'Trincomalee', 'Vavuniya'
];

const ASPECT_LABELS = {
  safety: { label: 'Safety', icon: '🛡️', color: '#ef4444', bg: '#fef2f2' },
  cleanliness: { label: 'Cleanliness', icon: '🧹', color: '#f59e0b', bg: '#fffbeb' },
  roads_access: { label: 'Roads & Access', icon: '🛣️', color: '#8b5cf6', bg: '#f5f3ff' },
  facilities: { label: 'Facilities', icon: '🏗️', color: '#0ea5e9', bg: '#f0f9ff' },
  crowd: { label: 'Crowd & Noise', icon: '👥', color: '#ec4899', bg: '#fdf2f8' },
  price: { label: 'Price & Value', icon: '💰', color: '#10b981', bg: '#ecfdf5' },
  scenery: { label: 'Scenery', icon: '🌄', color: '#06b6d4', bg: '#ecfeff' },
};

const POLARITY_CONFIG = {
  N: { label: 'Negative', color: '#ef4444', bg: '#fef2f2', border: '#fecaca', icon: '⚠️' },
  P: { label: 'Positive', color: '#10b981', bg: '#ecfdf5', border: '#a7f3d0', icon: '✓' },
  X: { label: 'Neutral', color: '#64748b', bg: '#f8fafc', border: '#e2e8f0', icon: '•' },
};

export default function LostInSriLanka() {
  const [activeTab, setActiveTab] = useState('map');

  return (
    <div style={S.page}>
      <div style={S.header}>
        <div style={S.headerInner}>
          <h1 style={S.brand}>
            Lost<span style={{ color: '#f59e0b' }}>in</span>SriLanka
          </h1>
          <p style={S.tagline}>What visitors report about Sri Lanka’s destinations</p>
        </div>
        <div style={S.tabsContainer}>
          <button
            style={activeTab === 'map' ? S.activeTab : S.tab}
            onClick={() => setActiveTab('map')}
          >
            🗺️ Map
          </button>
          <button
            style={activeTab === 'stories' ? S.activeTab : S.tab}
            onClick={() => setActiveTab('stories')}
          >
            📰 Stories & Videos
          </button>
          <button
            style={activeTab === 'review' ? S.activeTab : S.tab}
            onClick={() => setActiveTab('review')}
          >
            ✏️ Add a Review
          </button>
        </div>
      </div>

      <div style={S.contentWrap}>
        {activeTab === 'map' && <MapTab />}
        {activeTab === 'stories' && <StoriesTab />}
        {activeTab === 'review' && <AddReviewTab />}
      </div>
    </div>
  );
}

// ── Tabs Components ────────────────────────────────────────────────────────

function MapTab() {
  return (
    <div style={S.fadeIn}>
      <div style={S.ledeContainer}>
        <h2 style={S.lede}>Every destination in the study, and what visitors complain about there.</h2>
        <p style={S.sub}>
          46,854 reviews from 293 places across 19 districts, sorted into seven everyday topics. 
          Click a district or a dot to read the evidence behind any number.
        </p>
      </div>
      <div style={S.frameWrap}>
        {/* Placeholder for the dashboard/map iframe */}
        <div style={S.mapPlaceholder}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🗺️</div>
          <h3 style={{ margin: '0 0 8px 0', color: '#0f172a' }}>Interactive Map Viewer</h3>
          <p style={{ color: '#64748b', margin: 0, maxWidth: 400, lineHeight: 1.5 }}>
            The destination intelligence map will render here, connecting live reports with geographic data.
          </p>
          <button style={{ ...S.btn, marginTop: 24, background: '#f1f5f9', color: '#334155' }}>
            Load Map Data
          </button>
        </div>
      </div>
    </div>
  );
}

function StoriesTab() {
  return (
    <div style={S.fadeIn}>
      <div style={S.ledeContainer}>
        <h2 style={S.lede}>Longer stories, blog posts and videos about places in Sri Lanka.</h2>
        <p style={S.sub}>
          Anything here is for reading and watching only. Stories are <strong>never counted</strong> in any 
          of the numbers on this site — the same rule the collected news articles and videos already follow.
        </p>
      </div>

      <div style={S.grid2Col}>
        <div style={S.card}>
          <h3 style={S.cardTitle}>Add your story</h3>
          <p style={S.cardHint}>A trip write-up, a blog post, anything longer than a quick comment.</p>
          
          <div style={S.formGroup}>
            <label style={S.label}>Title</label>
            <input type="text" placeholder="Two days walking around Ella" style={S.input} />
          </div>
          <div style={S.formGroup}>
            <label style={S.label}>Which place? (optional)</label>
            <input type="text" placeholder="Ella Rock" style={S.input} />
          </div>
          <div style={S.formGroup}>
            <label style={S.label}>District (optional)</label>
            <select style={S.select}>
              {DISTRICTS.map(d => <option key={d}>{d}</option>)}
            </select>
          </div>
          <div style={S.formGroup}>
            <label style={S.label}>Your story</label>
            <textarea placeholder="Write as much as you like..." style={S.textarea} rows={6} />
          </div>
          <div style={S.formGroup}>
            <label style={S.label}>Link to a blog post or video (optional)</label>
            <input type="url" placeholder="https://..." style={S.input} />
          </div>
          <button style={S.btnPrimary}>Publish story</button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <div style={S.card}>
            <h3 style={S.cardTitle}>Stories from visitors</h3>
            <p style={S.cardHint}>Newest first.</p>
            <div style={S.emptyBox}>No stories published yet.</div>
          </div>

          <div style={S.card}>
            <h3 style={S.cardTitle}>Videos and articles we collected</h3>
            <p style={S.cardHint}>Gathered from YouTube and news sites, shown here, never counted.</p>
            <div style={S.formGroup}>
              <label style={S.label}>Filter by place</label>
              <input type="text" placeholder="Type a place, or leave blank for a mixture" style={S.input} />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <MediaCard 
                type="youtube" 
                title="Horton Plains National Park | World's End | Sri Lanka 🇱🇰"
                source="Nicole & Ryan"
                date="2022-03-12"
              />
              <MediaCard 
                type="news" 
                title="Clarion call to protect vulnerable Horton Plains NP"
                source="The Sunday Times, Sri Lanka"
                date="Sun, 05 Jun"
              />
              <MediaCard 
                type="youtube" 
                title="Riverston, Matale ❤️🍃 #srilanka #travel"
                source="Enviro Trails"
                date="2023-12-09"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AddReviewTab() {
  const [text, setText] = useState('');
  const [destination, setDestination] = useState('');
  const [district, setDistrict] = useState('Colombo');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleAnalyse = async (e) => {
    e.preventDefault();
    if (!text.trim() || !destination.trim()) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const res = await fetch('/analyse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, destination, district }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError('Could not reach the analysis backend. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={S.fadeIn}>
      <div style={S.ledeContainer}>
        <h2 style={S.lede}>Was the road broken? Were the toilets locked? Was there rubbish, or a crowd, or something that felt unsafe?</h2>
        <p style={S.sub}>
          We read what you write and sort it into everyday topics — one line at a time — so the people who look after these places can see what keeps going wrong. <strong>If we get it wrong, you can fix it.</strong>
        </p>
      </div>

      <div style={S.grid2Col}>
        {/* Left: Input */}
        <div>
          <div style={S.card}>
            <h3 style={S.cardTitle}>Your experience</h3>
            <p style={S.cardHint}>No name, no email, no account. Just what happened and where.</p>
            
            <form onSubmit={handleAnalyse}>
              <div style={S.formGroup}>
                <label style={S.label}>Which place?</label>
                <input 
                  type="text" 
                  value={destination}
                  onChange={e => setDestination(e.target.value)}
                  placeholder="Start typing, e.g. Kandy Lake" 
                  style={S.input} 
                  required
                />
              </div>
              <div style={S.formGroup}>
                <label style={S.label}>Which district is it in?</label>
                <select value={district} onChange={e => setDistrict(e.target.value)} style={S.select}>
                  {DISTRICTS.map(d => <option key={d}>{d}</option>)}
                </select>
              </div>
              <div style={S.formGroup}>
                <label style={S.label}>What happened?</label>
                <textarea 
                  value={text}
                  onChange={e => setText(e.target.value)}
                  placeholder="The path down to the beach is broken and there was rubbish everywhere, but the view is worth it." 
                  style={S.textarea} 
                  rows={6}
                  required
                />
                <div style={{ textAlign: 'right', fontSize: 11, color: '#94a3b8', marginTop: 4 }}>
                  {text.length} / 5000
                </div>
              </div>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <button type="submit" disabled={loading || !text || !destination} style={{ ...S.btnPrimary, opacity: loading || !text || !destination ? 0.6 : 1 }}>
                  {loading ? 'Analysing...' : 'Send it'}
                </button>
                <button type="button" style={S.btnGhost} onClick={() => {
                  setDestination('Sigiriya Rock');
                  setDistrict('Matale');
                  setText('The climb was exhausting but the views at the top were spectacular. However, the ticket price of $30 is extremely high for what it is, and the path was incredibly crowded making it hard to move.');
                }}>
                  Show me an example
                </button>
              </div>
              {error && <div style={{ marginTop: 16, padding: 12, borderRadius: 8, background: '#fee2e2', color: '#dc2626', fontSize: 13 }}>{error}</div>}
            </form>
          </div>
        </div>

        {/* Right: Output */}
        <div>
          <div style={S.card}>
            <h3 style={S.cardTitle}>What we understood</h3>
            <p style={S.cardHint}>We split what you wrote into separate points, and show the words that made us pick each topic.</p>
            
            {!result && !loading && (
              <div style={S.emptyBox}>Nothing yet. Write something on the left.</div>
            )}
            
            {loading && (
              <div style={S.emptyBox}>
                <div style={{ animation: 'pulse 1.5s infinite', fontSize: 24 }}>⚙️</div>
                <div style={{ marginTop: 8 }}>Processing your review...</div>
              </div>
            )}

            {result && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {result.segments.map((seg, idx) => {
                  const pol = POLARITY_CONFIG[seg.polarity] || POLARITY_CONFIG.X;
                  return (
                    <div key={idx} style={{ ...S.findingCard, borderLeft: `4px solid ${pol.color}` }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          <span style={{ ...S.findingPolBadge, background: pol.bg, color: pol.color }}>
                            {pol.icon} {pol.label}
                          </span>
                          {seg.aspects.map(a => {
                            const meta = ASPECT_LABELS[a] || { label: a, icon: '📌', color: '#64748b', bg: '#f1f5f9' };
                            return (
                              <span key={a} style={{ ...S.findingAspectTag, background: meta.bg, color: meta.color }}>
                                {meta.icon} {meta.label}
                              </span>
                            );
                          })}
                        </div>
                        {seg.aspects.length > 0 && (
                          <button style={S.fixBtn}>Fix this</button>
                        )}
                      </div>
                      
                      <div style={S.findingText}>"{seg.segment_text}"</div>
                      
                      {seg.triggered_words && seg.triggered_words.length > 0 && (
                        <div style={S.findingTriggered}>
                          Triggers: {seg.triggered_words.join(', ')}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function MediaCard({ type, title, source, date }) {
  return (
    <div style={S.mediaItem}>
      <div style={S.mediaKind}>{type}</div>
      <div>
        <a href="#" style={S.mediaTitle}>{title}</a>
        <div style={S.mediaSource}>{source} &bull; {date}</div>
      </div>
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────

const S = {
  page: {
    minHeight: '100vh',
    background: '#f8fafc',
    fontFamily: "'Inter', -apple-system, sans-serif",
  },
  header: {
    background: '#0f172a',
    paddingTop: 32,
    borderBottom: '1px solid #1e293b',
  },
  headerInner: {
    maxWidth: 1040,
    margin: '0 auto',
    padding: '0 32px',
  },
  brand: {
    fontSize: 28,
    fontWeight: 800,
    color: '#fff',
    margin: '0 0 4px',
    letterSpacing: '-0.03em',
  },
  tagline: {
    fontSize: 14,
    color: '#94a3b8',
    margin: 0,
    fontWeight: 500,
  },
  tabsContainer: {
    maxWidth: 1040,
    margin: '32px auto 0',
    padding: '0 32px',
    display: 'flex',
    gap: 8,
    overflowX: 'auto',
  },
  tab: {
    padding: '12px 20px',
    background: 'transparent',
    border: 'none',
    borderBottom: '3px solid transparent',
    color: '#cbd5e1',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'color 0.2s',
  },
  activeTab: {
    padding: '12px 20px',
    background: 'transparent',
    border: 'none',
    borderBottom: '3px solid #f59e0b',
    color: '#fff',
    fontSize: 14,
    fontWeight: 700,
    cursor: 'pointer',
  },
  contentWrap: {
    maxWidth: 1040,
    margin: '0 auto',
    padding: '40px 32px 80px',
  },
  fadeIn: {
    animation: 'fadeIn 0.3s ease-out',
  },
  ledeContainer: {
    marginBottom: 32,
    maxWidth: 700,
  },
  lede: {
    fontSize: 22,
    fontWeight: 700,
    color: '#0f172a',
    lineHeight: 1.4,
    margin: '0 0 12px 0',
    letterSpacing: '-0.02em',
  },
  sub: {
    fontSize: 15,
    color: '#475569',
    lineHeight: 1.6,
    margin: 0,
  },
  frameWrap: {
    background: '#fff',
    border: '1px solid #e2e8f0',
    borderRadius: 16,
    overflow: 'hidden',
    boxShadow: '0 10px 30px rgba(0,0,0,0.03)',
  },
  mapPlaceholder: {
    height: 500,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#f8fafc',
    textAlign: 'center',
    padding: 32,
  },
  grid2Col: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
    gap: 24,
    alignItems: 'start',
  },
  card: {
    background: '#fff',
    border: '1px solid #e2e8f0',
    borderRadius: 16,
    padding: 24,
    boxShadow: '0 4px 12px rgba(0,0,0,0.02)',
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: 700,
    color: '#0f172a',
    margin: '0 0 6px 0',
    letterSpacing: '-0.01em',
  },
  cardHint: {
    fontSize: 13,
    color: '#64748b',
    margin: '0 0 20px 0',
    lineHeight: 1.5,
  },
  formGroup: {
    marginBottom: 16,
  },
  label: {
    display: 'block',
    fontSize: 13,
    fontWeight: 600,
    color: '#334155',
    marginBottom: 6,
  },
  input: {
    width: '100%',
    padding: '10px 14px',
    borderRadius: 10,
    border: '1.5px solid #e2e8f0',
    fontSize: 14,
    color: '#0f172a',
    outline: 'none',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
    transition: 'border-color 0.2s',
  },
  select: {
    width: '100%',
    padding: '10px 14px',
    borderRadius: 10,
    border: '1.5px solid #e2e8f0',
    fontSize: 14,
    color: '#0f172a',
    outline: 'none',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
    cursor: 'pointer',
    background: '#fff',
  },
  textarea: {
    width: '100%',
    padding: '12px 14px',
    borderRadius: 10,
    border: '1.5px solid #e2e8f0',
    fontSize: 14,
    color: '#0f172a',
    outline: 'none',
    resize: 'vertical',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
    lineHeight: 1.6,
  },
  btnPrimary: {
    background: '#0ea5e9',
    color: '#fff',
    border: 'none',
    borderRadius: 10,
    padding: '10px 20px',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    boxShadow: '0 4px 12px rgba(14,165,233,0.25)',
    transition: 'filter 0.2s',
  },
  btnGhost: {
    background: 'transparent',
    color: '#0ea5e9',
    border: '1px solid #bae6fd',
    borderRadius: 10,
    padding: '10px 16px',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
  btn: {
    border: 'none',
    borderRadius: 8,
    padding: '10px 20px',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
  },
  emptyBox: {
    padding: 32,
    textAlign: 'center',
    background: '#f8fafc',
    borderRadius: 12,
    border: '1px dashed #cbd5e1',
    color: '#64748b',
    fontSize: 14,
  },
  findingCard: {
    background: '#fff',
    border: '1px solid #e2e8f0',
    borderRadius: 12,
    padding: '16px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.02)',
  },
  findingPolBadge: {
    fontSize: 11,
    fontWeight: 700,
    padding: '2px 8px',
    borderRadius: 6,
  },
  findingAspectTag: {
    fontSize: 11,
    fontWeight: 600,
    padding: '2px 8px',
    borderRadius: 6,
  },
  fixBtn: {
    background: 'transparent',
    border: 'none',
    color: '#0ea5e9',
    fontSize: 11,
    fontWeight: 600,
    cursor: 'pointer',
    textDecoration: 'underline',
  },
  findingText: {
    fontSize: 14,
    color: '#1e293b',
    lineHeight: 1.6,
    margin: 0,
    fontStyle: 'italic',
  },
  findingTriggered: {
    fontSize: 11,
    color: '#94a3b8',
    marginTop: 8,
  },
  mediaItem: {
    display: 'flex',
    gap: 12,
    alignItems: 'flex-start',
    padding: '12px 0',
    borderBottom: '1px solid #f1f5f9',
  },
  mediaKind: {
    fontSize: 10,
    fontWeight: 700,
    color: '#64748b',
    background: '#f1f5f9',
    padding: '3px 6px',
    borderRadius: 4,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  mediaTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: '#0f172a',
    textDecoration: 'none',
    display: 'block',
    marginBottom: 4,
  },
  mediaSource: {
    fontSize: 12,
    color: '#64748b',
  },
};
