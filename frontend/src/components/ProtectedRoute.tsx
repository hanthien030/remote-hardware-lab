import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

interface ProtectedRouteProps {
  children: React.ReactNode;
  adminOnly?: boolean;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  adminOnly = false,
}) => {
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  // Not authenticated - redirect to login
  if (!isAuthenticated || !user) {
    console.log('Not authenticated, redirecting to login');
    return <Navigate to="/login" />;
  }

  // Admin only check
  if (adminOnly) {
    console.log('Admin only route. User role:', user?.role);
    if (user?.role !== 'admin') {
      console.log('User is not admin, redirecting to dashboard');
      return <Navigate to="/dashboard" />;
    }
  }

  return <>{children}</>;
};
