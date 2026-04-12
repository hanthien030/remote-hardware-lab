import React, { useCallback, useEffect, useState } from 'react';
import { useBlocker, useNavigate, useParams } from 'react-router-dom';
import { CodeEditor, type CompileEditorMarker } from '../components/CodeEditor';
import { CompilePanel, type CompileSavedArtifact } from '../components/CompilePanel';
import { FileTree } from '../components/FileTree';
import { FlashDialog } from '../components/FlashDialog';
import { ToastContainer } from '../components/ToastContainer';
import { flashQueueAPI, type FlashQueueRequest } from '../api/flashQueue';
import { workspaceAPI } from '../api/workspace';
import { useDeviceSocket } from '../hooks/useDeviceSocket';
import { useToast } from '../hooks/useToast';
import { useAuthStore } from '../store/authStore';
import '../styles/DeviceDetail.css';

export const ProjectWorkspace: React.FC = () => {
  const { projectName } = useParams<{ projectName: string }>();
  const navigate = useNavigate();
  const { user, token } = useAuthStore();

  const [projects, setProjects] = useState<any[]>([]);
  const [openFiles, setOpenFiles] = useState<string[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [fileContents, setFileContents] = useState<Record<string, string>>({});
  const [dirtyFiles, setDirtyFiles] = useState<Record<string, boolean>>({});
  const [compileMarkers, setCompileMarkers] = useState<Record<string, CompileEditorMarker[]>>({});
  const [fileLoading, setFileLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showCompileOnly, setShowCompileOnly] = useState(false);
  const [showFlashDialog, setShowFlashDialog] = useState(false);
  const [selectedBoard, setSelectedBoard] = useState<string>(
    () => localStorage.getItem('rhl_selected_board') || 'esp32'
  );
  const [lastCompileArtifact, setLastCompileArtifact] = useState<CompileSavedArtifact | null>(null);
  const [activeRequest, setActiveRequest] = useState<FlashQueueRequest | null>(null);
  const [activeRequestLoading, setActiveRequestLoading] = useState(false);
  const [cancellingActiveRequest, setCancellingActiveRequest] = useState(false);

  const { toasts, showToast, removeToast } = useToast();
  const { onFlashDone, onFlashTaskUpdate } = useDeviceSocket();

  const isDirty = Object.values(dirtyFiles).some(Boolean);

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty && currentLocation.pathname !== nextLocation.pathname
  );

  useEffect(() => {
    if (blocker.state === 'blocked') {
      if (window.confirm('You have unsaved files. Leave this workspace?')) {
        blocker.proceed();
      } else {
        blocker.reset();
      }
    }
  }, [blocker]);

  const fetchProjects = useCallback(async () => {
    try {
      const response = await workspaceAPI.listProjects();
      setProjects(response.data.projects);
    } catch {
      // Keep page usable even if project refresh fails.
    }
  }, []);

  const fetchActiveRequest = useCallback(async () => {
    if (!token) {
      setActiveRequest(null);
      return;
    }

    setActiveRequestLoading(true);
    try {
      const response = await flashQueueAPI.getActiveRequest();
      setActiveRequest(response.data.request);
    } catch {
      setActiveRequest(null);
    } finally {
      setActiveRequestLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!projectName) return;

    setOpenFiles([]);
    setActiveFile(null);
    setFileContents({});
    setDirtyFiles({});
    setCompileMarkers({});
    setLastCompileArtifact(null);
    fetchProjects();
    fetchActiveRequest();
  }, [fetchActiveRequest, fetchProjects, projectName]);

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!Object.values(dirtyFiles).some(Boolean)) return;
      event.preventDefault();
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [dirtyFiles]);

  useEffect(() => {
    if (!token || !user?.username) return undefined;

    const refreshForCurrentUser = (eventUser?: string) => {
      if (eventUser === user.username) {
        fetchActiveRequest();
      }
    };

    const unsubTaskUpdate = onFlashTaskUpdate((event) => refreshForCurrentUser(event.user));
    const unsubFlashDone = onFlashDone((event) => refreshForCurrentUser(event.user));

    return () => {
      unsubTaskUpdate();
      unsubFlashDone();
    };
  }, [fetchActiveRequest, onFlashDone, onFlashTaskUpdate, token, user?.username]);

  const loadFile = async (filename: string) => {
    if (!projectName) return;

    setFileLoading(true);
    try {
      const response = await workspaceAPI.readFile(projectName, filename);
      setFileContents((prev) => ({ ...prev, [filename]: response.data.content }));
      setDirtyFiles((prev) => ({ ...prev, [filename]: false }));
    } catch (error: any) {
      showToast(`Cannot load ${filename}: ${error.response?.data?.error || error.message}`, 'error');
    } finally {
      setFileLoading(false);
    }
  };

  useEffect(() => {
    const handleSaveShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 's') {
        event.preventDefault();
        event.stopPropagation();
        if (activeFile) {
          saveFile(activeFile, fileContents[activeFile] || '');
        }
      }
    };

    window.addEventListener('keydown', handleSaveShortcut);
    return () => window.removeEventListener('keydown', handleSaveShortcut);
  }, [activeFile, fileContents, projectName]);

  const saveFile = async (filename: string, content: string) => {
    if (!projectName || !filename) return;

    setSaving(true);
    try {
      await workspaceAPI.saveFile(projectName, filename, content);
      setDirtyFiles((prev) => ({ ...prev, [filename]: false }));
    } catch (error: any) {
      showToast(`Auto-save failed: ${error.response?.data?.error || error.message}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleFileSelect = (filename: string) => {
    if (!openFiles.includes(filename)) {
      setOpenFiles((prev) => [...prev, filename]);
      loadFile(filename);
    }
    setActiveFile(filename);
  };

  const handleFileRenamed = (oldPath: string, newPath: string) => {
    setOpenFiles((prev) => prev.map((file) => {
      if (file === oldPath) return newPath;
      if (file.startsWith(`${oldPath}/`)) return file.replace(oldPath, newPath);
      return file;
    }));

    setFileContents((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((key) => {
        if (key === oldPath) {
          next[newPath] = next[key];
          delete next[key];
        } else if (key.startsWith(`${oldPath}/`)) {
          next[key.replace(oldPath, newPath)] = next[key];
          delete next[key];
        }
      });
      return next;
    });

    setDirtyFiles((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((key) => {
        if (key === oldPath) {
          next[newPath] = next[key];
          delete next[key];
        } else if (key.startsWith(`${oldPath}/`)) {
          next[key.replace(oldPath, newPath)] = next[key];
          delete next[key];
        }
      });
      return next;
    });

    if (activeFile === oldPath) {
      setActiveFile(newPath);
    } else if (activeFile && activeFile.startsWith(`${oldPath}/`)) {
      setActiveFile(activeFile.replace(oldPath, newPath));
    }
  };

  const closeTab = (filename: string) => {
    if (dirtyFiles[filename]) {
      const confirmed = window.confirm(`File ${filename} has unsaved changes. Close it anyway?`);
      if (!confirmed) return;
    }

    setOpenFiles((prev) => {
      const nextFiles = prev.filter((file) => file !== filename);
      if (activeFile === filename) {
        if (nextFiles.length > 0) {
          const currentIndex = prev.indexOf(filename);
          const nextIndex = Math.max(0, currentIndex - 1);
          setActiveFile(nextFiles[nextIndex]);
        } else {
          setActiveFile(null);
        }
      }
      return nextFiles;
    });

    setFileContents((prev) => {
      const next = { ...prev };
      delete next[filename];
      return next;
    });

    setDirtyFiles((prev) => {
      const next = { ...prev };
      delete next[filename];
      return next;
    });
  };

  const handleCompileSaved = useCallback((artifact: CompileSavedArtifact) => {
    setLastCompileArtifact(artifact);
    showToast(`Compile succeeded. Saved artifact: ${artifact.path}`, 'success');
  }, [showToast]);

  const handleCancelActiveRequest = useCallback(async () => {
    if (!activeRequest || activeRequest.status !== 'waiting') return;

    setCancellingActiveRequest(true);
    try {
      await flashQueueAPI.cancelRequest(activeRequest.id);
      showToast('Cancelled the waiting flash request.', 'success');
      await fetchActiveRequest();
    } catch (error: any) {
      try {
        const verification = await flashQueueAPI.verifyCancelOutcome(activeRequest.id);
        if (verification.cancelled) {
          setActiveRequest(verification.activeRequest);
          showToast('Cancelled the waiting flash request.', 'success');
          return;
        }
      } catch {
        // Fall through to the original error toast if recovery also fails.
      }

      showToast(error.response?.data?.error || error.message || 'Cannot cancel the flash request.', 'error');
    } finally {
      setCancellingActiveRequest(false);
    }
  }, [activeRequest, fetchActiveRequest, showToast]);

  const getEditorModelPath = (filename: string) =>
    `file:///workspace/${encodeURIComponent(projectName || 'project')}/${filename
      .split('/')
      .map(encodeURIComponent)
      .join('/')}`;

  const activeStatusLabel =
    activeRequest?.status === 'waiting'
      ? 'waiting'
      : activeRequest?.status === 'flashing'
        ? 'flashing'
        : activeRequest?.status || null;
  const hasActiveRequest = Boolean(activeRequest);
  const isWaitingRequest = activeRequest?.status === 'waiting';
  const isFlashingRequest = activeRequest?.status === 'flashing';
  const boardSupportsQueueFlash = selectedBoard === 'esp32' || selectedBoard === 'esp8266';
  const compiledArtifactMatchesBoard = Boolean(
    lastCompileArtifact?.path && lastCompileArtifact.board === selectedBoard
  );
  const hasCompileArtifactReady = Boolean(lastCompileArtifact?.path) && compiledArtifactMatchesBoard;
  const isCompileOnlyBoard = hasCompileArtifactReady && !boardSupportsQueueFlash;
  const canOpenFlashDialog = hasCompileArtifactReady && boardSupportsQueueFlash && !hasActiveRequest;
  const workspaceActionLabel = hasActiveRequest ? '⬛ HỦY' : '⚡ Nạp';
  const workspaceActionDisabled = activeRequestLoading
    || cancellingActiveRequest
    || isFlashingRequest
    || (!hasActiveRequest && !canOpenFlashDialog);
  const workspaceActionTitle = hasActiveRequest
    ? isWaitingRequest
      ? 'Cancel the current waiting flash request'
      : 'The request is already flashing. Open /history to follow progress'
    : !compiledArtifactMatchesBoard
      ? `Compile successfully for ${selectedBoard} before sending a flash request`
    : isCompileOnlyBoard
      ? 'Arduino Uno compile is ready, but flashing will be added later via avrdude'
    : hasCompileArtifactReady
      ? 'Send the compiled firmware into the flash queue'
      : 'Compile successfully before sending a flash request';
  const workspaceActionStyle: React.CSSProperties = hasActiveRequest
    ? {
        background: workspaceActionDisabled
          ? 'rgba(185, 28, 28, 0.42)'
          : 'linear-gradient(135deg, #ef4444 0%, #b91c1c 100%)',
        border: '1px solid',
        borderColor: workspaceActionDisabled ? 'rgba(239, 68, 68, 0.32)' : '#ef4444',
        color: '#fff5f5',
        boxShadow: workspaceActionDisabled ? 'none' : '0 10px 24px rgba(185, 28, 28, 0.22)',
        opacity: workspaceActionDisabled ? 0.72 : 1,
        cursor: workspaceActionDisabled ? 'not-allowed' : 'pointer',
      }
    : {
        background: canOpenFlashDialog
          ? 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)'
          : 'rgba(148, 163, 184, 0.24)',
        border: '1px solid',
        borderColor: canOpenFlashDialog ? '#60a5fa' : 'rgba(148, 163, 184, 0.35)',
        color: canOpenFlashDialog ? '#eff6ff' : 'rgba(255, 255, 255, 0.72)',
        boxShadow: canOpenFlashDialog ? '0 10px 24px rgba(37, 99, 235, 0.22)' : 'none',
        opacity: canOpenFlashDialog ? 1 : 0.7,
        cursor: canOpenFlashDialog ? 'pointer' : 'not-allowed',
      };

  return (
    <div className="device-detail-page">
      <div className="detail-header">
        <button className="btn-back" onClick={() => navigate('/workspace')}>{"<-"} Workspace</button>
        <h1>Project: {projectName}</h1>
        <div className="header-save-indicator" style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
          <select
            value={projectName}
            onChange={(event) => navigate(`/workspace/${event.target.value}`)}
            className="dropdown-select"
          >
            {projects.map((project) => (
              <option key={project.name} value={project.name}>{project.name}</option>
            ))}
          </select>

          {saving && <span className="save-indicator saving">Saving...</span>}
          {!saving && activeFile && dirtyFiles[activeFile] && <span className="save-indicator dirty">Unsaved</span>}
          {!saving && activeFile && Object.keys(dirtyFiles).length > 0 && !dirtyFiles[activeFile] && (
            <span className="save-indicator saved">Saved</span>
          )}
        </div>
      </div>

      <div className="detail-container">
        <div className="detail-sidebar">
          <div
            style={{
              border: '1px solid var(--vscode-border)',
              borderRadius: 8,
              padding: 12,
              background: 'var(--vscode-bg-panel)',
              display: 'grid',
              gap: 8,
              marginBottom: 12,
            }}
          >
            <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--vscode-text-muted)' }}>
              Queue Flash
            </div>
            {activeRequestLoading ? (
              <div style={{ color: 'var(--vscode-text-muted)', fontSize: 13 }}>Syncing active request from backend...</div>
            ) : activeRequest ? (
              <>
                <div style={{ color: 'var(--vscode-text-main)', fontWeight: 700 }}>
                  {activeRequest.status === 'waiting' ? 'Waiting to flash' : 'Flashing in progress'}
                </div>
                <div style={{ color: 'var(--vscode-text-muted)', fontSize: 13 }}>
                  {activeRequest.tag_name} • {activeRequest.board_type}
                </div>
                {activeRequest.status === 'waiting' && activeRequest.queue_position ? (
                  <div style={{ color: 'var(--vscode-text-muted)', fontSize: 13 }}>
                    Queue position: {activeRequest.queue_position}
                  </div>
                ) : null}
                <button
                  type="button"
                  className="btn-back"
                  style={{ width: '100%', marginTop: 4 }}
                  onClick={() => navigate('/history')}
                >
                  Open History
                </button>
              </>
            ) : (
              <div style={{ color: 'var(--vscode-text-muted)', fontSize: 13 }}>
                No active flash request. Compile successfully before opening the queue flash dialog.
              </div>
            )}
          </div>

          <div className="quick-stats" style={{ marginTop: 'auto' }}>
            <div className="stat">
              <span className="stat-label">File</span>
              <span className="stat-value">{activeFile}</span>
            </div>
          </div>
        </div>

        <div className="detail-main" style={{ display: 'flex', flexDirection: 'row', flex: 1 }}>
          {projectName && (
            <FileTree
              projectName={projectName}
              activeFile={activeFile || ''}
              onFileSelect={handleFileSelect}
              onFileRenamed={handleFileRenamed}
              dirtyFiles={dirtyFiles}
            />
          )}

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            {activeFile ? (
              <div className="editor-section" style={{ flex: 1 }}>
                <div
                  className="editor-tab-bar"
                  style={{
                    display: 'flex',
                    background: 'var(--vscode-bg-tabbar)',
                    overflowX: 'auto',
                    borderBottom: '1px solid var(--vscode-border)',
                  }}
                >
                  {openFiles.map((file) => {
                    const isActive = activeFile === file;
                    return (
                      <div
                        key={file}
                        onClick={() => setActiveFile(file)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '8px 12px',
                          cursor: 'pointer',
                          background: isActive ? 'var(--vscode-bg-editor)' : 'transparent',
                          color: isActive ? 'var(--vscode-text-main)' : 'var(--vscode-text-muted)',
                          borderTop: isActive ? '1px solid var(--vscode-accent)' : '1px solid transparent',
                          borderRight: '1px solid var(--vscode-border)',
                          fontSize: 13,
                        }}
                      >
                        <span
                          style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                          title={file}
                        >
                          {file.split('/').pop()}
                        </span>
                        {dirtyFiles[file] && <span style={{ color: 'var(--vscode-text-main)' }}>*</span>}
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            closeTab(file);
                          }}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: 'inherit',
                            cursor: 'pointer',
                            fontSize: 14,
                            padding: '0 4px',
                            lineHeight: 1,
                          }}
                        >
                          x
                        </button>
                      </div>
                    );
                  })}
                </div>
                {fileLoading && <div style={{ padding: 10, color: 'var(--vscode-text-muted)' }}>Loading {activeFile}...</div>}

                <div style={{ flex: 1, position: 'relative' }}>
                  {openFiles.map((file) => (
                    fileContents[file] !== undefined && (
                      <div
                        key={file}
                        style={{
                          position: 'absolute',
                          top: 0,
                          left: 0,
                          right: 0,
                          bottom: 0,
                          display: file === activeFile ? 'block' : 'none',
                        }}
                      >
                        <CodeEditor
                          language={file.endsWith('.py') ? 'python' : 'cpp'}
                          defaultValue={fileContents[file]}
                          path={getEditorModelPath(file)}
                          markers={compileMarkers[file] || []}
                          onChange={(value) => {
                            const safeValue = value ?? '';
                            setFileContents((prev) => ({ ...prev, [file]: safeValue }));
                            setDirtyFiles((prev) => ({ ...prev, [file]: true }));
                          }}
                          height="calc(100vh - 280px)"
                        />
                      </div>
                    )
                  ))}
                </div>

                <div className="editor-footer" style={{ display: 'grid', gap: 10 }}>
                  {activeRequest && (
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: 12,
                        flexWrap: 'wrap',
                        padding: '10px 12px',
                        borderRadius: 8,
                        border: '1px solid rgba(245, 158, 11, 0.35)',
                        background: 'rgba(245, 158, 11, 0.12)',
                        color: 'var(--vscode-text-main)',
                      }}
                    >
                      <div style={{ display: 'grid', gap: 4 }}>
                        <div style={{ fontSize: 12, textTransform: 'uppercase', fontWeight: 700, color: '#fbbf24' }}>
                          Active flash request
                        </div>
                        <div style={{ fontSize: 13 }}>
                          Flash is currently tied to an active backend request with status{' '}
                          <strong>{activeStatusLabel}</strong>. Use the footer action below or open <strong>/history</strong> to track it.
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        <button type="button" className="btn-back" onClick={() => navigate('/history')}>
                          Open /history
                        </button>
                      </div>
                    </div>
                  )}

                  {!activeRequest && isCompileOnlyBoard && (
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: 12,
                        flexWrap: 'wrap',
                        padding: '10px 12px',
                        borderRadius: 8,
                        border: '1px solid rgba(59, 130, 246, 0.35)',
                        background: 'rgba(59, 130, 246, 0.1)',
                        color: 'var(--vscode-text-main)',
                      }}
                    >
                      <div style={{ display: 'grid', gap: 4 }}>
                        <div style={{ fontSize: 12, textTransform: 'uppercase', fontWeight: 700, color: '#93c5fd' }}>
                          Compile-only board
                        </div>
                        <div style={{ fontSize: 13 }}>
                          Arduino Uno compile succeeded and saved <strong>{lastCompileArtifact?.path}</strong>. Flashing stays disabled in this batch and will be added later via avrdude.
                        </div>
                      </div>
                    </div>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                    <div className="editor-info">C++ syntax for ESP32/Arduino</div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <select
                        value={selectedBoard}
                        onChange={(event) => {
                          setSelectedBoard(event.target.value);
                          localStorage.setItem('rhl_selected_board', event.target.value);
                        }}
                        style={{
                          background: 'var(--vscode-bg-sidebar)',
                          color: 'var(--vscode-text-main)',
                          border: '1px solid var(--vscode-border)',
                          borderRadius: 4,
                          padding: '4px 8px',
                          fontSize: 12,
                          cursor: 'pointer',
                        }}
                      >
                        <option value="esp32">ESP32</option>
                        <option value="esp8266">ESP8266</option>
                        <option value="arduino_uno">Arduino Uno</option>
                      </select>

                      <button
                        className="btn-compile"
                        disabled={!projectName}
                        title={`Compile full project (${selectedBoard}) without a device`}
                        onClick={async () => {
                          if (!projectName) return;
                          const saves = Object.entries(dirtyFiles)
                            .filter(([, dirty]) => dirty)
                            .map(([file]) =>
                              workspaceAPI
                                .saveFile(projectName, file, fileContents[file] || '')
                                .then(() => setDirtyFiles((prev) => ({ ...prev, [file]: false })))
                            );
                          await Promise.all(saves);
                          setShowCompileOnly(true);
                        }}
                        style={{ background: '#1e7e34', borderColor: '#1e7e34' }}
                      >
                        Compile
                      </button>

                      <button
                        type="button"
                        className="btn-compile"
                        disabled={workspaceActionDisabled}
                        title={workspaceActionTitle}
                        onClick={() => {
                          if (isWaitingRequest) {
                            void handleCancelActiveRequest();
                            return;
                          }
                          if (!canOpenFlashDialog) return;
                          setShowFlashDialog(true);
                        }}
                        style={{
                          padding: '6px 14px',
                          borderRadius: 6,
                          fontWeight: 700,
                          ...workspaceActionStyle,
                        }}
                      >
                        {cancellingActiveRequest ? 'Đang hủy...' : workspaceActionLabel}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div
                className="editor-section"
                style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--vscode-text-muted)' }}
              >
                <h2>No file is open</h2>
              </div>
            )}
          </div>
        </div>
      </div>

      {projectName && (
        <CompilePanel
          projectName={projectName}
          board={selectedBoard}
          isOpen={showCompileOnly}
          onClose={() => setShowCompileOnly(false)}
          onMarkersChange={setCompileMarkers}
          onSaved={handleCompileSaved}
          token={token || ''}
        />
      )}

      {projectName && lastCompileArtifact?.path && canOpenFlashDialog && (
        <FlashDialog
          isOpen={showFlashDialog}
          projectName={projectName}
          firmwarePath={lastCompileArtifact.path}
          initialBoard={selectedBoard}
          onClose={() => setShowFlashDialog(false)}
          onQueued={(request, board) => {
            setSelectedBoard(board);
            localStorage.setItem('rhl_selected_board', board);
            setActiveRequest(request);
            setShowFlashDialog(false);
            showToast('Queued the flash request. Opening history...', 'success');
            navigate('/history');
          }}
        />
      )}

      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </div>
  );
};
