import { useEffect, useState, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'

export default function Syncing() {
  const [searchParams] = useSearchParams()
  const projectId = searchParams.get('project_id')
  const navigate = useNavigate()
  const [status, setStatus] = useState({ logs: [], status: 'processing' })
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!projectId) return
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:5000/api/ingest/status/${projectId}`)
        const data = await res.json()
        setStatus(data)
        
        // REDIRECT LOGIC: Check both status AND logs for "DONE" signal
        if (data.status === 'completed' || data.logs.some(l => l.includes('DONE'))) {
          clearInterval(interval)
          setTimeout(() => navigate('/dashboard'), 2000)
        }
      } catch (e) { console.error(e) }
    }, 1500)
    return () => clearInterval(interval)
  }, [projectId, navigate])

  return (
    <div style={{ height: '100vh', background: '#09090b', color: '#fff', display: 'flex', flexDirection: 'column', fontFamily: 'monospace' }}>
      <div style={{ padding: '20px', borderBottom: '1px solid #27272a', display: 'flex', justifyContent: 'space-between' }}>
        <span>Lumis Engine Output</span>
        <button onClick={() => navigate('/dashboard')} style={{background:'#27272a', color:'#fff', border:'none', cursor:'pointer'}}>Exit to Dashboard</button>
      </div>
      <div style={{ flex: 1, padding: '40px', overflowY: 'auto' }}>
        {status.logs.map((log, i) => <div key={i} style={{marginBottom:'8px'}}>{log}</div>)}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}