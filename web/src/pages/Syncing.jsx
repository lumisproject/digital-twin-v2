import { useEffect, useState, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'

export default function Syncing() {
  const [searchParams] = useSearchParams()
  const projectId = searchParams.get('project_id')
  const navigate = useNavigate()
  
  const [status, setStatus] = useState({ step: 'Initializing', logs: [], status: 'processing' })
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!projectId) return

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:5000/api/ingest/status/${projectId}`)
        const data = await res.json()
        
        setStatus(data)
        
        // When complete, go back to Dashboard
        if (data.status === 'completed') {
          clearInterval(interval)
          setTimeout(() => navigate('/dashboard'), 1500)
        }
      } catch (e) {
        console.error("Polling error", e)
      }
    }, 1000)

    return () => clearInterval(interval)
  }, [projectId, navigate])

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [status.logs])

  return (
    <div style={{ 
      height: '100vh', 
      background: '#09090b', 
      color: '#fff', 
      display: 'flex', 
      flexDirection: 'column', 
      fontFamily: 'monospace' 
    }}>
      {/* Header */}
      <div style={{ 
        padding: '20px', 
        borderBottom: '1px solid #27272a', 
        display: 'flex', 
        alignItems: 'center', 
        gap: '12px' 
      }}>
        <div className={`status-dot ${status.status}`}></div>
        <span style={{ fontSize: '1.1rem', fontWeight: 600 }}>
          Lumis Engine — {status.step}
        </span>
      </div>

      {/* Terminal Output */}
      <div style={{ flex: 1, padding: '40px', overflowY: 'auto' }}>
        <div style={{ maxWidth: '800px', margin: '0 auto' }}>
          {status.logs.map((log, i) => (
            <div key={i} style={{ marginBottom: '8px', opacity: 0.9, lineHeight: '1.6' }}>
              <span style={{ color: '#10b981', marginRight: '10px' }}>➜</span>
              {log}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      <style>{`
        .status-dot { width: 12px; height: 12px; border-radius: 50%; background: #fbbf24; box-shadow: 0 0 10px #fbbf24; }
        .status-dot.completed { background: #10b981; box-shadow: 0 0 10px #10b981; }
        .status-dot.failed { background: #ef4444; box-shadow: 0 0 10px #ef4444; }
      `}</style>
    </div>
  )
}