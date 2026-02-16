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
  const bottomRef = useRef(null)
  const [repoUrl, setRepoUrl] = useState('')

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
        const res = await fetch(`http://localhost:5000/api/risks/${p.id}`)
        const d = await res.json()
        if (d.status === 'success') setRisks(d.risks)
      } else {
        setAppState('NO_PROJECT')
      }
    }
    boot()
  }, [navigate])

  // 2. THE WATCHER: Detects Webhooks and Completion
  useEffect(() => {
    if (appState !== 'READY' || !projectData?.id) return

    const watchBackend = async () => {
      try {
        const res = await fetch(`http://localhost:5000/api/ingest/status/${projectData.id}`)
        const data = await res.json()

        // TRIGGER WIZARD: If status is anything active
        const activeStatuses = ['STARTING', 'PROCESSING', 'Cloning', 'Analyzing', 'Processing', 'Cleanup', 'Intelligence']
        if (activeStatuses.includes(data.status)) {
          if (!isIngesting) {
            console.log("Sync detected via Heartbeat...");
            setIngestionProjectId(projectData.id)
            setIsIngesting(true)
          }
        }

        // TRIGGER RELOAD: If status is DONE, close wizard and hard refresh
        // This takes you back to the Dashboard automatically
        if (data.status === 'DONE') {
          console.log("Sync complete. Reloading application...");
          setIsIngesting(false)
          window.location.reload() 
        }
      } catch (e) { console.error("Watcher error", e) }
    }

    const timer = setInterval(watchBackend, 3000) 
    return () => clearInterval(timer)
  }, [appState, projectData?.id, isIngesting])

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // 3. Handlers
  const handleIngest = async () => {
    if (!repoUrl) return
    const res = await fetch('http://localhost:5000/api/ingest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: session.user.id, repo_url: repoUrl })
    })
    const data = await res.json()
    if (res.ok) {
      setIngestionProjectId(data.project_id)
      setIsIngesting(true)
    }
  }

  const handleIngestionComplete = () => {
    setShowWizard(false);
    window.location.reload(); // Force refresh to see new risks
  };

  const handleChat = async (e) => {
    e.preventDefault()
    if (!input.trim() || chatLoading) return
    
    const userMsg = { role: 'user', content: input }
    // 1. Add User Message
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setChatLoading(true)
    
    // 2. Add "Thinking" placeholder immediately
    setMessages(prev => [...prev, { role: 'lumis', content: '...', isThinking: true }])
    
    try {
      const res = await fetch('http://localhost:5000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectData.id, query: userMsg.content })
      })
      const data = await res.json()
      
      // 3. Replace placeholder with real answer
      setMessages(prev => {
        const filtered = prev.filter(m => !m.isThinking)
        return [...filtered, { role: 'lumis', content: data.response }]
      })
    } catch (err) {
      console.error("Chat error", err)
      // Remove thinking bubble on error
      setMessages(prev => prev.filter(m => !m.isThinking))
    } finally {
      setChatLoading(false)
    }
  }

  // --- VIEWS ---
  if (isIngesting) {
    return (
      <div className="page-center">
        <IngestionWizard 
            projectId={ingestionProjectId} 
            onComplete={handleIngestionComplete} 
        />
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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>
                    {projectData?.repo_url?.split('/').pop()}
                  </span>
                  <code style={{ fontSize: '0.7rem', color: '#71717a' }}>
                    {projectData?.last_commit?.substring(0, 7) || 'no-sync'}
                  </code>
              </div>
              <div style={{ borderTop: '1px solid #e4e4e7', paddingTop: '10px' }}>
                <div style={{ fontSize: '0.7rem', color: '#71717a', marginBottom: '4px' }}>GITHUB WEBHOOK</div>
                <code style={{ display: 'block', background: '#f4f4f5', padding: '8px', borderRadius: '4px', fontSize: '0.6rem', wordBreak: 'break-all' }}>
                  {`https://unsparing-kaley-unmodest.ngrok-free.dev/api/webhook/${session?.user?.id}/${projectData?.id}`}
                </code>
              </div>
          </div>
          
          <div className="section-title">Risk Monitor</div>
          <div className="risk-stack">
            {risks.length === 0 ? <div className="info-card">✅ System stable</div> : risks.map(r => (
              <div key={r.id} className="risk-card">
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
        <div className="stage-header"><span>Digital Twin Terminal</span></div>
        <div className="chat-scroll-area">
          <div className="message-wrapper">
            {messages.map((m, i) => (
              <div key={i} className={`message-row ${m.role}`}>
                <div className={`message-bubble ${m.isThinking ? 'thinking' : ''}`}>
                  {m.isThinking ? (
                    <div className="dots-container">
                      <span className="thinking-text">Exploring codebase...</span>
                      <div className="dot"></div>
                      <div className="dot"></div>
                      <div className="dot"></div>
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
                <input className="chat-input" placeholder="Ask Lumis..." value={input} onChange={e => setInput(e.target.value)} />
                <button type="submit" className="send-button">Send</button>
            </form>
        </div>
      </main>
    </div>
  )
}