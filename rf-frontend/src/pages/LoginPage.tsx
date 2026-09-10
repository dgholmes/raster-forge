import React, { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Layers, LogIn } from 'lucide-react';
import { APP } from '../config/config';
import { STATUS } from '../design-system/tokens';
import { useAuth } from '../components/auth/AuthContext';
import { useTheme } from '../hooks/useTheme';
import { Button, Field, FONT, TextInput } from '../components/rf/ui';

const LoginPage: React.FC = () => {
  const { C } = useTheme();
  const { login, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? '/';

  if (!isLoading && isAuthenticated) return <Navigate to={from} replace />;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100%',
        display: 'grid',
        placeItems: 'center',
        background: C.appBg,
        fontFamily: FONT,
        padding: 20,
      }}
    >
      <div
        className="rf-detail-in"
        style={{
          width: '100%',
          maxWidth: 380,
          background: C.win,
          border: `1px solid ${C.b}`,
          borderRadius: 12,
          padding: 32,
          boxShadow: C.dark
            ? '0 32px 80px rgba(0,0,0,0.60), 0 0 0 1px rgba(255,255,255,0.06)'
            : '0 20px 50px rgba(0,0,0,0.14), 0 0 0 1px rgba(0,0,0,0.07)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <Layers size={22} color={C.accent} strokeWidth={2} />
          <h1
            style={{
              margin: 0,
              fontSize: 20,
              fontWeight: 700,
              letterSpacing: '-0.02em',
              color: C.t1,
            }}
          >
            {APP.name}
          </h1>
        </div>
        <p style={{ fontSize: 13, color: C.t3, marginBottom: 24 }}>
          From GeoTIFF to deployable web maps.
        </p>

        <form onSubmit={submit}>
          <Field C={C} label="Username" htmlFor="rf-username">
            <TextInput
              id="rf-username"
              C={C}
              value={username}
              onChange={setUsername}
              placeholder="admin"
              disabled={busy}
            />
          </Field>

          <Field C={C} label="Password" htmlFor="rf-password">
            <TextInput
              id="rf-password"
              C={C}
              type="password"
              value={password}
              onChange={setPassword}
              placeholder="••••••••"
              disabled={busy}
            />
          </Field>

          {error && (
            <div
              style={{
                background: STATUS.redBg,
                border: `1px solid ${STATUS.red}`,
                borderRadius: 8,
                padding: 12,
                fontSize: 12,
                color: STATUS.red,
                marginBottom: 16,
              }}
            >
              {error}
            </div>
          )}

          <Button C={C} variant="primary" icon={LogIn} type="submit" disabled={busy} full>
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
