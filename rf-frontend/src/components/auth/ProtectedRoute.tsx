import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext';

/* ============================================================================
 * ProtectedRoute — gate a route behind authentication.
 *
 * • If VITE_AUTH_ENABLED is false, this is a pure pass-through.
 * • Otherwise, unauthenticated users are redirected to /login (with the
 *   attempted path saved so they return there after logging in).
 * • While the initial auth check is in flight, renders nothing (avoids a
 *   flash-redirect on hard reload with a valid token).
 * ========================================================================== */

interface Props {
  children: React.ReactNode;
  /** Restrict to specific roles; others are redirected to '/'. */
  allowedRoles?: string[];
}

const ProtectedRoute: React.FC<Props> = ({ children, allowedRoles }) => {
  const { authEnabled, isAuthenticated, isLoading, user } = useAuth();
  const location = useLocation();

  if (!authEnabled) return <>{children}</>;
  if (isLoading) return null;

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles && user && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
