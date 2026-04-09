import React from 'react';
import { Sidebar } from './Sidebar';

interface SidebarLayoutProps {
  children: React.ReactNode;
}

export const SidebarLayout: React.FC<SidebarLayoutProps> = ({ children }) => {
  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden' }}>
      <Sidebar />
      <div style={{ flex: 1, overflowY: 'auto', backgroundColor: 'var(--vscode-bg-editor)' }}>
        {children}
      </div>
    </div>
  );
};
