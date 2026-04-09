// src/components/CompileLogPanel.tsx
// Hiển thị SSE log stream từ compile-flash endpoint

import React, { useEffect, useRef, useState } from 'react';
import './CompileLogPanel.css';

interface LogLine {
  stage: 'compile' | 'flash' | 'done' | 'error';
  log?: string;
  error?: string;
  bytes_written?: number;
}

interface CompileLogPanelProps {
  tagName: string;
  projectName?: string;
  filename: string;
  board?: string;
  isOpen: boolean;
  onClose: () => void;
  onDone?: (bytesWritten: number) => void;
  token: string;
}

export const CompileLogPanel: React.FC<CompileLogPanelProps> = ({
  tagName,
  projectName,
  filename,
  board = 'esp32',
  isOpen,
  onClose,
  onDone,
  token,
}) => {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const logRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    startStream();
    return () => { esRef.current?.close(); };
  }, [isOpen]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [lines]);

  const startStream = () => {
    setLines([]);
    setStatus('running');

    // EventSource doesn't support custom headers natively.
    // Use fetch + ReadableStream for SSE with auth.
    const url = `/api/hardware/compile-flash?tag_name=${encodeURIComponent(tagName)}&project_name=${encodeURIComponent(projectName || tagName)}&filename=${encodeURIComponent(filename)}&board=${board}`;

    fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    }).then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({ error: response.statusText }));
        setLines(prev => [...prev, { stage: 'error', error: err.error || 'Request failed' }]);
        setStatus('error');
        return;
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const dataLine = part.split('\n').find(l => l.startsWith('data: '));
          if (!dataLine) continue;
          try {
            const event: LogLine = JSON.parse(dataLine.slice(6));
            setLines(prev => [...prev, event]);
            if (event.stage === 'done') {
              setStatus('done');
              onDone?.(event.bytes_written || 0);
            } else if (event.stage === 'error') {
              setStatus('error');
            }
          } catch {/* skip malformed */ }
        }
      }
    }).catch(err => {
      setLines(prev => [...prev, { stage: 'error', error: String(err) }]);
      setStatus('error');
    });
  };

  if (!isOpen) return null;

  return (
    <div className="compile-panel-overlay" onClick={onClose}>
      <div className="compile-panel" onClick={e => e.stopPropagation()}>
        <div className="compile-panel-header">
          <span className="compile-panel-title">
            {status === 'running' && '⏳ Compiling & Flashing...'}
            {status === 'done' && '✅ Done!'}
            {status === 'error' && '❌ Failed'}
            {status === 'idle' && '🔨 Output'}
          </span>
          <button className="compile-panel-close" onClick={onClose}>×</button>
        </div>

        <div className="compile-panel-log" ref={logRef}>
          {lines.map((line, i) => (
            <div key={i} className={`log-line log-${line.stage}`}>
              {line.stage === 'compile' && <span className="log-badge compile">COMPILE</span>}
              {line.stage === 'flash'   && <span className="log-badge flash">FLASH</span>}
              {line.stage === 'done'    && <span className="log-badge done">DONE</span>}
              {line.stage === 'error'   && <span className="log-badge error">ERROR</span>}
              <span className="log-text">{line.log || line.error}</span>
            </div>
          ))}
          {status === 'running' && (
            <div className="log-line log-compile">
              <span className="log-badge compile">…</span>
              <span className="log-cursor">▋</span>
            </div>
          )}
        </div>

        <div className="compile-panel-footer">
          {status === 'error' && (
            <button className="compile-retry-btn" onClick={startStream}>🔄 Retry</button>
          )}
          {status === 'done' && (
            <button className="compile-close-btn" onClick={onClose}>Close</button>
          )}
        </div>
      </div>
    </div>
  );
};
