import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ToastContainer } from '../components/ToastContainer';
import { flashQueueAPI, type FlashQueueRequest, type FlashRequestStatus } from '../api/flashQueue';
import { useDeviceSocket } from '../hooks/useDeviceSocket';
import { useToast } from '../hooks/useToast';
import { useAuthStore } from '../store/authStore';

const STATUS_OPTIONS: Array<{ value: 'all' | FlashRequestStatus; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'waiting', label: 'Waiting' },
  { value: 'flashing', label: 'Flashing' },
  { value: 'success', label: 'Success' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
];

const badgeStyle = (status: FlashRequestStatus): React.CSSProperties => {
  const palette: Record<FlashRequestStatus, { bg: string; color: string }> = {
    waiting: { bg: 'rgba(250, 204, 21, 0.18)', color: '#fde047' },
    flashing: { bg: 'rgba(59, 130, 246, 0.18)', color: '#93c5fd' },
    success: { bg: 'rgba(34, 197, 94, 0.18)', color: '#86efac' },
    failed: { bg: 'rgba(239, 68, 68, 0.18)', color: '#fca5a5' },
    cancelled: { bg: 'rgba(148, 163, 184, 0.18)', color: '#cbd5e1' },
  };

  return {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 92,
    padding: '4px 10px',
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 700,
    background: palette[status].bg,
    color: palette[status].color,
    textTransform: 'uppercase',
  };
};

const formatTime = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

