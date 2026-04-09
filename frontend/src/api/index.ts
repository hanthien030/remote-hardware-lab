import client from './client';

// Auth API
export const authAPI = {
  register: (userData: { username: string; password: string; email: string }) =>
    client.post('/api/auth/register', userData),
  
  login: (credentials: { username: string; password: string }) =>
    client.post('/api/auth/login', credentials),
  
  logout: () => client.post('/api/auth/logout'),
  
  getCurrentUser: () => client.get('/api/auth/profile'),
};

// User Hardware API
export const userHardwareAPI = {
  listDevices: (filters?: { page?: number; limit?: number }) =>
    client.get('/api/hardware/my-devices', { params: filters }),

  createDevice: (data: any) => client.post('/api/hardware/my-devices/tag_name', data),

  deleteDevice: (deviceId: string) =>
    client.delete(`/api/hardware/my-devices/tag_name`, { data: { device_id: deviceId } }),
};

// Admin Hardware API
export const adminHardwareAPI = {
  listAllDevices: (filters?: { page?: number; limit?: number }) =>
    client.get('/api/admin/devices', { params: filters }),

  updateDevice: (tagName: string, data: { tag_name: string; device_name?: string | null; usage_mode?: 'free' | 'share' | 'block' }) =>
    client.put(`/api/admin/devices/${encodeURIComponent(tagName)}`, data),

  assignDevice: (deviceId: string, userId: string, expires_at?: string) =>
    client.post(`/api/admin/assignments`, { 
      user_id: userId,
      tag_name: deviceId,
      expires_at: expires_at || new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] + ' 23:59:59'
    }),

  revokeAssignment: (tagName: string, userId?: string) =>
    client.delete(`/api/admin/assignments/${encodeURIComponent(tagName)}`, {
      data: userId ? { user_id: userId } : {},
    }),
};

// Admin User API
export const adminUserAPI = {
  listAllUsers: (filters?: { page?: number; limit?: number }) =>
    client.get('/api/admin/users', { params: filters }),

  deleteUser: (userId: string) => 
    client.delete(`/api/admin/users/${userId}`),
};
