import { useState, useEffect, useRef } from 'react'
import { supabase } from '../supabase'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'

export default function Dashboard() {
  const navigate = useNavigate()

  // -- State --
  const [appState, setAppState] = useState('LOADING') 
  const [session, setSession] = useState(null)
  const [projectData, setProjectData] = useState(null)
  const [risks, setRisks] = useState([])
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [repoUrl, setRepoUrl] = useState('')
  const [chatMode, setChatMode] = useState('multi-turn') 
  
  const bottomRef = useRef(null)

  // 1. Boot: Check Session and Load Project
  useEffect(() => {
    const boot = async () => {
      const { data: { session: s } } = await supabase.auth.getSession()
      if (!s) { navigate('/login'); return; }
      setSession(s)

      const { data: p } = await supabase.from('projects').select('*').eq('user_id', s.user.id).maybeSingle()
      if (p) {
        setProjectData(p)
        setAppState('READY')
        
        // Initial check: Is it currently syncing?
        try {
            const res = await fetch(`http://localhost:5000/api/ingest/status/${p.id}`)
            const statusData = await res.json()
            if (['starting', 'processing'].includes(statusData.status)) {
                navigate(`/syncing?project_id=${p.id}`)
                return
            }
        } catch (e) {}

        // Load Risks
        try {
            const res = await fetch(`http://localhost:5000/api/risks/${p.id}`)
            const d = await res.json()
            if (d.status === 'success') setRisks(d.risks)
        } catch(e) { console.error("Risk fetch error", e) }
      } else {
        setAppState('NO_PROJECT')
      }
    }
    boot()
  }, [navigate])

  // NEW: Poll for "Thinking" logs when waiting for chat
  useEffect(() => {
    if (!chatLoading || !projectData?.id) return

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:5000/api/ingest/status/${projectData.id}`)
        const data = await res.json()
        
        if (data.logs && data.logs.length > 0) {
          // Get the very last log that starts with a brain emoji
          const lastThought = data.logs.filter(l => l.includes('🧠')).pop()
          if (lastThought) {
             // Update the "thinking" message in the UI
             setMessages(prev => prev.map(m => 
               m.isThinking ? { ...m, thinkingText: lastThought.replace('🧠', '').trim() } : m
             ))
          }
        }
      } catch (e) { console.error("Poll error", e) }
    }, 1000)

    return () => clearInterval(interval)
  }, [chatLoading, projectData])

  // Scroll to bottom on new message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 2. Handlers
  const handleIngest = async () => {
    const urlToUse = repoUrl || projectData?.repo_url
    if (!urlToUse) return

    try {
      const res = await fetch('http://localhost:5000/api/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: session.user.id, repo_url: urlToUse })
      })
      const data = await res.json()
      if (res.ok) {
        navigate(`/syncing?project_id=${data.project_id}`)
      }
    } catch (e) { alert("Server connection failed.") }
  }

  const handleChat = async (e) => {
    e.preventDefault()
    if (!input.trim() || chatLoading) return
    
    const userMsg = { role: 'user', content: input }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setChatLoading(true)
    
    // Add Thinking Bubble
    setMessages(prev => [...prev, { role: 'lumis', content: '...', isThinking: true }])
    
    try {
      const res = await fetch('http://localhost:5000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            project_id: projectData.id, 
            query: userMsg.content,
            mode: chatMode 
        })
      })
      const data = await res.json()
      
      // Replace Thinking Bubble with Answer
      setMessages(prev => {
        const filtered = prev.filter(m => !m.isThinking)
        return [...filtered, { role: 'lumis', content: data.response }]
      })
    } catch (err) {
      console.error("Chat error", err)
      setMessages(prev => [...prev.filter(m => !m.isThinking), { role: 'lumis', content: "Error: Could not reach Lumis Core." }])
    } finally {
      setChatLoading(false)
    }
  }

  // --- VIEWS ---
  if (appState === 'LOADING') return <div className="page-center"><div className="spinner"></div></div>

  if (appState === 'NO_PROJECT') {
    return (
      <div className="page-center">
        <div className="auth-card" style={{ maxWidth: '440px' }}>
          <div className="auth-header">
            <h1>Activate Workspace</h1>
            <p>Connect a GitHub repository to begin.</p>
          </div>
          <input className="input-field" value={repoUrl} onChange={e => setRepoUrl(e.target.value)} placeholder="https://github.com/username/repo" />
          <button onClick={handleIngest} className="btn btn-primary" style={{width:'100%', marginTop:'1.25rem'}}>Begin Deep Analysis</button>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-header"><div className="brand">Lumis Intelligence</div></div>
        <div className="sidebar-content">
          <div className="section-title">Active Repository</div>
          
          <div className="info-card" style={{ padding: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.95rem', color: '#09090b' }}>
                        {projectData?.repo_url?.split('/').pop()}
                    </div>
                    <a 
                      href={projectData?.repo_url} 
                      target="_blank" 
                      rel="noreferrer"
                      style={{ fontSize: '0.75rem', color: '#71717a', textDecoration: 'none', display:'block', marginTop:'2px' }}
                    >
                      View on GitHub ↗
                    </a>
                  </div>
                  
                  <button 
                    onClick={handleIngest} 
                    title="Force Re-sync" 
                    className="btn-text"
                    style={{ fontSize:'1.1rem', padding:'4px', marginTop:'-4px' }}
                  >
                    🔄
                  </button>
              </div>

              {/* GitHub Webhook Info */}
              <div style={{ borderTop: '1px solid #e4e4e7', paddingTop: '10px', marginTop: '10px' }}>
                <div style={{ fontSize: '0.7rem', color: '#71717a', marginBottom: '4px', fontWeight: 600 }}>GITHUB WEBHOOK</div>
                <code style={{ display: 'block', background: '#f4f4f5', padding: '8px', borderRadius: '4px', fontSize: '0.6rem', wordBreak: 'break-all', fontFamily: 'var(--font-mono)' }}>
                    {`https://your-ngrok-url.ngrok-free.dev/api/webhook/${session?.user?.id}/${projectData?.id}`}
                </code>
              </div>

              {/* Commit ID Section */}
              <div style={{ borderTop: '1px solid #e4e4e7', paddingTop: '10px', marginTop: '10px' }}>
                <div style={{ fontSize: '0.7rem', color: '#71717a', marginBottom: '4px', fontWeight: 600, letterSpacing: '0.02em' }}>
                    CURRENT COMMIT
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: projectData?.last_commit ? '#10b981' : '#f59e0b' }}></div>
                    <code style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: '#09090b', background: '#f4f4f5', padding: '2px 6px', borderRadius: '4px' }}>
                        {projectData?.last_commit ? projectData.last_commit.substring(0, 7) : 'PENDING'}
                    </code>
                </div>
              </div>
          </div>
          
          <div className="section-title">Risk Monitor</div>
          <div className="risk-stack">
            {risks.length === 0 ? <div className="info-card" style={{color:'#71717a'}}>No active risks detected.</div> : risks.map((r, i) => (
              <div key={i} className="risk-card">
                  <div className="risk-header"><span className="risk-type">{r.risk_type}</span></div>
                  <div className="risk-desc">{r.description}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="sidebar-footer">
           <button className="btn-text" onClick={() => supabase.auth.signOut().then(() => navigate('/'))}>Logout</button>
        </div>
      </aside>

      <main className="main-stage">
        <div className="stage-header">
            <span>Digital Twin Terminal</span>
            <div style={{display:'flex', gap:'8px', background:'#f4f4f5', padding:'4px', borderRadius:'6px'}}>
                <button 
                    onClick={() => setChatMode('multi-turn')}
                    style={{
                        background: chatMode === 'multi-turn' ? 'white' : 'transparent',
                        border: 'none', padding: '4px 12px', borderRadius: '4px', fontSize:'0.8rem', cursor:'pointer',
                        boxShadow: chatMode === 'multi-turn' ? '0 1px 2px rgba(0,0,0,0.1)' : 'none',
                        fontWeight: chatMode === 'multi-turn' ? 600 : 400
                    }}
                >
                    Multi-Turn
                </button>
                <button 
                    onClick={() => setChatMode('single-turn')}
                    style={{
                        background: chatMode === 'single-turn' ? 'white' : 'transparent',
                        border: 'none', padding: '4px 12px', borderRadius: '4px', fontSize:'0.8rem', cursor:'pointer',
                        boxShadow: chatMode === 'single-turn' ? '0 1px 2px rgba(0,0,0,0.1)' : 'none',
                        fontWeight: chatMode === 'single-turn' ? 600 : 400
                    }}
                >
                    Single-Turn
                </button>
            </div>
        </div>
        
        <div className="chat-scroll-area">
          <div className="message-wrapper">
            {messages.map((m, i) => (
              <div key={i} className={`message-row ${m.role}`}>
                <div className={`message-bubble ${m.isThinking ? 'thinking' : ''}`}>
                  {m.isThinking ? (
                    <div className="dots-container" style={{display:'flex', flexDirection:'column', alignItems:'flex-start'}}>
                      {/* Show the dynamic thought or default text */}
                      <span className="thinking-text" style={{fontSize:'0.8rem', marginBottom:'4px'}}>
                        {m.thinkingText || "Exploring codebase..."}
                      </span>
                      <div style={{display:'flex', gap:'4px'}}>
                        <div className="dot"></div><div className="dot"></div><div className="dot"></div>
                      </div>
                    </div>
                  ) : (
                    <ReactMarkdown>{m.content}</ReactMarkdown>
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>
        
        <div className="input-zone">
            <form className="input-container" onSubmit={handleChat}>
                <input 
                    className="chat-input" 
                    placeholder="Ask Lumis about architecture, bugs, or risks..." 
                    value={input} 
                    onChange={e => setInput(e.target.value)} 
                />
                <button type="submit" className="send-button">Send</button>
            </form>
        </div>
      </main>
    </div>
  )
}