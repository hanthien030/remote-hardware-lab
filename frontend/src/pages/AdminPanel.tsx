import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminHardwareAPI, adminUserAPI } from '../api';
import { useAuthStore } from '../store/authStore';
import '../styles/Admin.css';

type UsageMode = 'free' | 'share' | 'block';
type BoardClass = 'esp32' | 'esp8266' | 'arduino_uno';

interface DeviceAssignment {
  user_id: string;
  expires_at: string | null;
}

interface Device {
  tag_name: string;
  device_name: string | null;
  type: string;
  port: string | null;
  status: string;
  usage_mode: UsageMode;
  board_class?: BoardClass | null;
  review_state?: 'pending_review' | 'approved';
  assigned_to: string | null;
  assignments: DeviceAssignment[];
  locked_by_user: string | null;
}

interface PendingDevice {
  tag_name: string;
  device_name: string | null;
  type: string;
  port: string | null;
  status: string;
  usage_mode: UsageMode;
  board_class?: BoardClass | null;
  chip_type?: string | null;
  chip_family?: string | null;
  mac_address?: string | null;
  flash_size?: string | null;
  crystal_freq?: string | null;
  review_state: 'pending_review' | 'approved';
  created_at?: string;
}

interface PendingReviewDraft {
  deviceNameInput: string;
  boardClass: '' | BoardClass;
}

interface User {
  id: string;
  username: string;
  email: string;
  role: string;
}

interface EditModalState {
  open: boolean;
  device: Device | null;
  deviceNameInput: string;
}

interface SharePanelState {
  open: boolean;
  device: Device | null;
}

const usageModeLabel = (mode: UsageMode) => {
  if (mode === 'share') return 'Share';
  if (mode === 'block') return 'Block';
  return 'Free';
};

