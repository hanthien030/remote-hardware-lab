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

    if (loopbackHosts.has(configuredHost) && !loopbackHosts.has(currentHost)) {
      return '';
    }

    return configuredBaseUrl;
  } catch {
    return configuredBaseUrl;
  }
};

export const API_BASE_URL = resolveApiBaseUrl();

export const DEVICE_STATUS = {
  ACTIVE: 'active',
  INACTIVE: 'inactive',
  MAINTENANCE: 'maintenance',
};

export const USER_ROLES = {
  ADMIN: 'admin',
  USER: 'user',
};
