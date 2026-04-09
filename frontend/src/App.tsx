import type React from 'react';
import { useEffect } from 'react';
import { createBrowserRouter, createRoutesFromElements, RouterProvider, Route, Navigate } from 'react-router-dom';
import { Login } from './pages/Login';
import { Register } from './pages/Register';
import { Dashboard } from './pages/Dashboard';
import { AdminPanel } from './pages/AdminPanel';
import { ProtectedRoute } from './components/ProtectedRoute';
import { SidebarLayout } from './components/SidebarLayout';
import { WorkspaceIndex } from './pages/WorkspaceIndex';
import { ProjectWorkspace } from './pages/ProjectWorkspace';
import { HistoryIndex } from './pages/HistoryIndex';
import { ProfileIndex } from './pages/ProfileIndex';
import { authSyncConstants, useAuthStore } from './store/authStore';
import './App.css';

const authDestination = (role?: string | null) => (role === 'admin' ? '/admin' : '/workspace');

const AuthAwareRedirect = () => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const userRole = useAuthStore((state) => state.user?.role);

  return <Navigate to={isAuthenticated ? authDestination(userRole) : '/login'} replace />;
};

const PublicOnlyRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const userRole = useAuthStore((state) => state.user?.role);

  if (isAuthenticated) {
    return <Navigate to={authDestination(userRole)} replace />;
  }

  return <>{children}</>;
};

const SessionScopedSidebarLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const sessionKey = useAuthStore((state) => state.sessionKey);

  return <SidebarLayout key={sessionKey || 'guest-session'}>{children}</SidebarLayout>;
};

const router = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route path="/login" element={<PublicOnlyRoute><Login /></PublicOnlyRoute>} />
      <Route path="/register" element={<PublicOnlyRoute><Register /></PublicOnlyRoute>} />
      
      {/* User authenticated routes */}
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <SessionScopedSidebarLayout><Dashboard /></SessionScopedSidebarLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/workspace"
        element={
           <ProtectedRoute>
            <SessionScopedSidebarLayout><WorkspaceIndex /></SessionScopedSidebarLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/workspace/:projectName"
        element={
           <ProtectedRoute>
            <SessionScopedSidebarLayout><ProjectWorkspace /></SessionScopedSidebarLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/history"
        element={
           <ProtectedRoute>
            <SessionScopedSidebarLayout><HistoryIndex /></SessionScopedSidebarLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/profile"
        element={
           <ProtectedRoute>
            <SessionScopedSidebarLayout><ProfileIndex /></SessionScopedSidebarLayout>
          </ProtectedRoute>
        }
      />
      
      {/* Admin authenticated routes */}
      <Route
        path="/admin"
        element={
          <ProtectedRoute adminOnly>
            <SessionScopedSidebarLayout><AdminPanel /></SessionScopedSidebarLayout>
          </ProtectedRoute>
        }
      />
      
      <Route path="/" element={<AuthAwareRedirect />} />
    </>
  )
);

function App() {
  useEffect(() => {
    const syncFromStorage = () => {
      useAuthStore.getState().syncFromStorage();
    };

    const handleStorage = (event: StorageEvent) => {
      if (!event.key) return;
      if (event.key === 'token' || event.key === 'user' || event.key === authSyncConstants.AUTH_SYNC_STORAGE_KEY) {
        syncFromStorage();
      }
    };

    window.addEventListener('storage', handleStorage);

    const channel = typeof window !== 'undefined' && 'BroadcastChannel' in window
      ? new BroadcastChannel(authSyncConstants.AUTH_CHANNEL_NAME)
      : null;

    const handleBroadcast = () => syncFromStorage();
    channel?.addEventListener('message', handleBroadcast);

    const unsubscribe = useAuthStore.subscribe((state, previousState) => {
      const currentPath = router.state.location.pathname;
      const previousSessionKey = previousState.sessionKey;
      const nextSessionKey = state.sessionKey;

      if (previousSessionKey === nextSessionKey) return;

      if (!state.isAuthenticated || !state.user) {
        if (currentPath !== '/login') {
          router.navigate('/login', { replace: true });
        }
        return;
      }

      const isGuestPath = currentPath === '/' || currentPath === '/login' || currentPath === '/register';
      const sessionChangedAcrossAccounts = previousSessionKey !== null && previousSessionKey !== nextSessionKey;

      if (isGuestPath || sessionChangedAcrossAccounts) {
        router.navigate(authDestination(state.user.role), { replace: true });
      }
    });

    return () => {
      unsubscribe();
      window.removeEventListener('storage', handleStorage);
      channel?.removeEventListener('message', handleBroadcast);
      channel?.close();
    };
  }, []);

  return <RouterProvider router={router} />;
}

export default App;
