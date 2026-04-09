import React, { useState } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import './Sidebar.css';

export const Sidebar: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const navigate = useNavigate();
  const location = useLocation();

  // Tự động thu gọn Sidebar khi vào màn hình Làm việc (workspace/device)
  // và nếu đang ở device thì thu gọn mặc định.
  // Tuy nhiên, ta chỉ dùng state hiện tại cho collapsed, 
  // ta chỉ force thu gọn nếu người dùng bấm icon.
  // Theo spec "Sidebar thu lại khi vào giao diện Làm việc"
  const isWorkspace = location.pathname.startsWith('/device') || location.pathname.startsWith('/workspace');
  
  // Actually, we can just use `collapsed` state, but let's default to collapsed if in workspace.
  // Wait, React warning: don't update state during render. We'll handle it nicely.
  React.useEffect(() => {
    if (isWorkspace) {
      setCollapsed(true);
    } else {
      setCollapsed(false);
    }
  }, [isWorkspace]);


  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  if (!user) return null;

  const isAdmin = user.role === 'admin';

  return (
    <div className={`sidebar-container ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <button className="toggle-btn" onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? '≡' : '≡ Logo'}
        </button>
      </div>

      <div className="sidebar-nav">
        {!isAdmin ? (
          <>
            <NavLink to="/workspace" className={({ isActive }) => `nav-item ${isActive || isWorkspace ? 'active' : ''}`}>
              <span className="icon">💻</span>
              <span className="label">Làm việc</span>
            </NavLink>
            <NavLink to="/dashboard" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <span className="icon">📋</span>
              <span className="label">Thiết bị</span>
            </NavLink>
            <NavLink to="/history" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <span className="icon">📜</span>
              <span className="label">Lịch sử</span>
            </NavLink>
            <div className="divider"></div>
            <NavLink to="/profile" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <span className="icon">👤</span>
              <span className="label">Cá nhân</span>
            </NavLink>
          </>
        ) : (
          <>
            <NavLink to="/admin" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <span className="icon">🔧</span>
              <span className="label">Quản lý chung</span>
            </NavLink>
          </>
        )}
      </div>

      <div className="sidebar-footer">
        <button className="nav-item logout-item" onClick={handleLogout}>
          <span className="icon">🚪</span>
          <span className="label">Đăng xuất</span>
        </button>
      </div>
    </div>
  );
};
