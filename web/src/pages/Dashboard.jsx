import { useState, useEffect, useRef } from 'react'
import { supabase } from '../supabase'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'

export default function Dashboard() {
  const navigate = useNavigate()

  const [appState, setAppState] = useState('LOADING') 
  const [session, setSession] = useState(null)
  const [projectData, setProjectData] = useState(null)
  const [risks, setRisks] = useState([])
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [repoUrl, setRepoUrl] = useState('')
  const [copied, setCopied] = useState(false)
  const [chatMode, setChatMode] = useState('single-turn') 
  const [reasoning, setReasoning] = useState(true) 
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
        
        try {
            const res = await fetch(`http://localhost:5000/api/ingest/status/${p.id}`)
            const statusData = await res.json()
            // Catching both cases for the sync wizard redirection
            if (['starting', 'processing', 'PROCESSING', 'STARTING'].includes(statusData.status)) {
                navigate(`/syncing?project_id=${p.id}`)
                return
            }
        } catch (e) {}

        fetchRisks(p.id)
      } else {
        setAppState('NO_PROJECT')
      }
    }
    boot()
  }, [navigate])

  const fetchRisks = async (id) => {
    try {
        const res = await fetch(`http://localhost:5000/api/risks/${id}`)
        const d = await res.json()
        if (d.status === 'success') setRisks(d.risks)
    } catch(e) { console.error("Risk fetch error", e) }
  }

  // 2. The Watcher: Handles thought logs and completion trigger
  useEffect(() => {
    if (!projectData?.id) return

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:5000/api/ingest/status/${projectData.id}`)
        const data = await res.json()
        if (['PROCESSING', 'STARTING'].includes(data.status)) {
             navigate(`/syncing?project_id=${projectData.id}`)
        }
        if (chatLoading && data.logs && data.logs.length > 0) {
          const lastThought = data.logs.filter(l => l.includes('🧠') || l.includes('🤔')).pop()
          if (lastThought) {
             setMessages(prev => prev.map(m => 
               m.isThinking ? { ...m, thinkingText: lastThought.replace(/🧠|🤔/, '').trim() } : m
             ))
          }
        }

        // AUTO-REFRESH UI when a background sync finishes
        if (data.status === 'completed') {
            const { data: freshProject } = await supabase.from('projects').select('*').eq('id', projectData.id).maybeSingle();
            if (freshProject) setProjectData(freshProject);

            fetchRisks(projectData.id);
            clearInterval(interval); 
        }

      } catch (e) { console.error("Poll error", e) }
    }, 1500)

    return () => clearInterval(interval)
  }, [chatLoading, projectData])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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
    
    setMessages(prev => [...prev, { role: 'lumis', content: '...', isThinking: true }])
    
    try {
      const res = await fetch('http://localhost:5000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            project_id: projectData.id, 
            query: userMsg.content,
            mode: chatMode,
            reasoning: reasoning 
        })
      })
      const data = await res.json()
      
      setMessages(prev => {
        const filtered = prev.filter(m => !m.isThinking)
        return [...filtered, { role: 'lumis', content: data.response }]
      })
    } catch (err) {
      setMessages(prev => [...prev.filter(m => !m.isThinking), { role: 'lumis', content: "Error: Could not reach Lumis Core." }])
    } finally {
      setChatLoading(false)
    }
  }

  const handleCopyWebhook = () => {
    const webhookUrl = `https://unsparing-kaley-unmodest.ngrok-free.dev/api/webhook/${session?.user?.id}/${projectData?.id}`;
    navigator.clipboard.writeText(webhookUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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
          <div className="info-card" style={{ padding: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.95rem', color: '#09090b' }}>
                        {projectData?.repo_url?.split('/').pop()}
                    </div>
                    <a href={projectData?.repo_url} target="_blank" rel="noreferrer" style={{ fontSize: '0.75rem', color: '#71717a', textDecoration: 'none', display:'block', marginTop:'2px' }}>
                      View on GitHub ↗
                    </a>
                  </div>
                  <button onClick={handleIngest} title="Force Re-sync" className="btn-text" style={{ fontSize:'1.1rem', padding:'4px', marginTop:'-4px' }}>🔄</button>
              </div>

              <div style={{ borderTop: '1px solid #e4e4e7', paddingTop: '10px', marginTop: '10px' }}>
                <div style={{ fontSize: '0.7rem', color: '#71717a', marginBottom: '4px', fontWeight: 600, letterSpacing: '0.02em' }}>
                    LAST COMMIT
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
            {risks.length === 0 ? (
              <div className="info-card" style={{color:'#71717a'}}>No active risks detected.</div>
            ) : (
              risks.map((r, i) => (
                <div key={i} className="risk-card">
                    <div className="risk-header">
                      <span className="risk-type">{r.risk_type}</span>
                      <span className={`risk-badge ${r.severity?.toLowerCase() || 'medium'}`}>
                        {r.severity}
                      </span>
                    </div>
                    <div className="risk-desc">
                      <ReactMarkdown>{r.description}</ReactMarkdown>
                    </div>
                </div>
              ))
            )}
          </div>

          <div className="section-title">Webhook Integration</div>
          <div className="info-card" style={{ padding: '16px' }}>
            <div style={{ fontSize: '0.75rem', color: '#71717a', lineHeight: '1.5', marginBottom: '12px' }}>
              Sync automatically on every push:
              <ol style={{ paddingLeft: '1.2rem', margin: '8px 0' }}>
                <li>GitHub <strong>Settings</strong> → <strong>Webhooks</strong></li>
                <li>Add URL below as <strong>Payload URL</strong></li>
                <li>Type: <code>application/json</code></li>
              </ol>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input 
                className="input-field" 
                readOnly 
                value={`https://unsparing-kaley-unmodest.ngrok-free.dev/api/webhook/${session?.user?.id}/${projectData?.id}`} 
                style={{ fontSize: '0.7rem', padding: '6px 8px', background: '#f9fafb' }}
              />
              <button onClick={handleCopyWebhook} className="btn btn-outline" style={{ padding: '6px 10px', fontSize: '0.75rem' }}>
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
          
        </div>
        <div className="sidebar-footer">
           <button className="btn-text" onClick={() => supabase.auth.signOut().then(() => navigate('/'))}>Logout</button>
        </div>
      </aside>

      <main className="main-stage">
        <div className="stage-header">
            <span>Digital Twin Terminal</span>
            <div style={{display:'flex', gap:'8px', alignItems:'center'}}>
                <button 
                    onClick={() => setReasoning(!reasoning)}
                    style={{
                        background: reasoning ? '#8b5cf6' : '#f4f4f5',
                        color: reasoning ? 'white' : '#71717a',
                        border: 'none', padding: '4px 12px', borderRadius: '4px', fontSize:'0.8rem', cursor:'pointer',
                        fontWeight: 600, transition: 'all 0.2s', marginRight: '8px'
                    }}
                    title="Enable Chain-of-Thought (Slower but smarter)"
                >
                    {reasoning ? '✨ Reasoning ON' : 'Reasoning OFF'}
                </button>

                <div style={{display:'flex', gap:'4px', background:'#f4f4f5', padding:'4px', borderRadius:'6px'}}>
                    <button onClick={() => setChatMode('multi-turn')} style={{ background: chatMode === 'multi-turn' ? 'white' : 'transparent', border: 'none', padding: '4px 12px', borderRadius: '4px', fontSize:'0.8rem', cursor:'pointer', boxShadow: chatMode === 'multi-turn' ? '0 1px 2px rgba(0,0,0,0.1)' : 'none', fontWeight: chatMode === 'multi-turn' ? 600 : 400 }}>Multi-Turn</button>
                    <button onClick={() => setChatMode('single-turn')} style={{ background: chatMode === 'single-turn' ? 'white' : 'transparent', border: 'none', padding: '4px 12px', borderRadius: '4px', fontSize:'0.8rem', cursor:'pointer', boxShadow: chatMode === 'single-turn' ? '0 1px 2px rgba(0,0,0,0.1)' : 'none', fontWeight: chatMode === 'single-turn' ? 600 : 400 }}>Single-Turn</button>
                </div>
            </div>
        </div>
        
        <div className="chat-scroll-area">
          <div className="message-wrapper">
            {messages.map((m, i) => (
              <div key={i} className={`message-row ${m.role}`}>
                <div className={`message-bubble ${m.isThinking ? 'thinking' : ''}`}>
                  {m.isThinking ? (
                    <div className="dots-container" style={{display:'flex', flexDirection:'column', alignItems:'flex-start'}}>
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
                <input className="chat-input" placeholder="Ask Lumis about architecture, bugs, or risks..." value={input} onChange={e => setInput(e.target.value)} />
                <button type="submit" className="send-button">Send</button>
            </form>
        </div>
      </main>
    </div>
  )
}