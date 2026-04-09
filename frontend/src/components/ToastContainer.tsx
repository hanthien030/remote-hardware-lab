// src/components/ToastContainer.tsx
import React from 'react';
import { Toast } from '../hooks/useToast';

interface ToastContainerProps {
  toasts: Toast[];
  onRemove: (id: number) => void;
}

const COLORS: Record<string, { bg: string; border: string; icon: string }> = {
  success: { bg: '#f0fdf4', border: '#16a34a', icon: '✅' },
  error:   { bg: '#fef2f2', border: '#dc2626', icon: '❌' },
  warning: { bg: '#fffbeb', border: '#d97706', icon: '⚠️' },
  info:    { bg: '#eff6ff', border: '#2563eb', icon: 'ℹ️' },
};

export const ToastContainer: React.FC<ToastContainerProps> = ({ toasts, onRemove }) => {
  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        maxWidth: 360,
        pointerEvents: 'none',
      }}
    >
      {toasts.map((toast) => {
        const style = COLORS[toast.type] || COLORS.info;
        return (
          <div
            key={toast.id}
            onClick={() => onRemove(toast.id)}
            style={{
              background: style.bg,
              border: `1px solid ${style.border}`,
              borderLeft: `4px solid ${style.border}`,
              borderRadius: 8,
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
              cursor: 'pointer',
              pointerEvents: 'all',
              animation: 'slideIn 0.2s ease',
              fontFamily: 'inherit',
              fontSize: 14,
              fontWeight: 500,
              color: '#1f2937',
              wordBreak: 'break-word',
            }}
          >
            <span style={{ fontSize: 16, flexShrink: 0 }}>{style.icon}</span>
            <span style={{ flex: 1 }}>{toast.message}</span>
            <span style={{ color: '#9ca3af', fontSize: 18, flexShrink: 0 }}>×</span>
          </div>
        );
      })}
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>
    </div>
  );
};
