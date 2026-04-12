import React, { useEffect, useMemo, useState } from 'react';
import { flashQueueAPI, type FlashEligibleDevice, type FlashQueueRequest } from '../api/flashQueue';

interface FlashDialogProps {
  isOpen: boolean;
  projectName: string;
  firmwarePath: string;
  initialBoard: string;
  onClose: () => void;
  onQueued: (request: FlashQueueRequest, board: string) => void;
}

const OVERLAY_STYLE: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.62)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1100,
};

const MODAL_STYLE: React.CSSProperties = {
  width: 'min(640px, 94vw)',
  maxHeight: '88vh',
  overflow: 'hidden',
  borderRadius: 10,
  border: '1px solid var(--vscode-border)',
  background: 'var(--vscode-bg-sidebar)',
  boxShadow: '0 18px 42px rgba(0,0,0,0.45)',
  display: 'flex',
  flexDirection: 'column',
};

const BOARD_OPTIONS = [
  { value: 'esp32', label: 'ESP32' },
  { value: 'esp8266', label: 'ESP8266' },
  { value: 'arduino_uno', label: 'Arduino Uno' },
];

const BAUD_RATE_OPTIONS = [9600, 19200, 38400, 57600, 74880, 115200, 230400, 460800, 921600];

const normalizeBoardValue = (value?: string | null) => (value || '').trim().toLowerCase();

