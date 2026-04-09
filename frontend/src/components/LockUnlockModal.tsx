// src/components/LockUnlockModal.tsx
import React, { useState } from 'react';
import '../styles/LockUnlockModal.css';

interface LockUnlockModalProps {
  deviceId: string;
  deviceName: string;
  isLocked: boolean;
  lockedBy?: string;
  currentUser: string;       // ← thêm: để phân biệt "tôi lock" vs "người khác lock"
  isOpen: boolean;
  onClose: () => void;
  onLock: () => Promise<void>;
  onUnlock: () => Promise<void>;
}

// 3 trạng thái rõ ràng
type LockState = 'UNLOCKED' | 'LOCKED_BY_ME' | 'LOCKED_BY_OTHERS';

export const LockUnlockModal: React.FC<LockUnlockModalProps> = ({
  deviceId,
  deviceName,
  isLocked,
  lockedBy,
  currentUser,
  isOpen,
  onClose,
  onLock,
  onUnlock,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Xác định state chính xác
  const lockState: LockState = !isLocked
    ? 'UNLOCKED'
    : lockedBy === currentUser
    ? 'LOCKED_BY_ME'
    : 'LOCKED_BY_OTHERS';

  const handleLock = async () => {
    setLoading(true);
    setError('');
    setSuccess('');
    try {
      await onLock();
      setSuccess('✅ Thiết bị đã được khóa thành công!');
      setTimeout(() => { onClose(); setSuccess(''); }, 2000);
    } catch (err: any) {
      setError(err?.response?.data?.error || 'Khóa thiết bị thất bại!');
    } finally {
      setLoading(false);
    }
  };

  const handleUnlock = async () => {
    setLoading(true);
    setError('');
    setSuccess('');
    try {
      await onUnlock();
      setSuccess('✅ Thiết bị đã được mở khóa thành công!');
      setTimeout(() => { onClose(); setSuccess(''); }, 2000);
    } catch (err: any) {
      setError(err?.response?.data?.error || 'Mở khóa thiết bị thất bại!');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  // --- Config theo từng state ---
  const stateConfig = {
    UNLOCKED: {
      headerIcon: '🔐',
      headerTitle: 'Khóa Thiết Bị',
      statusClass: 'unlocked',
      statusIcon: '🔓',
      statusTitle: 'Thiết bị chưa bị khóa',
      statusDesc: 'Bất kỳ ai cũng có thể sử dụng thiết bị này.',
      infoItems: [
        'Khóa thiết bị để đảm bảo chỉ bạn sử dụng',
        'Không ai khác có thể flash firmware khi bị khóa',
        'Bạn có thể mở khóa bất cứ lúc nào',
      ],
    },
    LOCKED_BY_ME: {
      headerIcon: '🔓',
      headerTitle: 'Mở Khóa Thiết Bị',
      statusClass: 'locked-mine',
      statusIcon: '🔒',
      statusTitle: 'Thiết bị đang do bạn khóa',
      statusDesc: `Khóa bởi: ${lockedBy} (bạn)`,
      infoItems: [
        'Thiết bị hiện đang được khóa bởi bạn',
        'Người khác không thể flash hoặc sử dụng thiết bị',
        'Mở khóa để cho phép người khác truy cập',
      ],
    },
    LOCKED_BY_OTHERS: {
      headerIcon: '⛔',
      headerTitle: 'Thiết Bị Đang Bị Khóa',
      statusClass: 'locked-others',
      statusIcon: '🔒',
      statusTitle: 'Thiết bị bị khóa bởi người khác',
      statusDesc: `Khóa bởi: ${lockedBy || 'Không xác định'}`,
      infoItems: [
        'Bạn không thể flash firmware khi thiết bị bị khóa',
        'Chỉ người khóa hoặc Admin mới có thể mở khóa',
        'Liên hệ người quản trị nếu cần quyền truy cập khẩn',
      ],
    },
  };

  const cfg = stateConfig[lockState];

  return (
    <div className="modal-overlay" onClick={() => !loading && onClose()}>
      <div className="lock-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{cfg.headerIcon} {cfg.headerTitle}</h2>
          <button className="close-btn" onClick={() => !loading && onClose()}>×</button>
        </div>

        <div className="modal-content">
          {/* Device Info */}
          <div className="device-info-card">
            <div className="device-info-item">
              <span className="label">Thiết Bị:</span>
              <span className="value">{deviceName}</span>
            </div>
            <div className="device-info-item">
              <span className="label">ID:</span>
              <span className="value">{deviceId}</span>
            </div>
          </div>

          {/* Status Box — màu khác nhau theo state */}
          <div className={`status-box ${cfg.statusClass}`}>
            <div className="status-icon">{cfg.statusIcon}</div>
            <div className="status-content">
              <div className="status-title">{cfg.statusTitle}</div>
              <div className="status-description">{cfg.statusDesc}</div>
              {lockState === 'LOCKED_BY_OTHERS' && (
                <div className="lock-warning">
                  ⚠️ Bạn không có quyền mở khóa thiết bị này
                </div>
              )}
            </div>
          </div>

          {/* Info Box */}
          <div className="info-box">
            <div className="info-title">ℹ️ Thông tin</div>
            <ul className="info-list">
              {cfg.infoItems.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>

          {/* Messages */}
          {error   && <div className="error-message">⚠️ {error}</div>}
          {success && <div className="success-message">{success}</div>}
        </div>

        {/* Actions */}
        <div className="modal-actions">
          <button className="btn-secondary" onClick={() => !loading && onClose()} disabled={loading}>
            {lockState === 'LOCKED_BY_OTHERS' ? 'Đóng' : 'Huỷ'}
          </button>

          {lockState === 'UNLOCKED' && (
            <button className="btn-primary" onClick={handleLock} disabled={loading}>
              {loading ? '⏳ Đang xử lý...' : '🔐 Khóa Thiết Bị'}
            </button>
          )}

          {lockState === 'LOCKED_BY_ME' && (
            <button className="btn-danger" onClick={handleUnlock} disabled={loading}>
              {loading ? '⏳ Đang xử lý...' : '🔓 Mở Khóa'}
            </button>
          )}

          {/* LOCKED_BY_OTHERS: không có nút action */}
        </div>
      </div>
    </div>
  );
};