const formatExpiry = (value: string | null) => {
  if (!value) return 'No expiry';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const boardClassLabel = (value: BoardClass) => {
  if (value === 'esp8266') return 'ESP8266';
  if (value === 'arduino_uno') return 'Arduino Uno';
  return 'ESP32';
};

const getPendingDraftBoardClass = (device: PendingDevice): PendingReviewDraft['boardClass'] => {
  if (
    device.board_class === 'esp32'
    || device.board_class === 'esp8266'
    || device.board_class === 'arduino_uno'
  ) {
    return device.board_class;
  }
  return '';
};

const buildPendingDraft = (device: PendingDevice, existingDraft?: PendingReviewDraft): PendingReviewDraft => ({
  deviceNameInput: existingDraft?.deviceNameInput ?? device.device_name ?? '',
  boardClass: existingDraft?.boardClass || getPendingDraftBoardClass(device),
});

const renderPendingMetadataValue = (value?: string | null) => value || '—';

export const AdminPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'devices' | 'users'>('devices');
  const [devices, setDevices] = useState<Device[]>([]);
  const [pendingDevices, setPendingDevices] = useState<PendingDevice[]>([]);
  const [pendingDrafts, setPendingDrafts] = useState<Record<string, PendingReviewDraft>>({});
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [usageSavingTag, setUsageSavingTag] = useState<string | null>(null);
  const [approvingTag, setApprovingTag] = useState<string | null>(null);
  const [checkingTag, setCheckingTag] = useState<string | null>(null);
  const [resettingTag, setResettingTag] = useState<string | null>(null);
  const [deletingTag, setDeletingTag] = useState<string | null>(null);
  const [pendingCheckNotes, setPendingCheckNotes] = useState<Record<string, string>>({});
  const [shareLoading, setShareLoading] = useState(false);
  const [shareUserId, setShareUserId] = useState('');
  const [shareExpiresAt, setShareExpiresAt] = useState('');

  const [editModal, setEditModal] = useState<EditModalState>({ open: false, device: null, deviceNameInput: '' });
  const [editLoading, setEditLoading] = useState(false);
  const [sharePanel, setSharePanel] = useState<SharePanelState>({ open: false, device: null });

  const navigate = useNavigate();
  const logout = useAuthStore((state) => state.logout);
  const currentUser = useAuthStore((state) => state.user);

  useEffect(() => {
    if (activeTab === 'devices') {
      void fetchDevices();
      void ensureUsersLoaded();
    } else {
      void fetchUsers();
    }
  }, [activeTab]);

  const showSuccess = (msg: string) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(''), 3000);
  };

  const fetchDevices = async () => {
    try {
      setLoading(true);
      setError('');
      const [devicesResponse, pendingResponse] = await Promise.all([
        adminHardwareAPI.listAllDevices(),
        adminHardwareAPI.listPendingDevices(),
      ]);
      const nextDevices = (devicesResponse.data.devices || []) as Device[];
      const nextPendingDevices = (pendingResponse.data.devices || []) as PendingDevice[];
      setDevices(nextDevices);
      setPendingDevices(nextPendingDevices);
      setPendingDrafts((currentDrafts) => {
        const nextDrafts: Record<string, PendingReviewDraft> = {};
        nextPendingDevices.forEach((device) => {
          nextDrafts[device.tag_name] = buildPendingDraft(device, currentDrafts[device.tag_name]);
        });
        return nextDrafts;
      });
      setPendingCheckNotes((currentNotes) => {
        const nextNotes: Record<string, string> = {};
        nextPendingDevices.forEach((device) => {
          if (currentNotes[device.tag_name]) {
            nextNotes[device.tag_name] = currentNotes[device.tag_name];
          }
        });
        return nextNotes;
      });
      setSharePanel((prev) => {
        if (!prev.device) return prev;
        const refreshed = nextDevices.find((device) => device.tag_name === prev.device?.tag_name) || null;
        if (!refreshed) {
          return { open: false, device: null };
        }
        return { ...prev, device: refreshed };
      });
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to fetch devices');
    } finally {
      setLoading(false);
    }
  };

  const fetchUsers = async () => {
    try {
      setLoading(true);
      setError('');
      const response = await adminUserAPI.listAllUsers();
      setUsers(response.data.users || []);
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to fetch users');
    } finally {
      setLoading(false);
    }
  };

  const ensureUsersLoaded = async () => {
    if (users.length > 0) return;
    try {
      const response = await adminUserAPI.listAllUsers();
      setUsers(response.data.users || []);
    } catch {
      // Device management can still work even if user list refresh fails.
    }
  };

  const shareableUsers = useMemo(
    () => users.filter((user) => user.role !== 'admin'),
    [users]
  );

  const openEditModal = (device: Device) => {
    setEditModal({ open: true, device, deviceNameInput: device.device_name || '' });
  };

  const openSharePanel = async (device: Device) => {
    await ensureUsersLoaded();
    setSharePanel({ open: true, device });
    setShareUserId('');
    const d = new Date();
    d.setDate(d.getDate() + 30);
    setShareExpiresAt(d.toISOString().slice(0, 10));
  };

  const handleUsageModeChange = async (device: Device, nextMode: UsageMode) => {
    if (device.usage_mode === nextMode) return;

    setUsageSavingTag(device.tag_name);
    setError('');
    try {
      await adminHardwareAPI.updateDevice(device.tag_name, {
        tag_name: device.tag_name,
        device_name: device.device_name,
        usage_mode: nextMode,
      });
      showSuccess(`Updated ${device.tag_name} to ${usageModeLabel(nextMode)} mode.`);
      await fetchDevices();
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to update device usage mode');
    } finally {
      setUsageSavingTag(null);
    }
  };

  const handleAssignShare = async () => {
    if (!sharePanel.device || !shareUserId.trim()) return;

    setShareLoading(true);
    setError('');
    try {
      await adminHardwareAPI.assignDevice(
        sharePanel.device.tag_name,
        shareUserId.trim(),
        `${shareExpiresAt} 23:59:59`
      );
      showSuccess(`Shared ${sharePanel.device.tag_name} with ${shareUserId.trim()}.`);
      setShareUserId('');
      await fetchDevices();
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to share device');
    } finally {
      setShareLoading(false);
    }
  };

  const handleRevokeShare = async (tagName: string, userId: string) => {
    if (!window.confirm(`Revoke ${userId} from ${tagName}?`)) return;

    setShareLoading(true);
    setError('');
    try {
      await adminHardwareAPI.revokeAssignment(tagName, userId);
      showSuccess(`Revoked ${userId} from ${tagName}.`);
      await fetchDevices();
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to revoke shared user');
    } finally {
      setShareLoading(false);
    }
  };

  const handleEditSave = async () => {
    if (!editModal.device) return;

    setEditLoading(true);
    setError('');
    try {
      await adminHardwareAPI.updateDevice(editModal.device.tag_name, {
        tag_name: editModal.device.tag_name,
        device_name: editModal.deviceNameInput,
        usage_mode: editModal.device.usage_mode,
      });
      showSuccess(`Updated device name for ${editModal.device.tag_name}.`);
      setEditModal({ open: false, device: null, deviceNameInput: '' });
      await fetchDevices();
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to update device');
    } finally {
      setEditLoading(false);
    }
  };

  const updatePendingDraft = (tagName: string, patch: Partial<PendingReviewDraft>) => {
    setPendingDrafts((prev) => ({
      ...prev,
      [tagName]: {
        deviceNameInput: prev[tagName]?.deviceNameInput || '',
        boardClass: prev[tagName]?.boardClass || '',
        ...patch,
      },
    }));
  };

  const handleApprovePendingDevice = async (device: PendingDevice) => {
    const draft = pendingDrafts[device.tag_name] || buildPendingDraft(device);
    if (!draft.boardClass) {
      setError(`Please choose a board class for ${device.tag_name}.`);
      return;
    }

    setApprovingTag(device.tag_name);
    setError('');
    try {
      await adminHardwareAPI.approveDevice(device.tag_name, {
        device_name: draft.deviceNameInput.trim() || null,
        board_class: draft.boardClass,
      });
      showSuccess(`Approved ${device.tag_name} as ${boardClassLabel(draft.boardClass)}.`);
      await fetchDevices();
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to approve pending device');
    } finally {
      setApprovingTag(null);
    }
  };

  const handleCheckPendingDevice = async (device: PendingDevice) => {
    setCheckingTag(device.tag_name);
    setError('');
    try {
      const response = await adminHardwareAPI.checkPendingDevice(device.tag_name);
      const refreshedDevice = response.data.device as PendingDevice | undefined;
      const checkSummary = response.data.check_summary || response.data.message || 'Check completed.';

      if (refreshedDevice) {
        setPendingDevices((prev) => prev.map((item) => (
          item.tag_name === refreshedDevice.tag_name ? refreshedDevice : item
        )));
        setPendingDrafts((prev) => ({
          ...prev,
          [refreshedDevice.tag_name]: buildPendingDraft(refreshedDevice, prev[refreshedDevice.tag_name]),
        }));
      }

      setPendingCheckNotes((prev) => ({
        ...prev,
        [device.tag_name]: checkSummary,
      }));
      showSuccess(response.data.message || `Checked ${device.tag_name}.`);
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to check pending device');
    } finally {
      setCheckingTag(null);
    }
  };

  const handleResetDeviceReview = async (device: Device) => {
    if (!window.confirm(`Reset ${device.tag_name} back to Pending Review?`)) return;

    setResettingTag(device.tag_name);
    setError('');
    try {
      await adminHardwareAPI.resetDeviceReview(device.tag_name);
      showSuccess(`Moved ${device.tag_name} back to Pending Review.`);
      await fetchDevices();
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to reset device review');
    } finally {
      setResettingTag(null);
    }
  };

  const handleDeleteDeviceRecord = async (tagName: string) => {
    if (!window.confirm(`Delete device record ${tagName}? This cannot be undone.`)) return;

    setDeletingTag(tagName);
    setError('');
    try {
      await adminHardwareAPI.deleteDeviceRecord(tagName);
      showSuccess(`Deleted device record ${tagName}.`);
      await fetchDevices();
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to delete device record');
    } finally {
      setDeletingTag(null);
    }
  };

  const handleDeleteUser = async (userId: string, username: string) => {
    if (username === currentUser?.username) {
      alert('Cannot delete your own account.');
      return;
    }
    if (!window.confirm(`Delete user "${username}"? This cannot be undone.`)) return;
    try {
      await adminUserAPI.deleteUser(userId);
      showSuccess(`Deleted user "${username}".`);
      await fetchUsers();
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to delete user');
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="admin-panel">
      <nav className="admin-tabs">
        <button className={`tab ${activeTab === 'devices' ? 'active' : ''}`} onClick={() => setActiveTab('devices')}>
          Devices
        </button>
        <button className={`tab ${activeTab === 'users' ? 'active' : ''}`} onClick={() => setActiveTab('users')}>
          Users
        </button>
      </nav>

      <main className="admin-content">
        {error && <div className="error-message">❌ {error}</div>}
        {successMsg && <div className="success-message">{successMsg}</div>}

        {loading ? (
          <div className="loading">Loading...</div>
        ) : activeTab === 'devices' ? (
          <div className="devices-section">
            <div className="devices-toolbar">
              <div>
                <h2>Device Management</h2>
                <p>Set each device to Free, Share, or Block, then manage sharing only when the device is in Share mode.</p>
              </div>
            </div>

            <section className="pending-review-card">
              <div className="pending-review-header">
                <div>
                  <h3>Pending Review</h3>
                  <p>New devices stay blocked until an admin names and classifies them.</p>
                </div>
                <span className="pending-review-badge">{pendingDevices.length}</span>
              </div>

              {pendingDevices.length === 0 ? (
                <div className="pending-review-empty">No devices are waiting for review.</div>
              ) : (
                <div className="pending-review-list">
                  {pendingDevices.map((device) => {
                     const draft = pendingDrafts[device.tag_name] || buildPendingDraft(device);
                     const isApproving = approvingTag === device.tag_name;
                     const isChecking = checkingTag === device.tag_name;
                     const isDeleting = deletingTag === device.tag_name;
                     const metadataItems = [
                       { label: 'Chip Type', value: device.chip_type },
                       { label: 'Chip Family', value: device.chip_family },
                       { label: 'MAC', value: device.mac_address },
                       { label: 'Flash', value: device.flash_size },
                       { label: 'Crystal', value: device.crystal_freq },
                    ];
                    return (
                      <div key={device.tag_name} className="pending-review-item">
                        <div className="pending-review-item-header">
                          <div>
                            <strong>{device.tag_name}</strong>
                            <div className="device-subline">
                              {device.type} • {device.port || 'No port'} • {device.status}
                            </div>
                          </div>
                          <span className="usage-badge usage-block">Blocked</span>
                        </div>

                        <div className="pending-review-metadata">
                          {metadataItems.map((item) => (
                            <div key={`${device.tag_name}-${item.label}`} className="pending-review-meta-pill">
                              <span className="pending-review-meta-label">{item.label}</span>
                              <span className="pending-review-meta-value">{renderPendingMetadataValue(item.value)}</span>
                            </div>
                          ))}
                        </div>

                        {pendingCheckNotes[device.tag_name] ? (
                          <div className="pending-review-check-note">{pendingCheckNotes[device.tag_name]}</div>
                        ) : null}

                        <div className="pending-review-form">
                          <label className="share-form-label">
                            Device Name
                            <input
                              type="text"
                              value={draft.deviceNameInput}
                              onChange={(event) => updatePendingDraft(device.tag_name, { deviceNameInput: event.target.value })}
                              placeholder="e.g. ESP8266_TEST"
                              className="share-date-input"
                            />
                          </label>

                          <label className="share-form-label">
                            Board Class
                            <select
                              value={draft.boardClass}
                              onChange={(event) => updatePendingDraft(device.tag_name, { boardClass: event.target.value as PendingReviewDraft['boardClass'] })}
                              className="usage-select"
                            >
                              <option value="">Choose board class</option>
                              <option value="esp32">ESP32</option>
                              <option value="esp8266">ESP8266</option>
                              <option value="arduino_uno">Arduino Uno</option>
                            </select>
                          </label>

                          <div className="pending-review-form-actions">
                            <button
                              className="btn-secondary"
                              onClick={() => handleCheckPendingDevice(device)}
                              disabled={isApproving || isChecking || isDeleting}
                            >
                              {isChecking ? 'Checking...' : 'Check'}
                            </button>
                            <button
                              className="btn-primary"
                              onClick={() => handleApprovePendingDevice(device)}
                              disabled={isApproving || isChecking || isDeleting || !draft.boardClass}
                            >
                              {isApproving ? 'Approving...' : 'Confirm & Approve'}
                            </button>
                            <button
                              className="btn-danger"
                              onClick={() => handleDeleteDeviceRecord(device.tag_name)}
                              disabled={isApproving || isChecking || isDeleting}
                            >
                              {isDeleting ? 'Deleting...' : 'Delete Record'}
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {devices.length === 0 ? (
              <div className="empty-state">No approved devices found</div>
            ) : (
              <div className="device-layout">
                <div className="device-list-card">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>Tag Name</th>
                        <th>Device Name</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Usage Mode</th>
                        <th>Share</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {devices.map((device) => {
                        const isShareMode = device.usage_mode === 'share';
                        return (
                          <tr key={device.tag_name}>
                            <td>
                              <strong>{device.tag_name}</strong>
                              <div className="device-subline">{device.port || 'No port'}</div>
                            </td>
                            <td>{device.device_name || <span className="muted-text">—</span>}</td>
                            <td><code>{device.type}</code></td>
                            <td>
                              <span className={`status ${device.status}`}>{device.status}</span>
                            </td>
                            <td>
                              <div className="usage-mode-cell">
                                <span className={`usage-badge usage-${device.usage_mode}`}>{usageModeLabel(device.usage_mode)}</span>
                                <select
                                  value={device.usage_mode}
                                  onChange={(event) => handleUsageModeChange(device, event.target.value as UsageMode)}
                                  disabled={usageSavingTag === device.tag_name}
                                  className="usage-select"
                                >
                                  <option value="free">Free</option>
                                  <option value="share">Share</option>
                                  <option value="block">Block</option>
                                </select>
                              </div>
                            </td>
                            <td>
                              {isShareMode ? (
                                <div className="share-summary">
                                  <div>{device.assignments.length} shared user{device.assignments.length === 1 ? '' : 's'}</div>
                                  <button
                                    className="btn-secondary"
                                    onClick={() => openSharePanel(device)}
                                  >
                                    Manage share
                                  </button>
                                </div>
                              ) : (
                                <span className="muted-text">
                                  {device.usage_mode === 'free' ? 'Open to all users' : 'Blocked from queue use'}
                                </span>
                              )}
                            </td>
                            <td>
                              <div className="admin-table-actions">
                                <button
                                  className="btn-secondary"
                                  onClick={() => openEditModal(device)}
                                >
                                  Edit name
                                </button>
                                <button
                                  className="btn-secondary"
                                  onClick={() => handleResetDeviceReview(device)}
                                  disabled={resettingTag === device.tag_name || deletingTag === device.tag_name}
                                >
                                  {resettingTag === device.tag_name ? 'Resetting...' : 'Reset to Pending'}
                                </button>
                                <button
                                  className="btn-danger"
                                  onClick={() => handleDeleteDeviceRecord(device.tag_name)}
                                  disabled={resettingTag === device.tag_name || deletingTag === device.tag_name}
                                >
                                  {deletingTag === device.tag_name ? 'Deleting...' : 'Delete Record'}
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <aside className="share-panel-card">
                  {sharePanel.open && sharePanel.device ? (
                    <>
                      <div className="share-panel-header">
                        <div>
                          <h3>Share Management</h3>
                          <p>{sharePanel.device.tag_name}</p>
                        </div>
                        <button
                          className="btn-secondary"
                          onClick={() => setSharePanel({ open: false, device: null })}
                        >
                          Close
                        </button>
                      </div>

                      {sharePanel.device.usage_mode !== 'share' ? (
                        <div className="share-panel-empty">
                          This device is not in Share mode. Set its usage mode to Share to manage user access.
                        </div>
                      ) : (
                        <>
                          <div className="share-panel-section">
                            <h4>Currently shared users</h4>
                            {sharePanel.device.assignments.length === 0 ? (
                              <div className="share-panel-empty">No active shared users yet.</div>
                            ) : (
                              <div className="share-assignment-list">
                                {sharePanel.device.assignments.map((assignment) => (
                                  <div key={`${sharePanel.device?.tag_name}-${assignment.user_id}`} className="share-assignment-row">
                                    <div>
                                      <strong>{assignment.user_id}</strong>
                                      <div className="device-subline">Expires: {formatExpiry(assignment.expires_at)}</div>
                                    </div>
                                    <button
                                      className="btn-danger"
                                      onClick={() => handleRevokeShare(sharePanel.device!.tag_name, assignment.user_id)}
                                      disabled={shareLoading}
                                    >
                                      Revoke
                                    </button>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>

                          <div className="share-panel-section">
                            <h4>Add shared user</h4>
                            <label className="share-form-label">
                              User
                              <select
                                value={shareUserId}
                                onChange={(event) => setShareUserId(event.target.value)}
                                className="usage-select"
                              >
                                <option value="">Select a user</option>
                                {shareableUsers.map((user) => (
                                  <option key={user.id} value={user.username}>
                                    {user.username} ({user.email})
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="share-form-label">
                              Expiry
                              <input
                                type="date"
                                value={shareExpiresAt}
                                onChange={(event) => setShareExpiresAt(event.target.value)}
                                className="share-date-input"
                              />
                            </label>
                            <button
                              className="btn-primary"
                              onClick={handleAssignShare}
                              disabled={shareLoading || !shareUserId || !shareExpiresAt}
                            >
                              {shareLoading ? 'Saving...' : 'Add shared user'}
                            </button>
                          </div>
                        </>
                      )}
                    </>
                  ) : (
                    <div className="share-panel-empty">
                      Select “Manage share” on a Share-mode device to see current shared users, add an expiry, or revoke access.
                    </div>
                  )}
                </aside>
              </div>
            )}
          </div>
        ) : (
          <div className="users-section">
            <h2>All Users ({users.length})</h2>
            {users.length === 0 ? (
              <div className="empty-state">No users found</div>
            ) : (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Username</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>
                        {user.username}
                        {user.username === currentUser?.username && (
                          <span className="badge-self"> (You)</span>
                        )}
                      </td>
                      <td>{user.email}</td>
                      <td><span className={`role ${user.role}`}>{user.role}</span></td>
                      <td>
                        <button
                          className="btn-danger"
                          onClick={() => handleDeleteUser(user.id, user.username)}
                          disabled={user.username === currentUser?.username}
                          title={user.username === currentUser?.username ? 'Cannot delete yourself' : 'Delete user'}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </main>

      {editModal.open && editModal.device && (
        <div className="modal-overlay" onClick={() => setEditModal({ open: false, device: null, deviceNameInput: '' })}>
          <div className="admin-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Edit Device</h3>
            <p><strong>Tag:</strong> {editModal.device.tag_name} | <strong>Type:</strong> {editModal.device.type}</p>
            <div className="form-group" style={{ marginTop: 12 }}>
              <label>Friendly Name (device_name):</label>
              <input
                type="text"
                value={editModal.deviceNameInput}
                onChange={(e) => setEditModal((prev) => ({ ...prev, deviceNameInput: e.target.value }))}
                placeholder="e.g. Lab ESP32 Board #1"
                style={{ width: '100%', padding: '8px', marginTop: 4 }}
              />
            </div>
            <div className="modal-actions" style={{ marginTop: 16, display: 'flex', gap: 8 }}>
              <button className="btn-secondary" onClick={() => setEditModal({ open: false, device: null, deviceNameInput: '' })}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleEditSave} disabled={editLoading}>
                {editLoading ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