export const HistoryIndex: React.FC = () => {
  const navigate = useNavigate();
  const { token, user } = useAuthStore();
  const { toasts, showToast, removeToast } = useToast();
  const {
    onFlashDone,
    onFlashSerialChunk,
    onFlashSerialFinished,
    onFlashSerialPing,
    onFlashSerialStarted,
    onFlashTaskUpdate,
    emitFlashSerialPong,
    emitFlashSerialViewStart,
    emitFlashSerialViewStop,
  } = useDeviceSocket();

  const [activeRequest, setActiveRequest] = useState<FlashQueueRequest | null>(null);
  const [requests, setRequests] = useState<FlashQueueRequest[]>([]);
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null);
  const [selectedRequest, setSelectedRequest] = useState<FlashQueueRequest | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | FlashRequestStatus>('all');
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [cancellingRequestId, setCancellingRequestId] = useState<number | null>(null);
  const [stoppingLiveRequestId, setStoppingLiveRequestId] = useState<number | null>(null);
  const [liveSerialLog, setLiveSerialLog] = useState('');
  const [serialLiveState, setSerialLiveState] = useState<'idle' | 'running' | 'finished'>('idle');
  const [liveSessionNotice, setLiveSessionNotice] = useState('');

  const fetchActiveRequest = useCallback(async () => {
    if (!token) {
      setActiveRequest(null);
      return;
    }

    try {
      const response = await flashQueueAPI.getActiveRequest();
      setActiveRequest(response.data.request);
    } catch {
      setActiveRequest(null);
    }
  }, [token]);

  const fetchHistory = useCallback(async () => {
    if (!token) {
      setRequests([]);
      return;
    }

    setLoading(true);
    try {
      const response = await flashQueueAPI.listHistory({
        page: 1,
        limit: 25,
        status: statusFilter === 'all' ? undefined : statusFilter,
      });
      setRequests(response.data.items || []);
    } catch (error: any) {
      setRequests([]);
      showToast(error.response?.data?.error || error.message || 'Unable to load flash history.', 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast, statusFilter, token]);

  const fetchDetail = useCallback(async (requestId: number) => {
    setDetailLoading(true);
    try {
      const response = await flashQueueAPI.getRequestDetail(requestId);
      setSelectedRequest(response.data.request);
      setLiveSerialLog(response.data.request.serial_log || '');
      setSerialLiveState('idle');
      setLiveSessionNotice('');
    } catch (error: any) {
      setSelectedRequest(null);
      setLiveSerialLog('');
      setSerialLiveState('idle');
      setLiveSessionNotice('');
      showToast(error.response?.data?.error || error.message || 'Unable to load request detail.', 'error');
    } finally {
      setDetailLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchActiveRequest();
    fetchHistory();
  }, [fetchActiveRequest, fetchHistory]);

  useEffect(() => {
    if (selectedRequestId == null) return;
    fetchDetail(selectedRequestId);
  }, [fetchDetail, selectedRequestId]);

  useEffect(() => {
    if (selectedRequestId && requests.some((request) => request.id === selectedRequestId)) {
      return;
    }

    if (activeRequest) {
      setSelectedRequestId(activeRequest.id);
      return;
    }

    if (requests.length > 0) {
      setSelectedRequestId(requests[0].id);
      return;
    }

    setSelectedRequestId(null);
    setSelectedRequest(null);
    setLiveSerialLog('');
    setSerialLiveState('idle');
    setLiveSessionNotice('');
  }, [activeRequest, requests, selectedRequestId]);

  const isViewingActiveSerial =
    !!activeRequest &&
    !!selectedRequest &&
    selectedRequest.id === activeRequest.id &&
    activeRequest.status === 'flashing';

  useEffect(() => {
    if (!isViewingActiveSerial || !selectedRequest) return undefined;

    emitFlashSerialViewStart(selectedRequest.id);
    return () => {
      emitFlashSerialViewStop(selectedRequest.id);
    };
  }, [emitFlashSerialViewStart, emitFlashSerialViewStop, isViewingActiveSerial, selectedRequest]);

  useEffect(() => {
    if (!token || !user?.username) return undefined;

    const refreshForCurrentUser = (eventUser?: string) => {
      if (eventUser !== user.username) return;
      fetchActiveRequest();
      fetchHistory();
      if (selectedRequestId != null) {
        fetchDetail(selectedRequestId);
      }
    };

    const unsubTaskUpdate = onFlashTaskUpdate((event) => refreshForCurrentUser(event.user));
    const unsubFlashDone = onFlashDone((event) => refreshForCurrentUser(event.user));

    const unsubSerialStarted = onFlashSerialStarted((event) => {
      if (event.user !== user.username) return;
      if (selectedRequestId === event.request_id) {
        setSerialLiveState('running');
        setLiveSessionNotice('Live serial session is active.');
      }
    });

    const unsubSerialChunk = onFlashSerialChunk((event) => {
      if (event.user !== user.username) return;
      if (selectedRequestId === event.request_id) {
        setSerialLiveState('running');
        setLiveSerialLog((prev) => `${prev}${event.chunk}`);
      }
    });

    const unsubSerialFinished = onFlashSerialFinished((event) => {
      if (event.user !== user.username) return;
      if (selectedRequestId === event.request_id) {
        setSerialLiveState('finished');
        if (event.reason === 'viewer_timeout') {
          setLiveSessionNotice('Live serial session ended because the viewer did not answer in time.');
        } else if (event.reason === 'viewer_inactive') {
          setLiveSessionNotice('Live serial session ended because the viewer left the page or went offline.');
        } else if (event.reason === 'user_stopped') {
          setLiveSessionNotice('Live serial session was stopped and the device lock is being released.');
        } else {
          setLiveSessionNotice('');
        }
        fetchDetail(event.request_id);
      }
    });

    const unsubSerialPing = onFlashSerialPing((event) => {
      if (!selectedRequest || event.request_id !== selectedRequest.id) return;
      if (!isViewingActiveSerial) return;
      if (document.visibilityState !== 'visible') return;

      emitFlashSerialPong(event.request_id);
    });

    return () => {
      unsubTaskUpdate();
      unsubFlashDone();
      unsubSerialStarted();
      unsubSerialChunk();
      unsubSerialFinished();
      unsubSerialPing();
    };
  }, [
    emitFlashSerialPong,
    fetchActiveRequest,
    fetchDetail,
    fetchHistory,
    isViewingActiveSerial,
    onFlashDone,
    onFlashSerialChunk,
    onFlashSerialFinished,
    onFlashSerialPing,
    onFlashSerialStarted,
    onFlashTaskUpdate,
    selectedRequest,
    selectedRequestId,
    token,
    user?.username,
  ]);

  const handleCancel = async (request: FlashQueueRequest) => {
    if (request.status !== 'waiting') return;

    setCancellingRequestId(request.id);
    try {
      await flashQueueAPI.cancelRequest(request.id);
      showToast('Cancelled the waiting flash request.', 'success');
      await fetchActiveRequest();
      await fetchHistory();
      if (selectedRequestId === request.id) {
        await fetchDetail(request.id);
      }
    } catch (error: any) {
      try {
        const verification = await flashQueueAPI.verifyCancelOutcome(request.id);
        if (verification.cancelled) {
          setActiveRequest(verification.activeRequest);
          await fetchHistory();
          if (selectedRequestId === request.id) {
            if (verification.detailRequest) {
              setSelectedRequest(verification.detailRequest);
              setLiveSerialLog(verification.detailRequest.serial_log || '');
              setSerialLiveState('idle');
              setLiveSessionNotice('');
            } else {
              await fetchDetail(request.id);
            }
          }
          showToast('Cancelled the waiting flash request.', 'success');
          return;
        }
      } catch {
        // Fall through to the original error toast if recovery also fails.
      }

      showToast(error.response?.data?.error || error.message || 'Unable to cancel request.', 'error');
    } finally {
      setCancellingRequestId(null);
    }
  };

  const handleStopLiveSession = async (request: FlashQueueRequest) => {
    if (request.status !== 'flashing') return;

    setStoppingLiveRequestId(request.id);
    try {
      await flashQueueAPI.stopLiveSession(request.id);
      emitFlashSerialViewStop(request.id);
      showToast('Stopped the live serial session. Returning to workspace...', 'success');

      const projectTarget = request.project_name ? `/workspace/${request.project_name}` : '/workspace';
      navigate(projectTarget);
    } catch (error: any) {
      showToast(error.response?.data?.error || error.message || 'Unable to stop the live session.', 'error');
    } finally {
      setStoppingLiveRequestId(null);
    }
  };

  const detailRequest = useMemo(() => {
    if (selectedRequest) return selectedRequest;
    if (selectedRequestId == null) return null;
    return requests.find((request) => request.id === selectedRequestId) || null;
  }, [requests, selectedRequest, selectedRequestId]);

  const serialPanelText = useMemo(() => {
    if (liveSerialLog) return liveSerialLog;
    return detailRequest?.serial_log || '';
  }, [detailRequest?.serial_log, liveSerialLog]);

  const showLiveSerialBadge =
    !!detailRequest &&
    !!activeRequest &&
    detailRequest.id === activeRequest.id &&
    activeRequest.status === 'flashing' &&
    serialLiveState === 'running';

  return (
    <div
      style={{
        padding: 20,
        color: 'var(--vscode-text-main)',
        display: 'grid',
        gap: 16,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0 }}>Flash History</h1>
          <div style={{ color: 'var(--vscode-text-muted)', marginTop: 6 }}>
            REST restores active state and stored serial output. Websocket only adds live deltas.
          </div>
        </div>
        <label style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--vscode-text-muted)' }}>Filter</span>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as 'all' | FlashRequestStatus)}
            style={{
              background: 'var(--vscode-bg-sidebar)',
              color: 'var(--vscode-text-main)',
              border: '1px solid var(--vscode-border)',
              borderRadius: 6,
              padding: '8px 10px',
              minWidth: 150,
            }}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      </div>

      <div
        style={{
          border: '1px solid var(--vscode-border)',
          borderRadius: 10,
          padding: 16,
          background: 'var(--vscode-bg-panel)',
          display: 'grid',
          gap: 10,
        }}
      >
        <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--vscode-text-muted)' }}>
          Active Request
        </div>
            {activeRequest ? (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ display: 'grid', gap: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <strong>{activeRequest.tag_name}</strong>
                <span style={badgeStyle(activeRequest.status)}>{activeRequest.status}</span>
              </div>
              <div style={{ color: 'var(--vscode-text-muted)', fontSize: 13 }}>
                {activeRequest.board_type} • {activeRequest.firmware_name || activeRequest.firmware_path}
              </div>
              {activeRequest.status === 'waiting' && activeRequest.queue_position ? (
                <div style={{ color: 'var(--vscode-text-muted)', fontSize: 13 }}>
                  Queue position: {activeRequest.queue_position}
                </div>
              ) : null}
            </div>
            {activeRequest.status === 'waiting' ? (
              <button
                type="button"
                onClick={() => handleCancel(activeRequest)}
                disabled={cancellingRequestId === activeRequest.id}
                style={{
                  padding: '10px 14px',
                  borderRadius: 8,
                  border: '1px solid #b91c1c',
                  background: '#b91c1c',
                  color: '#fff',
                  cursor: cancellingRequestId === activeRequest.id ? 'not-allowed' : 'pointer',
                  opacity: cancellingRequestId === activeRequest.id ? 0.6 : 1,
                }}
              >
                {cancellingRequestId === activeRequest.id ? 'Cancelling...' : 'Cancel request'}
              </button>
            ) : isViewingActiveSerial ? (
              <button
                type="button"
                onClick={() => handleStopLiveSession(activeRequest)}
                disabled={stoppingLiveRequestId === activeRequest.id}
                style={{
                  padding: '10px 14px',
                  borderRadius: 8,
                  border: '1px solid #b91c1c',
                  background: '#b91c1c',
                  color: '#fff',
                  cursor: stoppingLiveRequestId === activeRequest.id ? 'not-allowed' : 'pointer',
                  opacity: stoppingLiveRequestId === activeRequest.id ? 0.6 : 1,
                }}
              >
                {stoppingLiveRequestId === activeRequest.id ? 'Stopping live session...' : 'Stop live session'}
              </button>
            ) : null}
          </div>
        ) : (
          <div style={{ color: 'var(--vscode-text-muted)' }}>There is no waiting or flashing request right now.</div>
        )}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(320px, 420px) minmax(0, 1fr)',
          gap: 16,
          alignItems: 'start',
        }}
      >
        <div
          style={{
            border: '1px solid var(--vscode-border)',
            borderRadius: 10,
            background: 'var(--vscode-bg-panel)',
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--vscode-border)', fontWeight: 700 }}>
            Queue-backed history
          </div>
          <div style={{ maxHeight: '66vh', overflowY: 'auto' }}>
            {loading ? (
              <div style={{ padding: 16, color: 'var(--vscode-text-muted)' }}>Loading history...</div>
            ) : requests.length === 0 ? (
              <div style={{ padding: 16, color: 'var(--vscode-text-muted)' }}>No requests match the current filter.</div>
            ) : (
              requests.map((request) => {
                const selected = request.id === selectedRequestId;
                return (
                  <button
                    key={request.id}
                    type="button"
                    onClick={() => setSelectedRequestId(request.id)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      border: 'none',
                      borderBottom: '1px solid var(--vscode-border)',
                      background: selected ? 'rgba(0, 122, 204, 0.16)' : 'transparent',
                      color: 'var(--vscode-text-main)',
                      padding: 16,
                      cursor: 'pointer',
                      display: 'grid',
                      gap: 8,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                      <strong>{request.tag_name}</strong>
                      <span style={badgeStyle(request.status)}>{request.status}</span>
                    </div>
                    <div style={{ color: 'var(--vscode-text-muted)', fontSize: 13 }}>
                      {request.board_type} • {request.firmware_name || request.firmware_path}
                    </div>
                    <div style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>
                      Created: {formatTime(request.created_at)}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        <div
          style={{
            border: '1px solid var(--vscode-border)',
            borderRadius: 10,
            background: 'var(--vscode-bg-panel)',
            minHeight: 320,
            display: 'grid',
            gridTemplateRows: 'auto 1fr',
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--vscode-border)', fontWeight: 700 }}>
            Request detail
          </div>
          <div style={{ padding: 16, overflowY: 'auto' }}>
            {detailLoading ? (
              <div style={{ color: 'var(--vscode-text-muted)' }}>Loading detail...</div>
            ) : detailRequest ? (
              <div style={{ display: 'grid', gap: 16 }}>
                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                    <strong style={{ fontSize: 18 }}>{detailRequest.tag_name}</strong>
                    <span style={badgeStyle(detailRequest.status)}>{detailRequest.status}</span>
                  </div>
                  <div style={{ color: 'var(--vscode-text-muted)', fontSize: 14 }}>
                    Board: {detailRequest.board_type}
                  </div>
                  <div style={{ color: 'var(--vscode-text-muted)', fontSize: 14 }}>
                    Baud: {detailRequest.baud_rate || 115200}
                  </div>
                  <div style={{ color: 'var(--vscode-text-muted)', fontSize: 14 }}>
                    Firmware: {detailRequest.firmware_name || detailRequest.firmware_path}
                  </div>
                  <div style={{ color: 'var(--vscode-text-muted)', fontSize: 14 }}>
                    Project: {detailRequest.project_name || 'Unknown'}
                  </div>
                  <div style={{ color: 'var(--vscode-text-muted)', fontSize: 14 }}>
                    Created: {formatTime(detailRequest.created_at)}
                  </div>
                  <div style={{ color: 'var(--vscode-text-muted)', fontSize: 14 }}>
                    Started: {formatTime(detailRequest.started_at)}
                  </div>
                  <div style={{ color: 'var(--vscode-text-muted)', fontSize: 14 }}>
                    Completed: {formatTime(detailRequest.completed_at)}
                  </div>
                  {detailRequest.status === 'waiting' && detailRequest.queue_position ? (
                    <div style={{ color: 'var(--vscode-text-muted)', fontSize: 14 }}>
                      Queue position: {detailRequest.queue_position}
                    </div>
                  ) : null}
                </div>

                {detailRequest.status === 'waiting' ? (
                  <div>
                    <button
                      type="button"
                      onClick={() => handleCancel(detailRequest)}
                      disabled={cancellingRequestId === detailRequest.id}
                      style={{
                        padding: '10px 14px',
                        borderRadius: 8,
                        border: '1px solid #b91c1c',
                        background: '#b91c1c',
                        color: '#fff',
                        cursor: cancellingRequestId === detailRequest.id ? 'not-allowed' : 'pointer',
                        opacity: cancellingRequestId === detailRequest.id ? 0.6 : 1,
                      }}
                    >
                      {cancellingRequestId === detailRequest.id ? 'Cancelling...' : 'Cancel waiting request'}
                    </button>
                  </div>
                ) : null}

                {isViewingActiveSerial ? (
                  <div style={{ display: 'grid', gap: 8 }}>
                    <button
                      type="button"
                      onClick={() => handleStopLiveSession(detailRequest)}
                      disabled={stoppingLiveRequestId === detailRequest.id}
                      style={{
                        padding: '10px 14px',
                        borderRadius: 8,
                        border: '1px solid #b91c1c',
                        background: '#b91c1c',
                        color: '#fff',
                        cursor: stoppingLiveRequestId === detailRequest.id ? 'not-allowed' : 'pointer',
                        opacity: stoppingLiveRequestId === detailRequest.id ? 0.6 : 1,
                        fontWeight: 700,
                      }}
                    >
                      {stoppingLiveRequestId === detailRequest.id ? 'Stopping live session...' : 'Stop live session'}
                    </button>
                    <div style={{ color: 'var(--vscode-text-muted)', fontSize: 13 }}>
                      Stop the active live serial session now, preserve the captured serial output, and release the device lock cleanly.
                    </div>
                  </div>
                ) : null}

                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--vscode-text-muted)' }}>
                    Flash Log
                  </div>
                  <pre
                    style={{
                      margin: 0,
                      padding: 14,
                      borderRadius: 8,
                      background: '#0b1220',
                      color: '#dbeafe',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      minHeight: 180,
                      border: '1px solid rgba(148, 163, 184, 0.2)',
                    }}
                  >
                    {detailRequest.log_output || 'No flash log stored for this request yet.'}
                  </pre>
                </div>

                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                    <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--vscode-text-muted)' }}>
                      Serial Output
                    </div>
                    {showLiveSerialBadge && (
                      <span
                        style={{
                          padding: '4px 10px',
                          borderRadius: 999,
                          background: 'rgba(59, 130, 246, 0.18)',
                          color: '#93c5fd',
                          fontSize: 12,
                          fontWeight: 700,
                        }}
                      >
                        Live
                      </span>
                    )}
                  </div>
                  <pre
                    style={{
                      margin: 0,
                      padding: 14,
                      borderRadius: 8,
                      background: '#05111f',
                      color: '#c4f1ff',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      minHeight: 180,
                      border: '1px solid rgba(96, 165, 250, 0.2)',
                    }}
                  >
                    {serialPanelText || 'No serial output captured for this request yet.'}
                  </pre>
                  {liveSessionNotice && (
                    <div style={{ color: '#93c5fd', fontSize: 13 }}>
                      {liveSessionNotice}
                    </div>
                  )}
                  {detailRequest.id === activeRequest?.id && activeRequest.status === 'flashing' && serialLiveState !== 'finished' && (
                    <div style={{ color: 'var(--vscode-text-muted)', fontSize: 13 }}>
                      Keeping the live view open will extend serial monitoring after the default 60-second hold.
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div style={{ color: 'var(--vscode-text-muted)' }}>Select a request from the list to inspect its logs.</div>
            )}
          </div>
        </div>
      </div>

      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </div>
  );
};
