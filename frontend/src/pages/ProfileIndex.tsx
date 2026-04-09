import React from 'react';
import { useAuthStore } from '../store/authStore';

export const ProfileIndex: React.FC = () => {
  const user = useAuthStore(state => state.user);

  return (
    <div style={{ padding: 20, color: '#cdd6f4' }}>
      <h1>👤 Cá nhân</h1>
      <p>Thông tin tài khoản: {user?.username}</p>
      <p>Vai trò: {user?.role}</p>
    </div>
  );
};
