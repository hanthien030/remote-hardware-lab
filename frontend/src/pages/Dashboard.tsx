import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { userHardwareAPI } from '../api';
import { useAuthStore } from '../store/authStore';
import { useDeviceSocket } from '../hooks/useDeviceSocket';
import '../styles/Dashboard.css';

interface Device {
  id: string;
  tag_name: string;
  device_name: string;
  status: string;
  created_at: string;
}

export const Dashboard: React.FC = () => {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({ tag_name: '', device_name: '' });
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const { onDeviceConnected, onDeviceDisconnected, onDeviceLocked, onDeviceUnlocked } = useDeviceSocket();

  useEffect(() => {
    fetchDevices();
  }, []);

  // WebSocket: auto-update device status without F5
  useEffect(() => {
    const unsubConnect = onDeviceConnected((ev) => {
      setDevices(prev =>
        prev.map(d => d.tag_name === ev.tag_name ? { ...d, status: 'connected' } : d)
      );
    });
    const unsubDisconnect = onDeviceDisconnected((ev) => {
      setDevices(prev =>
        prev.map(d => d.tag_name === ev.tag_name ? { ...d, status: 'disconnected' } : d)
      );
    });
    const unsubLocked = onDeviceLocked((ev) => {
      setDevices(prev =>
        prev.map(d => d.tag_name === ev.tag_name ? { ...d, locked_by_user: ev.locked_by } : d)
      );
    });
    const unsubUnlocked = onDeviceUnlocked((ev) => {
      setDevices(prev =>
        prev.map(d => d.tag_name === ev.tag_name ? { ...d, locked_by_user: undefined } : d)
      );
    });
    return () => {
      unsubConnect();
      unsubDisconnect();
      unsubLocked();
      unsubUnlocked();
    };
  }, [onDeviceConnected, onDeviceDisconnected, onDeviceLocked, onDeviceUnlocked]);

  const fetchDevices = async () => {
    try {
      setLoading(true);
      const response = await userHardwareAPI.listDevices();
      setDevices(response.data.devices || []);
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to fetch devices');
    } finally {
      setLoading(false);
    }
  };

  const handleAddDevice = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await userHardwareAPI.createDevice(formData);
      setFormData({ tag_name: '', device_name: '' });
      setShowModal(false);
      fetchDevices();
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to add device');
    }
  };

  const handleDeleteDevice = async (deviceId: string) => {
    if (!window.confirm('Are you sure?')) return;
    try {
      await userHardwareAPI.deleteDevice(deviceId);
      fetchDevices();
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to delete device');
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleAdminClick = () => {
    console.log('Admin button clicked. User role:', user?.role);
    if (user?.role === 'admin') {
      navigate('/admin');
    } else {
      alert('You are not an admin!');
    }
  };

  return (
    <div className="dashboard-content" style={{ padding: '20px' }}>
      <div className="devices-section">
          <div className="section-header">
            <h2>My Devices</h2>
            <button className="btn-primary" onClick={() => setShowModal(true)}>
              + Add Device
            </button>
          </div>

          {error && <div className="error-message">{error}</div>}

          {loading ? (
            <div className="loading">Loading devices...</div>
          ) : devices.length === 0 ? (
            <div className="empty-state">No devices yet. Create one to get started!</div>
          ) : (
            <div className="devices-grid">
              {devices.map((device) => (
                <div
                  key={device.tag_name}
                  className="device-card"
                  style={{ cursor: 'default' }}
                >
                  <h3>{device.tag_name}</h3>
                  <p className="device-name">{device.device_name}</p>
                  <div className="device-meta">
                    <span className={`status ${device.status}`}>{device.status}</span>
                    <span className="created">{new Date(device.created_at).toLocaleDateString()}</span>
                  </div>
                  <div className="device-actions">
                    <button
                      className="btn-danger"
                      onClick={() => {
                        handleDeleteDevice(device.tag_name);
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      {showModal && (
        <div className="modal">
          <div className="modal-content">
            <div className="modal-header">
              <h2>Add New Device</h2>
              <button className="close-btn" onClick={() => setShowModal(false)}>
                ×
              </button>
            </div>
            <form onSubmit={handleAddDevice}>
              <div className="form-group">
                <label>Tag Name</label>
                <input
                  type="text"
                  value={formData.tag_name}
                  onChange={(e) => setFormData({ ...formData, tag_name: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label>Device Name</label>
                <input
                  type="text"
                  value={formData.device_name}
                  onChange={(e) => setFormData({ ...formData, device_name: e.target.value })}
                  required
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
