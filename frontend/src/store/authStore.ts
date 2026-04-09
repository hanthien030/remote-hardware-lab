import { create } from 'zustand';

interface User {
  id: string;
  username: string;
  email: string;
  role: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  sessionKey: string | null;
  login: (token: string, user: User) => void;
  logout: () => void;
  setUser: (user: User) => void;
  syncFromStorage: () => void;
}

const AUTH_CHANNEL_NAME = 'remote-lab-auth';
const AUTH_SYNC_STORAGE_KEY = 'rhl_auth_sync';

type StoredAuthSnapshot = {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  sessionKey: string | null;
};

const readStoredAuth = (): StoredAuthSnapshot => {
  let user: User | null = null;
  let token: string | null = null;

  try {
    const storedUser = localStorage.getItem('user');
    if (storedUser && storedUser !== 'undefined' && storedUser !== 'null') {
      user = JSON.parse(storedUser);
    }

    const storedToken = localStorage.getItem('token');
    if (storedToken && storedToken !== 'undefined' && storedToken !== 'null') {
      token = storedToken;
    }
  } catch (error) {
    console.error('Failed to parse auth storage:', error);
    localStorage.removeItem('user');
    localStorage.removeItem('token');
  }

  const isAuthenticated = !!token && !!user;
  return {
    user,
    token,
    isAuthenticated,
    sessionKey: isAuthenticated ? `${user!.id}:${user!.username}:${token}` : null,
  };
};

const broadcastAuthChange = (type: 'login' | 'logout' | 'sync', payload: StoredAuthSnapshot) => {
  try {
    localStorage.setItem(
      AUTH_SYNC_STORAGE_KEY,
      JSON.stringify({
        type,
        sessionKey: payload.sessionKey,
        at: Date.now(),
      })
    );
  } catch {
    // Ignore localStorage sync write failures.
  }

  if (typeof window !== 'undefined' && 'BroadcastChannel' in window) {
    const channel = new BroadcastChannel(AUTH_CHANNEL_NAME);
    channel.postMessage({ type, sessionKey: payload.sessionKey });
    channel.close();
  }
};

export const useAuthStore = create<AuthState>((set) => {
  const initialState = readStoredAuth();

  return {
    ...initialState,

    login: (token: string, user: User) => {
      localStorage.setItem('token', token);
      localStorage.setItem('user', JSON.stringify(user));
      const nextState: StoredAuthSnapshot = {
        user,
        token,
        isAuthenticated: true,
        sessionKey: `${user.id}:${user.username}:${token}`,
      };
      set(nextState);
      broadcastAuthChange('login', nextState);
    },

    logout: () => {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      const nextState: StoredAuthSnapshot = {
        user: null,
        token: null,
        isAuthenticated: false,
        sessionKey: null,
      };
      set(nextState);
      broadcastAuthChange('logout', nextState);
    },

    setUser: (user: User) => {
      localStorage.setItem('user', JSON.stringify(user));
      set((state) => ({
        user,
        isAuthenticated: !!state.token,
        sessionKey: state.token ? `${user.id}:${user.username}:${state.token}` : null,
      }));
      broadcastAuthChange('sync', readStoredAuth());
    },

    syncFromStorage: () => {
      set(readStoredAuth());
    },
  };
});

export const authSyncConstants = {
  AUTH_CHANNEL_NAME,
  AUTH_SYNC_STORAGE_KEY,
};
