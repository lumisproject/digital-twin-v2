import { useState, useEffect, useRef } from 'react'
import { supabase } from '../supabase'
import { useNavigate } from 'react-router-dom'
import IngestionWizard from '../components/IngestionWizard'
import ReactMarkdown from 'react-markdown'

export default function Dashboard() {
  const navigate = useNavigate()

  // -- State --
  const [appState, setAppState] = useState('LOADING') 
  const [session, setSession] = useState(null)
  const [projectData, setProjectData] = useState(null)
  const [risks, setRisks] = useState([])
  const [isIngesting, setIsIngesting] = useState(false)
  const [ingestionProjectId, setIngestionProjectId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [repoUrl, setRepoUrl] = useState('')
  
  // NEW: Chat Mode State
  const [chatMode, setChatMode] = useState('multi-turn') // 'multi-turn' | 'single-turn'
  
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
        // Initial risk load
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
        setIngestionProjectId(data.project_id)
        setIsIngesting(true)
      }
    } catch (e) { alert("Server connection failed.") }
  }

  const handleIngestionComplete = () => {
    setIsIngesting(false);
    window.location.reload(); // Refresh to load new risks/graph
  };

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
            mode: chatMode // <--- Pass the selected mode
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
  if (isIngesting) {
    return (
      <div className="page-center">
        <IngestionWizard projectId={ingestionProjectId} onComplete={handleIngestionComplete} />
      </div>
    )
  }

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
          <div className="info-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.9rem', overflow:'hidden', textOverflow:'ellipsis' }}>
                    {projectData?.repo_url?.split('/').pop()}
                  </span>
                  {/* RE-SYNC BUTTON */}
                  <button onClick={handleIngest} title="Re-sync Codebase" style={{background:'none', border:'none', cursor:'pointer', fontSize:'1.2rem'}}>
                    🔄
                  </button>
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
            {/* MODE TOGGLE */}
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
                    <div className="dots-container">
                      <span className="thinking-text">Exploring codebase...</span>
                      <div className="dot"></div><div className="dot"></div><div className="dot"></div>
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