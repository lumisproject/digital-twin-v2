import { Link } from 'react-router-dom'

export default function Landing() {
  return (
    <div style={{ background: '#ffffff', minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      
      {/* Navbar */}
      <nav className="nav-public">
        <div className="brand" style={{ fontSize: '1.2rem' }}>
          <div style={{ width: 16, height: 16, background: '#000', borderRadius: '50%' }}></div>
          Lumis
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          {/* Changed /auth to /login to match App.tsx */}
          <Link to="/login" className="btn btn-outline" style={{ border: 'none' }}>Login</Link>
          <Link to="/signup" className="btn btn-primary">Sign Up</Link>
        </div>
      </nav>

      {/* Hero Section */}
      <main style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="landing-hero">
          <h1>The Memory Layer for <br/> your Software.</h1>
          <p>
            Lumis is an autonomous intelligence layer that connects your code, tasks, and communications into a single "Project Brain."
          </p>
          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', marginTop: '1rem' }}>
            <Link to="/signup" className="btn btn-primary" style={{ padding: '14px 32px', fontSize: '1rem' }}>
              Start for free
            </Link>
            <a href="https://github.com" target="_blank" className="btn btn-outline" style={{ padding: '14px 32px', fontSize: '1rem' }}>
              View Documentation
            </a>
          </div>
        </div>
      </main>

      <footer style={{ padding: '2rem', textAlign: 'center', borderTop: '1px solid #f4f4f5', color: '#71717a', fontSize: '0.85rem' }}>
        © {new Date().getFullYear()} Novagate Solutions ApS. All rights reserved.
      </footer>
    </div>
  )
}