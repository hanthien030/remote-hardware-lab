import type { AxiosInstance } from 'axios';
import axios from 'axios';
import { useAuthStore } from '../store/authStore';

const resolveApiBaseUrl = () => {
  const configuredBaseUrl = import.meta.env.VITE_API_URL?.trim();

  if (!configuredBaseUrl) {
    return '';
  }

  try {
    const parsedUrl = new URL(configuredBaseUrl, window.location.origin);
    const configuredHost = parsedUrl.hostname;
    const currentHost = window.location.hostname;
    const loopbackHosts = new Set(['localhost', '127.0.0.1', '0.0.0.0']);

    // If the app is opened from another machine but the build still points at
    // localhost, fall back to same-origin so /api continues to work via nginx.
    if (loopbackHosts.has(configuredHost) && !loopbackHosts.has(currentHost)) {
      return '';
    }

    return configuredBaseUrl;
  } catch {
    return configuredBaseUrl;
  }
};

const API_BASE_URL = resolveApiBaseUrl();

const client: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle errors
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default client;