export const FlashDialog: React.FC<FlashDialogProps> = ({
  isOpen,
  projectName,
  firmwarePath,
  initialBoard,
  onClose,
  onQueued,
}) => {
  const [devices, setDevices] = useState<FlashEligibleDevice[]>([]);
  const [selectedTag, setSelectedTag] = useState('');
  const [board, setBoard] = useState(initialBoard);
  const [baudRate, setBaudRate] = useState(115200);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isOpen) {
      setError('');
      setBoard('');
      setDevices([]);
      setSelectedTag('');
      return;
    }

    setBoard(normalizeBoardValue(initialBoard));
    setBaudRate(115200);
    setError('');
  }, [initialBoard, isOpen]);

  useEffect(() => {
    if (!isOpen || !board) {
      return;
    }

    let isCancelled = false;

    setLoading(true);
    setError('');

    flashQueueAPI.listEligibleDevices(board)
      .then((response) => {
        if (isCancelled) {
          return;
        }
        setDevices(response.data.devices || []);
      })
      .catch((err: any) => {
        if (isCancelled) {
          return;
        }
        setError(err.response?.data?.error || err.message || 'Khong the tai danh sach thiet bi.');
        setDevices([]);
        setSelectedTag('');
      })
      .finally(() => {
        if (!isCancelled) {
          setLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [board, isOpen]);

  useEffect(() => {
    setSelectedTag((currentTag) => {
      if (currentTag && devices.some((device) => device.tag_name === currentTag)) {
        return currentTag;
      }
      return devices[0]?.tag_name || '';
    });
  }, [devices]);

  const selectedDevice = useMemo(
    () => devices.find((device) => device.tag_name === selectedTag) || null,
    [devices, selectedTag]
  );

  const resolveQueuedRequest = async (fallbackRequest?: FlashQueueRequest | null) => {
    if (fallbackRequest) {
      return fallbackRequest;
    }

    const activeResponse = await flashQueueAPI.getActiveRequest();
      const activeRequest = activeResponse.data.request;
      if (
        activeRequest
        && activeRequest.tag_name === selectedTag
      && activeRequest.board_type === board
      && activeRequest.status !== 'cancelled'
    ) {
      return activeRequest;
    }

    return null;
  };

  const handleSubmit = async () => {
    if (!selectedTag) {
      setError('Vui long chon thiet bi de gui yeu cau nap.');
      return;
    }

    setSubmitting(true);
    setError('');

    try {
      const response = await flashQueueAPI.enqueueRequest({
        project_name: projectName,
        tag_name: selectedTag,
        board_type: board,
        firmware_path: firmwarePath,
        baud_rate: baudRate,
      });
      const queuedRequest = await resolveQueuedRequest(response.data.request || null);
      if (!queuedRequest) {
        throw new Error('Queue request succeeded but no active request data was returned.');
      }

      onQueued(queuedRequest, board);
    } catch (err: any) {
      try {
        const queuedRequest = await resolveQueuedRequest();
        if (queuedRequest) {
          onQueued(queuedRequest, board);
          return;
        }
      } catch {
        // Ignore fallback lookup errors and surface the original submit error below.
      }

      setError(err.response?.data?.error || err.message || 'Khong the gui yeu cau nap.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div style={OVERLAY_STYLE} onClick={onClose}>
      <div style={MODAL_STYLE} onClick={(event) => event.stopPropagation()}>
        <div
          style={{
            padding: '16px 18px',
            borderBottom: '1px solid var(--vscode-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--vscode-bg-tabbar)',
          }}
        >
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--vscode-text-main)' }}>Queue Flash Request</div>
            <div style={{ fontSize: 12, color: 'var(--vscode-text-muted)', marginTop: 4 }}>
              Project: {projectName} • Firmware: {firmwarePath}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--vscode-text-muted)',
              fontSize: 22,
              cursor: 'pointer',
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>

        <div style={{ padding: 18, overflowY: 'auto', display: 'grid', gap: 16 }}>
          <section>
            <div style={{ color: 'var(--vscode-text-muted)', fontSize: 12, textTransform: 'uppercase', marginBottom: 10 }}>
              1. Chon Board
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {BOARD_OPTIONS.map((option) => {
                const selected = board === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setBoard(option.value)}
                    style={{
                      padding: '10px 14px',
                      borderRadius: 8,
                      border: `1px solid ${selected ? 'var(--vscode-accent)' : 'var(--vscode-border)'}`,
                      background: selected ? 'rgba(0, 122, 204, 0.18)' : 'var(--vscode-bg-panel)',
                      color: 'var(--vscode-text-main)',
                      cursor: 'pointer',
                      fontWeight: selected ? 700 : 500,
                    }}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
          </section>

          <section>
            <div style={{ color: 'var(--vscode-text-muted)', fontSize: 12, textTransform: 'uppercase', marginBottom: 10 }}>
              2. Chon baud rate serial
            </div>
            <label style={{ display: 'grid', gap: 8, color: 'var(--vscode-text-main)' }}>
              <span style={{ fontSize: 14 }}>Baud rate duoc dung cho serial capture sau khi flash.</span>
              <select
                value={baudRate}
                onChange={(event) => setBaudRate(Number(event.target.value))}
                disabled={submitting}
                style={{
                  padding: '10px 12px',
                  borderRadius: 8,
                  border: '1px solid var(--vscode-border)',
                  background: 'var(--vscode-bg-panel)',
                  color: 'var(--vscode-text-main)',
                }}
              >
                {BAUD_RATE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          </section>

          <section>
            <div style={{ color: 'var(--vscode-text-muted)', fontSize: 12, textTransform: 'uppercase', marginBottom: 10 }}>
              3. Chon thiet bi dang ket noi
            </div>
            {loading ? (
              <div style={{ color: 'var(--vscode-text-muted)', padding: '18px 0' }}>Dang tai thiet bi...</div>
            ) : devices.length === 0 ? (
              <div
                style={{
                  padding: 14,
                  borderRadius: 8,
                  background: 'var(--vscode-bg-panel)',
                  border: '1px solid var(--vscode-border)',
                  color: 'var(--vscode-text-muted)',
                }}
              >
                Khong co thiet bi approved nao phu hop voi board dang chon va quyen su dung hien tai.
              </div>
            ) : (
              <div style={{ display: 'grid', gap: 10 }}>
                {devices.map((device) => {
                  const selected = device.tag_name === selectedTag;
                  const busyLabel = device.is_busy ? `Dang dung (${device.queue_depth})` : 'Ranh';
                  const queueLabel = device.queue_depth > 0 ? ` • Queue: ${device.queue_depth}` : '';
                  return (
                    <button
                      key={device.tag_name}
                      type="button"
                      onClick={() => setSelectedTag(device.tag_name)}
                      style={{
                        textAlign: 'left',
                        padding: 14,
                        borderRadius: 8,
                        border: `1px solid ${selected ? 'var(--vscode-accent)' : 'var(--vscode-border)'}`,
                        background: selected ? 'rgba(0, 122, 204, 0.16)' : 'var(--vscode-bg-panel)',
                        color: 'var(--vscode-text-main)',
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                          <div>
                            <div style={{ fontWeight: 700 }}>{device.device_name || device.tag_name}</div>
                            <div style={{ fontSize: 12, color: 'var(--vscode-text-muted)', marginTop: 4 }}>
                              {device.tag_name} • {device.type} • {device.board_class || 'Unclassified'} • {device.port || 'No port'}
                            </div>
                          </div>
                        <div
                          style={{
                            padding: '4px 10px',
                            borderRadius: 999,
                            background: device.is_busy ? 'rgba(255, 193, 7, 0.16)' : 'rgba(40, 167, 69, 0.16)',
                            color: device.is_busy ? '#facc15' : '#4ade80',
                            fontSize: 12,
                            fontWeight: 700,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {busyLabel}{queueLabel}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {selectedDevice && (
            <section
              style={{
                padding: 14,
                borderRadius: 8,
                background: 'var(--vscode-bg-panel)',
                border: '1px solid var(--vscode-border)',
                display: 'grid',
                gap: 6,
                color: 'var(--vscode-text-main)',
              }}
            >
              <div style={{ fontSize: 12, color: 'var(--vscode-text-muted)', textTransform: 'uppercase' }}>
                Tong quan request
              </div>
              <div>Board: <strong>{BOARD_OPTIONS.find((option) => option.value === board)?.label || board}</strong></div>
              <div>Baud rate: <strong>{baudRate}</strong></div>
              <div>Tag: <strong>{selectedDevice.tag_name}</strong></div>
              <div>Queue depth hien tai: <strong>{selectedDevice.queue_depth}</strong></div>
            </section>
          )}

          {error && (
            <div
              style={{
                padding: 12,
                borderRadius: 8,
                border: '1px solid rgba(220, 53, 69, 0.55)',
                background: 'rgba(220, 53, 69, 0.12)',
                color: '#fca5a5',
                fontSize: 14,
              }}
            >
              {error}
            </div>
          )}
        </div>

        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 10,
            padding: 16,
            borderTop: '1px solid var(--vscode-border)',
            background: 'var(--vscode-bg-tabbar)',
          }}
        >
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            style={{
              padding: '10px 14px',
              borderRadius: 8,
              border: '1px solid var(--vscode-border)',
              background: 'var(--vscode-bg-panel)',
              color: 'var(--vscode-text-main)',
              cursor: submitting ? 'not-allowed' : 'pointer',
              opacity: submitting ? 0.6 : 1,
            }}
          >
            Tro ve
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting || loading || !selectedTag}
            style={{
              padding: '10px 16px',
              borderRadius: 8,
              border: '1px solid #0f766e',
              background: '#0f766e',
              color: '#fff',
              fontWeight: 700,
              cursor: submitting || loading || !selectedTag ? 'not-allowed' : 'pointer',
              opacity: submitting || loading || !selectedTag ? 0.6 : 1,
            }}
          >
            {submitting ? 'Dang gui...' : 'Gui yeu cau nap'}
          </button>
        </div>
      </div>
    </div>
  );
};
