import React, { useState } from 'react';
import { askCulturalQuestion } from './api.js';

// Pre-defined Popular Questions matching reference UI design
const POPULAR_QUESTIONS = [
  "What is Esala Perahera?",
  "What are traditional Sri Lankan foods?",
  "Best time to visit Sri Lanka?",
  "What to wear in Sri Lanka?",
  "Etiquette for locals",
];

export default function CulturalAssistant({ onBack }) {
  const [questionInput, setQuestionInput] = useState('');
  const [loading, setLoading] = useState(false);

  // Chat starts EMPTY - user initiates the question
  const [chatHistory, setChatHistory] = useState([]);

  // Debug Inspector State for temporary backend input/output visualization
  const [rawRequestPayload, setRawRequestPayload] = useState(null);
  const [rawResponseJson, setRawResponseJson] = useState(null);
  const [isLiveApi, setIsLiveApi] = useState(false);
  const [showDebugPanel, setShowDebugPanel] = useState(true);

  // Helper to format current time string (e.g. "10:32 AM")
  const getCurrentTimeStr = () => {
    const now = new Date();
    return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const handleSendQuestion = async (customQuestion = null, e = null) => {
    if (e) e.preventDefault();
    const query = customQuestion !== null ? customQuestion : questionInput;
    if (!query.trim()) return;

    const timeStr = getCurrentTimeStr();

    // Append user question message
    const userMsg = { type: 'user', text: query, time: timeStr };
    setChatHistory((prev) => [...prev, userMsg]);

    if (customQuestion === null) {
      setQuestionInput('');
    }

    setLoading(true);

    const res = await askCulturalQuestion(query);
    if (res) {
      const resultObj = res.result || {};
      const responseContent = resultObj.response || {};

      const assistantMsg = {
        type: 'assistant',
        intent: resultObj.predicted_intent || 'cultural_qa',
        confidence: resultObj.confidence || 0.9,
        title: responseContent.title || 'Cultural Information',
        description: responseContent.description || 'Please follow local Sri Lankan cultural guidelines.',
        time: getCurrentTimeStr(),
      };

      setChatHistory((prev) => [...prev, assistantMsg]);
      setRawRequestPayload(res.requestPayload || { question: query });
      setRawResponseJson(res.rawJson || resultObj);
      setIsLiveApi(!!res.isLive);
    }
    setLoading(false);
  };

  return (
    <div style={styles.pageContainer}>
      {/* Top Header Navigation */}
      <div style={styles.topHeader}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          {onBack && (
            <button onClick={onBack} style={styles.backBtn}>
              ← Back
            </button>
          )}
          <div>
            <h1 style={styles.mainTitle}>Cultural Q&A Assistant</h1>
            <p style={styles.subTitle}>
              Ask anything about Sri Lankan culture, traditions and travel
            </p>
          </div>
        </div>
      </div>

      {/* Main 2-Column Grid */}
      <div style={styles.contentGrid}>
        
        {/* LEFT COLUMN: Chat Area + Bottom Input Bar */}
        <div style={styles.leftColumn}>
          
          {/* Chat Messages Flow */}
          <div style={styles.chatScrollArea}>
            {chatHistory.length === 0 ? (
              /* Empty Placeholder State when starting fresh */
              <div style={styles.emptyPlaceholder}>
                <div style={styles.emptyIconContainer}>
                  <span style={{ fontSize: 30 }}>🏛️</span>
                </div>
                <h3 style={{ fontSize: 18, fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                  Ask Cultural Q&A Assistant
                </h3>
                <p style={{ fontSize: 14, color: '#64748b', margin: 0, maxWidth: '420px', lineHeight: '1.5' }}>
                  Type your question below or select from <strong>Popular Questions</strong> on the right to start exploring Sri Lankan customs and etiquette.
                </p>
              </div>
            ) : (
              chatHistory.map((msg, idx) => (
                <React.Fragment key={idx}>
                  {msg.type === 'user' ? (
                    /* User Question Bubble (Right Aligned, Mint Green) */
                    <div style={styles.userBubbleWrapper}>
                      <div style={styles.userBubble}>
                        <div style={styles.userBubbleText}>{msg.text}</div>
                        <div style={styles.userBubbleMeta}>
                          <span>{msg.time}</span>
                          <span style={styles.checkIcon}>✓✓</span>
                        </div>
                      </div>
                    </div>
                  ) : (
                    /* AI Assistant Response Card (Left Aligned, White Card) */
                    <div style={styles.assistantCardWrapper}>
                      <div style={styles.assistantCard}>
                        {msg.title && (
                          <div style={styles.assistantTitle}>{msg.title}</div>
                        )}
                        
                        <div style={styles.assistantTextContent}>
                          {msg.description.split('\n').map((line, lIdx) => (
                            <div key={lIdx} style={{ marginBottom: line.trim() === '' ? 8 : 4 }}>
                              {line}
                            </div>
                          ))}
                        </div>

                        <div style={styles.assistantMetaRow}>
                          <span style={styles.timeSubtext}>{msg.time}</span>
                        </div>
                      </div>
                    </div>
                  )}
                </React.Fragment>
              ))
            )}

            {loading && (
              <div style={styles.assistantCardWrapper}>
                <div style={{ ...styles.assistantCard, padding: '16px 20px', color: '#64748b' }}>
                  <span style={styles.typingDot}></span> Thinking & analyzing cultural intent...
                </div>
              </div>
            )}
          </div>

          {/* Bottom Floating Input Bar */}
          <form onSubmit={(e) => handleSendQuestion(null, e)} style={styles.inputBarForm}>
            <input
              type="text"
              value={questionInput}
              onChange={(e) => setQuestionInput(e.target.value)}
              placeholder="Ask your question..."
              style={styles.inputBarField}
            />

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {/* Mic Icon */}
              <button type="button" style={styles.iconMicBtn} title="Voice Input">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2">
                  <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path>
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                  <line x1="12" y1="19" x2="12" y2="22"></line>
                </svg>
              </button>

              {/* Solid Green Send Button */}
              <button type="submit" disabled={loading} style={styles.sendGreenBtn} title="Send Question">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.4" style={{ transform: 'rotate(45deg)', margin: '0 0 2px 2px' }}>
                  <line x1="22" y1="2" x2="11" y2="13"></line>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                </svg>
              </button>
            </div>
          </form>
        </div>

        {/* RIGHT COLUMN: "Popular Questions" Card */}
        <div style={styles.rightColumn}>
          <div style={styles.popularQuestionsCard}>
            <h2 style={styles.popularTitle}>Popular Questions</h2>

            <div style={styles.questionsStack}>
              {POPULAR_QUESTIONS.map((qText, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSendQuestion(qText)}
                  style={styles.questionPillBtn}
                >
                  {qText}
                </button>
              ))}
            </div>

            <button
              onClick={() => handleSendQuestion("What are common Sri Lankan cultural customs?")}
              style={styles.viewAllBtn}
            >
              View All
            </button>
          </div>
        </div>

      </div>

      {/* ── TEMPORARY BACKEND INPUT & OUTPUT INSPECTOR PANEL ── */}
      <div style={styles.debugInspectorContainer}>
        <div style={styles.debugInspectorHeader}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: isLiveApi ? '#10b981' : '#f59e0b',
              boxShadow: isLiveApi ? '0 0 8px #10b981' : '0 0 8px #f59e0b',
            }} />
            <span style={{ fontSize: 13, fontWeight: 700, color: '#f8fafc' }}>
              🔌 Questions API Inspector — {isLiveApi ? 'Live Server Connected (http://127.0.0.1:5000/questions/predict)' : 'Fallback Simulation Mode'}
            </span>
          </div>
          <button
            onClick={() => setShowDebugPanel(!showDebugPanel)}
            style={styles.debugToggleBtn}
          >
            {showDebugPanel ? 'Hide API Inspector ▲' : 'Show API Inspector ▼'}
          </button>
        </div>

        {showDebugPanel && (
          <div style={styles.debugBodyGrid}>
            {/* 1. Sending Input (Request Payload) */}
            <div style={styles.debugColumn}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={styles.debugColHeader}>
                  📤 Sending Input (POST /questions/predict)
                </span>
                <span style={styles.debugMethodTag}>POST</span>
              </div>
              <pre style={styles.codeBlock}>
                {rawRequestPayload
                  ? JSON.stringify(rawRequestPayload, null, 2)
                  : '// Click any question or submit input to inspect request payload'}
              </pre>
            </div>

            {/* 2. Receiving Output (Response JSON) */}
            <div style={styles.debugColumn}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ ...styles.debugColHeader, color: isLiveApi ? '#34d399' : '#fbbf24' }}>
                  📥 Receiving Output (JSON Response)
                </span>
                <span style={{
                  ...styles.debugStatusTag,
                  background: isLiveApi ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                  color: isLiveApi ? '#34d399' : '#fbbf24',
                }}>
                  {isLiveApi ? '200 OK (Live)' : 'Fallback Output'}
                </span>
              </div>
              <pre style={{
                ...styles.codeBlock,
                borderColor: isLiveApi ? 'rgba(52, 211, 153, 0.4)' : 'rgba(251, 191, 36, 0.3)',
                color: isLiveApi ? '#6ee7b7' : '#fde68a'
              }}>
                {rawResponseJson
                  ? JSON.stringify(rawResponseJson, null, 2)
                  : '// Awaiting API response output...'}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Exact Design Styles Matching the Uploaded Reference Image ──
const styles = {
  pageContainer: {
    minHeight: '100vh',
    background: '#f8fafc',
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    color: '#0f172a',
    padding: '32px 48px 60px 48px',
    boxSizing: 'border-box',
  },

  topHeader: {
    maxWidth: '1280px',
    margin: '0 auto 28px auto',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  mainTitle: {
    fontSize: '26px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 4px 0',
    letterSpacing: '-0.02em',
  },

  subTitle: {
    fontSize: '14px',
    color: '#64748b',
    margin: 0,
    fontWeight: '400',
  },

  backBtn: {
    padding: '8px 16px',
    borderRadius: '10px',
    border: '1px solid #cbd5e1',
    background: '#ffffff',
    color: '#334155',
    fontSize: '13px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },

  contentGrid: {
    maxWidth: '1280px',
    margin: '0 auto',
    display: 'grid',
    gridTemplateColumns: '1fr 340px',
    gap: '28px',
    alignItems: 'start',
  },

  /* Left Column Chat Layout */
  leftColumn: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  },

  chatScrollArea: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
    minHeight: '400px',
  },

  emptyPlaceholder: {
    background: '#ffffff',
    borderRadius: '20px',
    border: '1px dashed #cbd5e1',
    padding: '48px 32px',
    textAlign: 'center',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '340px',
  },

  emptyIconContainer: {
    width: '60px',
    height: '60px',
    borderRadius: '50%',
    background: '#ecfdf5',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: '16px',
  },

  /* User Question Bubble (Right Aligned, Mint Green) */
  userBubbleWrapper: {
    display: 'flex',
    justifyContent: 'flex-end',
    width: '100%',
  },

  userBubble: {
    background: '#dcfce7',
    border: '1px solid #bbf7d0',
    borderRadius: '18px 18px 4px 18px',
    padding: '14px 20px',
    maxWidth: '80%',
    boxShadow: '0 2px 10px rgba(16, 185, 129, 0.06)',
  },

  userBubbleText: {
    fontSize: '14.5px',
    fontWeight: '600',
    color: '#0f172a',
    lineHeight: '1.4',
  },

  userBubbleMeta: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: '4px',
    fontSize: '11.5px',
    color: '#059669',
    marginTop: '6px',
    fontWeight: '600',
  },

  checkIcon: {
    fontSize: '13px',
    letterSpacing: '-2px',
  },

  /* Assistant Answer Card (Left Aligned, White Card) */
  assistantCardWrapper: {
    display: 'flex',
    justifyContent: 'flex-start',
    width: '100%',
  },

  assistantCard: {
    background: '#ffffff',
    borderRadius: '18px',
    border: '1px solid #e2e8f0',
    padding: '24px 28px',
    maxWidth: '92%',
    boxShadow: '0 4px 20px rgba(0, 0, 0, 0.03)',
  },

  assistantTitle: {
    fontSize: '16px',
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: '12px',
  },

  assistantTextContent: {
    fontSize: '14.5px',
    color: '#1e293b',
    lineHeight: '1.65',
    fontWeight: '400',
  },

  assistantMetaRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: '16px',
    paddingTop: '12px',
    borderTop: '1px solid #f1f5f9',
  },

  intentTag: {
    fontSize: '11px',
    fontWeight: '700',
    color: '#8b5cf6',
    background: '#f3e8ff',
    padding: '3px 10px',
    borderRadius: '8px',
  },

  timeSubtext: {
    fontSize: '11.5px',
    color: '#94a3b8',
  },

  typingDot: {
    display: 'inline-block',
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    background: '#8b5cf6',
    marginRight: '8px',
  },

  /* Bottom Floating Input Bar */
  inputBarForm: {
    background: '#ffffff',
    borderRadius: '18px',
    border: '1px solid #e2e8f0',
    padding: '8px 10px 8px 20px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    boxShadow: '0 8px 30px rgba(0, 0, 0, 0.04)',
    marginTop: '10px',
  },

  inputBarField: {
    flex: 1,
    border: 'none',
    background: 'transparent',
    fontSize: '14.5px',
    color: '#0f172a',
    outline: 'none',
    height: '40px',
  },

  iconMicBtn: {
    width: '38px',
    height: '38px',
    borderRadius: '50%',
    border: 'none',
    background: 'transparent',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    transition: 'background 0.15s ease',
  },

  sendGreenBtn: {
    width: '44px',
    height: '44px',
    borderRadius: '12px',
    border: 'none',
    background: '#059669',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    boxShadow: '0 4px 14px rgba(5, 150, 105, 0.3)',
    transition: 'background 0.15s ease',
  },

  /* Right Column: "Popular Questions" Card */
  rightColumn: {
    display: 'flex',
    flexDirection: 'column',
  },

  popularQuestionsCard: {
    background: '#ffffff',
    borderRadius: '20px',
    border: '1px solid #e2e8f0',
    padding: '24px',
    boxShadow: '0 4px 20px rgba(0, 0, 0, 0.03)',
  },

  popularTitle: {
    fontSize: '18px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 18px 0',
    letterSpacing: '-0.01em',
  },

  questionsStack: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },

  questionPillBtn: {
    width: '100%',
    padding: '14px 16px',
    borderRadius: '12px',
    border: '1.5px solid #e2e8f0',
    background: '#ffffff',
    color: '#334155',
    fontSize: '13.5px',
    fontWeight: '600',
    textAlign: 'left',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },

  viewAllBtn: {
    width: '100%',
    height: '42px',
    marginTop: '16px',
    borderRadius: '12px',
    border: '1.5px solid #cbd5e1',
    background: '#ffffff',
    color: '#2563eb',
    fontSize: '13.5px',
    fontWeight: '700',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },

  /* Debug API Inspector Panel Styles */
  debugInspectorContainer: {
    maxWidth: '1280px',
    margin: '32px auto 0 auto',
    background: '#0f172a',
    borderRadius: '16px',
    border: '1px solid #1e293b',
    overflow: 'hidden',
    boxShadow: '0 10px 30px rgba(0,0,0,0.15)',
  },

  debugInspectorHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '14px 20px',
    background: '#1e293b',
    borderBottom: '1px solid #334155',
  },

  debugToggleBtn: {
    background: 'rgba(255, 255, 255, 0.08)',
    border: '1px solid rgba(255, 255, 255, 0.12)',
    color: '#94a3b8',
    fontSize: '12px',
    fontWeight: '600',
    padding: '4px 12px',
    borderRadius: '6px',
    cursor: 'pointer',
  },

  debugBodyGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '20px',
    padding: '20px',
    background: '#090d16',
  },

  debugColumn: {
    display: 'flex',
    flexDirection: 'column',
  },

  debugColHeader: {
    fontSize: '11px',
    fontWeight: '700',
    color: '#38bdf8',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },

  debugMethodTag: {
    fontSize: '10px',
    fontWeight: '800',
    background: 'rgba(56, 189, 248, 0.15)',
    color: '#38bdf8',
    padding: '2px 8px',
    borderRadius: '4px',
  },

  debugStatusTag: {
    fontSize: '10px',
    fontWeight: '800',
    padding: '2px 8px',
    borderRadius: '4px',
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
    maxHeight: '260px',
    overflowY: 'auto',
    lineHeight: 1.45,
  },
};
