import { useState } from 'react';

const CREDENTIALS = { username: 'upwork', password: 'UpWork123' };

export function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (username === CREDENTIALS.username && password === CREDENTIALS.password) {
      onLogin();
    } else {
      setError('Invalid username or password');
    }
  };

  return (
    <div className="login-overlay">
      <div className="login-card">
        <div className="login-brand">
          <div className="logo-mark" aria-hidden="true">◈</div>
          <h1>Crypto Research Agent</h1>
          <p>AI-powered market analysis · LangGraph + LangChain</p>
        </div>
        <form className="login-form" onSubmit={handleSubmit} noValidate autoComplete="off">
          <div className="login-field">
            <label htmlFor="login-username">Username</label>
            <input
              id="login-username"
              type="text"
              autoComplete="off"
              value={username}
              onChange={(e) => { setUsername(e.target.value); setError(''); }}
              placeholder=""
            />
          </div>
          <div className="login-field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setError(''); }}
              placeholder=""
            />
          </div>
          {error && <p className="login-error">{error}</p>}
          <button type="submit" className="btn-analyze login-submit">Sign in</button>
        </form>
      </div>
    </div>
  );
}
