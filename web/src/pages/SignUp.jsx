import { useState } from 'react'
import { supabase } from '../supabase'
import { useNavigate, Link } from 'react-router-dom'

export default function SignUp() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSignUp = async (e) => {
    e.preventDefault()
    setLoading(true)
    const { error } = await supabase.auth.signUp({ email, password })
    if (error) alert(error.message)
    else {
      alert("Account created! You can now log in.")
      navigate('/auth')
    }
    setLoading(false)
  }

  return (
    <div className="page-center">
      <div className="auth-card">
        <div className="auth-header">
          <h1>Create an account</h1>
          <p>Start building your project memory layer today.</p>
        </div>
        
        <form onSubmit={handleSignUp} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <input 
            className="input-field"
            type="email" 
            placeholder="name@company.com" 
            value={email} 
            onChange={e => setEmail(e.target.value)} 
          />
          <input 
            className="input-field"
            type="password" 
            placeholder="Create a password" 
            value={password} 
            onChange={e => setPassword(e.target.value)} 
          />
          <button className="btn btn-primary" style={{ width: '100%', padding: '12px' }} disabled={loading}>
            {loading ? 'Creating...' : 'Sign Up'}
          </button>
        </form>

        <div style={{ marginTop: '1.5rem', fontSize: '0.9rem', color: '#71717a' }}>
          Already have an account? <Link to="/auth" style={{ color: '#09090b', fontWeight: 600, textDecoration: 'none' }}>Log in</Link>
        </div>
      </div>
    </div>
  )
}