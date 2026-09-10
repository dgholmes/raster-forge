import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { LayoutDashboard, Layers, ListChecks, ShieldCheck } from 'lucide-react';

import './index.css';
import './App.css';

import { useTheme } from './hooks/useTheme';
import { useBackendStatus } from './hooks/useBackendStatus';
import { AuthProvider, useAuth } from './components/auth/AuthContext';
import ProtectedRoute from './components/auth/ProtectedRoute';
import { Topbar } from './components/Topbar';

import DashboardPage from './pages/DashboardPage';
import DatasetsPage from './pages/DatasetsPage';
import DatasetDetailPage from './pages/DatasetDetailPage';
import JobsPage from './pages/JobsPage';
import AdminPage from './pages/AdminPage';
import LoginPage from './pages/LoginPage';

import type { NavItem } from './types';

/* ============================================================================
 * main.tsx — entry, routing, shared layout.
 *
 *   /              Dashboard  (stats, upload, recent datasets)
 *   /datasets      Datasets   (table)
 *   /datasets/:id  Detail     (analysis | configure | processing | published)
 *   /jobs          Jobs
 *   /admin         Admin      (admin role only)
 *   /login         Login
 *
 * The topbar is sticky rather than an overlay: RasterForge's screens are
 * scrolling documents, and glass chrome needs full-bleed content underneath
 * it to blur. The one genuinely map-like surface — the tile preview — is a
 * bounded card that carries its own glass controls.
 * ========================================================================== */

const BASE_NAV: NavItem[] = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard },
  { label: 'Datasets', path: '/datasets', icon: Layers },
  { label: 'Jobs', path: '/jobs', icon: ListChecks },
];

const ADMIN_NAV: NavItem = { label: 'Admin', path: '/admin', icon: ShieldCheck };

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { theme, toggle, C } = useTheme();
  const backendStatus = useBackendStatus();
  const { user } = useAuth();

  const nav = user?.role === 'admin' ? [...BASE_NAV, ADMIN_NAV] : BASE_NAV;

  return (
    <div className="md-shell" style={{ background: C.appBg }}>
      <Topbar
        C={C}
        theme={theme}
        onToggleTheme={toggle}
        nav={nav}
        backendStatus={backendStatus}
        overlay={false}
      />
      <div className="md-content">{children}</div>
    </div>
  );
};

const Guarded: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ProtectedRoute>
    <Layout>{children}</Layout>
  </ProtectedRoute>
);

const App: React.FC = () => (
  <BrowserRouter>
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Guarded><DashboardPage /></Guarded>} />
        <Route path="/datasets" element={<Guarded><DatasetsPage /></Guarded>} />
        <Route path="/datasets/:id" element={<Guarded><DatasetDetailPage /></Guarded>} />
        <Route path="/jobs" element={<Guarded><JobsPage /></Guarded>} />
        <Route path="/admin" element={<Guarded><AdminPage /></Guarded>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  </BrowserRouter>
);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
