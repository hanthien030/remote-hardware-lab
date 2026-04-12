// src/components/CompilePanel.tsx
// SSE compile-only panel (3B-3) - no device and no lock required

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { workspaceAPI } from '../api/workspace';
import type { CompileEditorMarker } from './CodeEditor';

interface LogLine {
  stage: 'info' | 'compile' | 'done' | 'saved' | 'error';
  log?: string;
  error?: string;
  size_bytes?: number;
  path?: string;
  artifact_ext?: string;
  flash_tool_hint?: string;
}

export interface CompileSavedArtifact {
  path: string;
  artifactExt?: string;
  flashToolHint?: string;
  board: string;
}

interface CompilePanelProps {
  projectName: string;
  board: string;
  isOpen: boolean;
  onClose: () => void;
  onSaved?: (artifact: CompileSavedArtifact) => void;
  onMarkersChange?: (markersByFile: Record<string, CompileEditorMarker[]>) => void;
  token: string;
}

interface RunConfig {
  projectName: string;
  board: string;
  token: string;
}

const DIAGNOSTIC_WITH_COLUMN_RE = /^(.*?):(\d+):(\d+):\s*(fatal error|error|warning|note):\s*(.+)$/i;
const DIAGNOSTIC_LINE_ONLY_RE = /^(.*?):(\d+):\s*(fatal error|error|warning|note):\s*(.+)$/i;
const RENAME_INFO_RE = /^\s*\[(?:cpp→ino|ino)\]\s+(.+?)\s+→\s+(.+?)(?:\s+\(|$)/;
const FILE_INFO_RE = /^\s*\[(?:cpp|hdr|ino)\]\s+(.+)$/;

const normalizeFileRef = (value: string) =>
  value.trim().replace(/^["']|["']$/g, '').replace(/\\/g, '/');

const getBasename = (value: string) => {
  const normalized = normalizeFileRef(value);
  const parts = normalized.split('/').filter(Boolean);
  return parts[parts.length - 1] || normalized;
};

const addMarker = (
  markersByFile: Record<string, CompileEditorMarker[]>,
  filename: string,
  marker: CompileEditorMarker
) => {
  if (!markersByFile[filename]) {
    markersByFile[filename] = [];
  }
  markersByFile[filename].push(marker);
};

const resolveWorkspaceFile = (
  diagnosticPath: string,
  workspaceFiles: string[],
  basenameToFiles: Map<string, string[]>,
  renameTargetsToSources: Map<string, string>,
  compilerFileNames: Set<string>
) => {
  const normalized = normalizeFileRef(diagnosticPath);
  const basename = getBasename(normalized);
  const renamed = renameTargetsToSources.get(normalized) || renameTargetsToSources.get(basename);
  if (renamed) {
    return renamed;
  }

  const exactMatches = workspaceFiles.filter(file => {
    const normalizedFile = normalizeFileRef(file);
    return normalized === normalizedFile || normalized.endsWith(`/${normalizedFile}`);
  });
  if (exactMatches.length > 0) {
    const longestLength = Math.max(...exactMatches.map(file => file.length));
    const bestMatches = exactMatches.filter(file => file.length === longestLength);
    if (bestMatches.length === 1) {
      return bestMatches[0];
    }
  }

  if (!compilerFileNames.has(basename)) {
    return null;
  }

  const basenameMatches = basenameToFiles.get(basename) || [];
  return basenameMatches.length === 1 ? basenameMatches[0] : null;
};

const parseDiagnosticMarker = (line: string) => {
  const withColumn = line.match(DIAGNOSTIC_WITH_COLUMN_RE);
  const withoutColumn = line.match(DIAGNOSTIC_LINE_ONLY_RE);
  const match = withColumn || withoutColumn;
  if (!match) return null;

  const filePath = match[1];
  const lineNumber = Number(match[2]);
  const severity = (withColumn ? match[4] : match[3]).toLowerCase();
  const message = withColumn ? match[5] : match[4];
  const columnNumber = withColumn ? Number(match[3]) : 1;

  if ((severity !== 'error' && severity !== 'fatal error') || !Number.isFinite(lineNumber) || lineNumber < 1) {
    return null;
  }

  const safeColumn = Number.isFinite(columnNumber) && columnNumber > 0 ? columnNumber : 1;

  return {
    filePath,
    marker: {
      startLineNumber: lineNumber,
      startColumn: safeColumn,
      endLineNumber: lineNumber,
      endColumn: safeColumn + 1,
      message: `${severity}: ${message}`,
    },
  };
};

export const CompilePanel: React.FC<CompilePanelProps> = ({
  projectName,
  board,
  isOpen,
  onClose,
  onSaved,
  onMarkersChange,
  token,
}) => {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const logRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const onSavedRef = useRef(onSaved);
  const onMarkersChangeRef = useRef(onMarkersChange);
  const latestConfigRef = useRef<RunConfig>({ projectName, board, token });
  const runSequenceRef = useRef(0);
  const activeRunIdRef = useRef<number | null>(null);

  useEffect(() => {
    onSavedRef.current = onSaved;
  }, [onSaved]);

  useEffect(() => {
    onMarkersChangeRef.current = onMarkersChange;
  }, [onMarkersChange]);

  useEffect(() => {
    latestConfigRef.current = { projectName, board, token };
  }, [projectName, board, token]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [lines]);

  const isRunActive = useCallback((runId: number) => activeRunIdRef.current === runId, []);

  const finishRun = useCallback((runId: number) => {
    if (activeRunIdRef.current !== runId) return;
    activeRunIdRef.current = null;
    abortRef.current = null;
  }, []);

  const startCompileRun = useCallback(async (runId: number, runConfig: RunConfig) => {
    setLines([]);
    setStatus('running');
    onMarkersChangeRef.current?.({});

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    activeRunIdRef.current = runId;

    let workspaceFiles: string[] = [];

    try {
      const filesResponse = await workspaceAPI.listFiles(runConfig.projectName);
      if (!isRunActive(runId)) return;

      workspaceFiles = (filesResponse.data.files || [])
        .filter(file => file.type !== 'folder')
        .map(file => file.filename);
    } catch {
      if (!isRunActive(runId)) return;
      workspaceFiles = [];
    }

    const basenameToFiles = new Map<string, string[]>();
    for (const file of workspaceFiles) {
      const basename = getBasename(file);
      const existing = basenameToFiles.get(basename) || [];
      existing.push(file);
      basenameToFiles.set(basename, existing);
    }

    const renameTargetsToSources = new Map<string, string>();
    const compilerFileNames = new Set<string>();
    const markersByFile: Record<string, CompileEditorMarker[]> = {};

    try {
      const response = await fetch(`/api/workspace/${encodeURIComponent(runConfig.projectName)}/compile`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${runConfig.token}`,
        },
        body: JSON.stringify({ board: runConfig.board }),
        signal: controller.signal,
      });

      if (!isRunActive(runId)) return;

      if (!response.ok) {
        const err = await response.json().catch(() => ({ error: response.statusText }));
        if (!isRunActive(runId)) return;

        setLines([{ stage: 'error', error: err.error || 'Request failed' }]);
        setStatus('error');
        finishRun(runId);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        setLines([{ stage: 'error', error: 'Compile stream was empty.' }]);
        setStatus('error');
        finishRun(runId);
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      const processSsePart = (part: string) => {
        const dataLine = part.split('\n').find(line => line.startsWith('data: '));
        if (!dataLine) return;

        try {
          const event: LogLine = JSON.parse(dataLine.slice(6));
          if (!isRunActive(runId)) return;

          setLines(prev => [...prev, event]);

          if (event.stage === 'info' && event.log) {
            const renameMatch = event.log.match(RENAME_INFO_RE);
            if (renameMatch) {
              const sourceName = renameMatch[1].trim();
              const targetName = renameMatch[2].trim();
              const sourceFile = resolveWorkspaceFile(
                sourceName,
                workspaceFiles,
                basenameToFiles,
                new Map(),
                new Set([getBasename(sourceName)])
              );
              const targetBasename = getBasename(targetName);
              compilerFileNames.add(targetBasename);
              if (sourceFile) {
                renameTargetsToSources.set(targetBasename, sourceFile);
                renameTargetsToSources.set(normalizeFileRef(targetName), sourceFile);
              }
              return;
            }

            const fileInfoMatch = event.log.match(FILE_INFO_RE);
            if (fileInfoMatch) {
              compilerFileNames.add(getBasename(fileInfoMatch[1]));
            }
          } else if (event.stage === 'compile' && event.log) {
            const parsedDiagnostic = parseDiagnosticMarker(event.log);
            if (parsedDiagnostic) {
              const resolvedFile = resolveWorkspaceFile(
                parsedDiagnostic.filePath,
                workspaceFiles,
                basenameToFiles,
                renameTargetsToSources,
                compilerFileNames
              );
              if (resolvedFile) {
                addMarker(markersByFile, resolvedFile, parsedDiagnostic.marker);
              }
            }
          }

          if (event.stage === 'done') {
            if (!isRunActive(runId)) return;
            setStatus('done');
            onMarkersChangeRef.current?.({});
          } else if (event.stage === 'saved' && event.path) {
            if (!isRunActive(runId)) return;
            onSavedRef.current?.({
              path: event.path,
              artifactExt: event.artifact_ext,
              flashToolHint: event.flash_tool_hint,
              board: runConfig.board,
            });
          } else if (event.stage === 'error') {
            if (!isRunActive(runId)) return;
            setStatus('error');
            onMarkersChangeRef.current?.(markersByFile);
            finishRun(runId);
          }
        } catch {
          // Ignore malformed SSE chunks and continue current run.
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (!isRunActive(runId)) return;
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          if (!isRunActive(runId)) return;
          processSsePart(part);
        }
      }

      buffer += decoder.decode();
      if (buffer.trim()) {
        processSsePart(buffer);
      }

      if (!isRunActive(runId)) return;

      setStatus(prev => (prev === 'running' ? 'done' : prev));
      onMarkersChangeRef.current?.({});
      finishRun(runId);
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        return;
      }
      if (!isRunActive(runId)) return;

      setLines(prev => [...prev, { stage: 'error', error: String(err) }]);
      setStatus('error');
      finishRun(runId);
    }
  }, [finishRun, isRunActive]);

  useEffect(() => {
    if (!isOpen) return;

    const runId = runSequenceRef.current + 1;
    runSequenceRef.current = runId;

    const runConfig = latestConfigRef.current;
    void startCompileRun(runId, runConfig);

    return () => {
      if (activeRunIdRef.current === runId) {
        activeRunIdRef.current = null;
        abortRef.current?.abort();
        abortRef.current = null;
      }
    };
  }, [isOpen, startCompileRun]);

  const handleStop = () => {
    if (activeRunIdRef.current === null) return;

    activeRunIdRef.current = null;
    abortRef.current?.abort();
    abortRef.current = null;
    setStatus('error');
    setLines(prev => {
      const lastLine = prev[prev.length - 1];
      if (lastLine?.stage === 'error' && lastLine.error === 'Compilation cancelled by user.') {
        return prev;
      }
      return [...prev, { stage: 'error', error: 'Compilation cancelled by user.' }];
    });
  };

  const handleRetry = () => {
    const runId = runSequenceRef.current + 1;
    runSequenceRef.current = runId;
    void startCompileRun(runId, latestConfigRef.current);
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: 720, maxWidth: '95vw',
          background: 'var(--vscode-bg-sidebar)',
          border: '1px solid var(--vscode-border)',
          borderRadius: 6,
          display: 'flex', flexDirection: 'column',
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          maxHeight: '80vh',
        }}
      >
        <div
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 16px',
            borderBottom: '1px solid var(--vscode-border)',
            background: 'var(--vscode-bg-tabbar)',
            borderRadius: '6px 6px 0 0',
          }}
        >
          <span style={{ color: 'var(--vscode-text-main)', fontWeight: 600, fontSize: 14 }}>
            {status === 'running' && '⏳ Đang biên dịch...'}
            {status === 'done' && '✅ Biên dịch thành công!'}
            {status === 'error' && '❌ Biên dịch thất bại'}
            {status === 'idle' && '🔨 Biên dịch'}
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            {status === 'running' && (
              <button
                onClick={handleStop}
                style={{
                  background: '#c0392b', color: '#fff', border: 'none',
                  borderRadius: 4, padding: '4px 12px', cursor: 'pointer', fontSize: 12,
                }}
              >
                ⬛ Dừng
              </button>
            )}
            <button
              onClick={onClose}
              style={{
                background: 'none', border: 'none',
                color: 'var(--vscode-text-muted)', fontSize: 18, cursor: 'pointer',
                lineHeight: 1,
              }}
            >
              ×
            </button>
          </div>
        </div>

        <div
          ref={logRef}
          style={{
            flex: 1, overflowY: 'auto',
            padding: '12px 16px',
            fontFamily: "'Fira Code', 'Consolas', monospace",
            fontSize: 12,
            lineHeight: 1.7,
            background: 'var(--vscode-bg-editor)',
            minHeight: 300,
          }}
        >
          {lines.map((line, i) => (
            <div
              key={i}
              style={{
                color: line.stage === 'error' ? '#f87171'
                  : line.stage === 'done' ? '#4ade80'
                  : line.stage === 'saved' ? '#60a5fa'
                  : line.stage === 'info' ? '#a3a3a3'
                  : '#d4d4d4',
                wordBreak: 'break-word',
                whiteSpace: 'pre-wrap',
              }}
            >
              <span style={{ opacity: 0.5, marginRight: 8, userSelect: 'none' }}>
                {line.stage === 'error' ? '[ERR] '
                  : line.stage === 'done' ? '[OK]  '
                  : line.stage === 'saved' ? '[BIN] '
                  : line.stage === 'info' ? '[INF] '
                  : '[LOG] '}
              </span>
              {line.log || line.error}
            </div>
          ))}
          {status === 'running' && (
            <div style={{ color: '#a3a3a3' }}>
              <span style={{ opacity: 0.5 }}>[...] </span>
              <span style={{ animation: 'pulse 1s infinite' }}>▋</span>
            </div>
          )}
        </div>

        <div
          style={{
            padding: '10px 16px',
            borderTop: '1px solid var(--vscode-border)',
            display: 'flex', justifyContent: 'flex-end', gap: 8,
            background: 'var(--vscode-bg-tabbar)',
            borderRadius: '0 0 6px 6px',
          }}
        >
          {status === 'error' && (
            <button
              onClick={handleRetry}
              style={{
                background: 'var(--vscode-accent)', color: '#fff', border: 'none',
                borderRadius: 4, padding: '6px 16px', cursor: 'pointer', fontSize: 13,
              }}
            >
              🔄 Thử lại
            </button>
          )}
          {(status === 'done' || status === 'error') && (
            <button
              onClick={onClose}
              style={{
                background: 'var(--vscode-bg-sidebar)', color: 'var(--vscode-text-main)',
                border: '1px solid var(--vscode-border)',
                borderRadius: 4, padding: '6px 16px', cursor: 'pointer', fontSize: 13,
              }}
            >
              Đóng
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
