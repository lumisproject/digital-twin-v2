import { useEffect, useState, useRef } from 'react'

export default function IngestionWizard({ projectId, onComplete }) {
  const [status, setStatus] = useState({ step: 'Initializing', logs: [], status: 'processing' })
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!projectId) return

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:5000/api/ingest/status/${projectId}`)
        const data = await res.json()
        
        setStatus(data)
        
        if (data.status === 'completed') {
          clearInterval(interval)
          setTimeout(() => onComplete(), 1000) // Give user a moment to see "Done"
        }
        if (data.status === 'failed') {
          clearInterval(interval)
        }
      } catch (e) {
        console.error("Polling error", e)
      }
    }, 1000)

    return () => clearInterval(interval)
  }, [projectId])

  // Auto-scroll logs
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [status.logs])

  return (
    <div className="ingestion-overlay">
      <div className="terminal-window">
        <div className="terminal-header">
          <div className="dot red"></div>
          <div className="dot yellow"></div>
          <div className="dot green"></div>
          <span>Lumis Engine — {status.step}</span>
        </div>
        
        <div className="terminal-body">
          {status.logs.map((log, i) => (
            <div key={i} className="log-line">
              <span className="prompt">{'>'}</span> {log}
            </div>
          ))}
          
          {status.status === 'failed' && (
            <div className="log-line error">
              <span className="prompt">!</span> ERROR: {status.error}
            </div>
          )}
          
          {status.status === 'processing' && (
            <div className="log-line animate-pulse">_</div>
          )}
          
          <div ref={bottomRef} />
        </div>
      </div>

      <style>{`
        .ingestion-overlay {
          position: fixed; top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(255, 255, 255, 0.9);
          backdrop-filter: blur(5px);
          display: flex; align-items: center; justify-content: center;
          z-index: 1000;
        }
        .terminal-window {
          width: 600px; height: 400px;
          background: #1e1e1e; border-radius: 8px;
          box-shadow: 0 20px 50px rgba(0,0,0,0.3);
          display: flex; flex-direction: column;
          overflow: hidden;
          font-family: 'Courier New', monospace;
        }
        .terminal-header {
          background: #2d2d2d; padding: 10px 15px;
          display: flex; align-items: center; gap: 8px;
          color: #aaa; font-size: 0.8rem;
        }
        .dot { width: 10px; height: 10px; border-radius: 50%; }
        .red { background: #ff5f56; }
        .yellow { background: #ffbd2e; }
        .green { background: #27c93f; }
        
        .terminal-body {
          padding: 20px; color: #fff; flex: 1; overflow-y: auto;
          font-size: 0.9rem; line-height: 1.5;
        }
        .log-line { margin-bottom: 4px; }
        .prompt { color: #27c93f; margin-right: 8px; }
        .error { color: #ff5f56; font-weight: bold; }
        .animate-pulse { animation: pulse 1s infinite; }
        @keyframes pulse { 0% { opacity: 0; } 50% { opacity: 1; } 100% { opacity: 0; } }
      `}</style>
    </div>
  )
}