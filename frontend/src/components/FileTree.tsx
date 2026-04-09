// src/components/FileTree.tsx
import React, { useState, useRef, useEffect, useMemo } from 'react';
import { workspaceAPI, WorkspaceFile } from '../api/workspace';
import './FileTree.css';

interface FileTreeProps {
  projectName: string;
  activeFile: string;
  onFileSelect: (filename: string) => void;
  onFileRenamed?: (oldPath: string, newPath: string) => void;
  onFilesChange?: () => void;
  dirtyFiles?: Record<string, boolean>;
}

interface TreeNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  children: TreeNode[];
}

const ICON_MAP: Record<string, string> = {
  cpp: '📄', c: '📄', h: '📋', hpp: '📋', ino: '🔧', txt: '📝', py: '🐍', json: '⚙️', md: '📖'
};
const getIcon = (filename: string) => ICON_MAP[filename.split('.').pop()?.toLowerCase() || ''] || '📄';

export const FileTree: React.FC<FileTreeProps> = ({ projectName, activeFile, onFileSelect, onFileRenamed, onFilesChange, dirtyFiles = {} }) => {
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  const [expanded, setExpanded] = useState<Set<string>>(new Set([''])); // '' is root
  const [selectedPath, setSelectedPath] = useState<string>('');
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  
  const [creating, setCreating] = useState<{ type: 'file' | 'folder'; parent: string } | null>(null);
  const [createValue, setCreateValue] = useState('');
  
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; path: string; type: 'file' | 'folder' | 'root' } | null>(null);
  const [clipboard, setClipboard] = useState<{ action: 'copy' | 'cut'; path: string } | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchFiles();
  }, [projectName]);

  useEffect(() => {
    if (renaming || creating) inputRef.current?.focus();
  }, [renaming, creating]);

  const tree = useMemo(() => {
    const root: TreeNode = { name: 'root', path: '', type: 'folder', children: [] };
    
    // Sort files so folders come first, then alphabetically
    const sorted = [...files].sort((a, b) => {
      if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
      return a.filename.localeCompare(b.filename);
    });

    for (const file of sorted) {
      const parts = file.filename.split('/');
      let current = root;
      let pathSoFar = '';
      
      for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        pathSoFar = pathSoFar ? `${pathSoFar}/${part}` : part;
        const isLast = i === parts.length - 1;
        
        let node = current.children.find(c => c.name === part);
        if (!node) {
          node = {
            name: part,
            path: pathSoFar,
            type: isLast ? (file.type || 'file') : 'folder',
            children: []
          };
          current.children.push(node);
        }
        current = node;
      }
    }
    return root.children;
  }, [files]);

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const res = await workspaceAPI.listFiles(projectName);
      setFiles(res.data.files);
    } catch (e: any) {
      setError(e.response?.data?.error || 'Load failed');
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (path: string, force?: boolean) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (force === true) next.add(path);
      else if (force === false) next.delete(path);
      else if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleCreate = async () => {
    if (!creating || !createValue.trim()) { setCreating(null); return; }
    const fullPath = creating.parent ? `${creating.parent}/${createValue.trim()}` : createValue.trim();
    try {
      if (creating.type === 'folder') {
        await workspaceAPI.createFolder(projectName, fullPath);
        toggleExpand(creating.parent, true);
      } else {
        await workspaceAPI.createFile(projectName, fullPath);
        toggleExpand(creating.parent, true);
        onFileSelect(fullPath);
      }
      setCreating(null);
      setCreateValue('');
      await fetchFiles();
      onFilesChange?.();
    } catch (e: any) {
      alert(e.response?.data?.error || 'Create failed');
    }
  };

  const handleRename = async () => {
    if (!renaming || !renameValue.trim()) { setRenaming(null); return; }
    
    if (Object.keys(dirtyFiles).some(k => (k === renaming || k.startsWith(renaming + '/')) && dirtyFiles[k])) {
      alert('Vui lòng lưu file trước khi đổi tên!');
      setRenaming(null);
      return;
    }
    
    const parentPath = renaming.substring(0, renaming.lastIndexOf('/'));
    const newPath = parentPath ? `${parentPath}/${renameValue.trim()}` : renameValue.trim();
    
    if (newPath === renaming) { setRenaming(null); return; }
    
    try {
      await workspaceAPI.renameFile(projectName, renaming, newPath);
      setRenaming(null);
      if (onFileRenamed) onFileRenamed(renaming, newPath);
      else {
        if (activeFile === renaming) onFileSelect(newPath);
        if (activeFile.startsWith(renaming + '/')) onFileSelect(activeFile.replace(renaming, newPath));
      }
      await fetchFiles();
      onFilesChange?.();
    } catch (e: any) {
      alert(e.response?.data?.error || 'Rename failed');
      setRenaming(null);
    }
  };

  const handleDelete = async (path: string) => {
    if (Object.keys(dirtyFiles).some(k => (k === path || k.startsWith(path + '/')) && dirtyFiles[k])) {
      alert('Vui lòng lưu file trước khi xóa!');
      return;
    }
    if (!window.confirm(`Delete "${path}"?`)) return;
    try {
      await workspaceAPI.deleteFile(projectName, path);
      if (activeFile === path || activeFile.startsWith(path + '/')) onFileSelect('');
      await fetchFiles();
      onFilesChange?.();
    } catch (e: any) {
      alert(e.response?.data?.error || 'Delete failed');
    }
  };

  const handlePaste = async (targetFolder: string) => {
    if (!clipboard) return;
    const basename = clipboard.path.split('/').pop();
    const targetPath = targetFolder ? `${targetFolder}/${basename}` : basename!;
    
    try {
      if (clipboard.action === 'copy') {
        await workspaceAPI.copyItem(projectName, clipboard.path, targetPath);
      } else {
        if (Object.keys(dirtyFiles).some(k => (k === clipboard.path || k.startsWith(clipboard.path + '/')) && dirtyFiles[k])) {
          alert('Vui lòng lưu file trước khi di chuyển!');
          return;
        }
        await workspaceAPI.renameFile(projectName, clipboard.path, targetPath);
        setClipboard(null);
        if (onFileRenamed) onFileRenamed(clipboard.path, targetPath);
        else {
          if (activeFile === clipboard.path) onFileSelect(targetPath);
          if (activeFile.startsWith(clipboard.path + '/')) onFileSelect(activeFile.replace(clipboard.path, targetPath));
        }
      }
      await fetchFiles();
      onFilesChange?.();
    } catch(e: any) {
      alert(e.response?.data?.error || 'Paste failed');
    }
  };

  // --- Keyboard & Context Menu ---
  useEffect(() => {
    const handleGlobalClick = () => setContextMenu(null);
    window.addEventListener('click', handleGlobalClick);
    return () => window.removeEventListener('click', handleGlobalClick);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (renaming || creating) return;
    if (!selectedPath) return;
    
    if (e.key === 'F2') {
      setRenaming(selectedPath);
      setRenameValue(selectedPath.split('/').pop() || '');
    }
    if (e.key === 'Delete') {
      handleDelete(selectedPath);
    }
  };

  // --- Drag and Drop ---
  const onDragStart = (e: React.DragEvent, path: string) => {
    e.dataTransfer.setData('path', path);
    e.stopPropagation();
  };

  const onDrop = async (e: React.DragEvent, targetFolder: string) => {
    e.preventDefault();
    e.stopPropagation();
    const sourcePath = e.dataTransfer.getData('path');
    if (!sourcePath || sourcePath === targetFolder) return;
    
    const basename = sourcePath.split('/').pop();
    const targetPath = targetFolder ? `${targetFolder}/${basename}` : basename!;
    if (sourcePath === targetPath) return;

    if (Object.keys(dirtyFiles).some(k => (k === sourcePath || k.startsWith(sourcePath + '/')) && dirtyFiles[k])) {
      alert('Vui lòng lưu file trước khi di chuyển!');
      return;
    }

    try {
      await workspaceAPI.renameFile(projectName, sourcePath, targetPath);
      await fetchFiles();
      if (onFileRenamed) onFileRenamed(sourcePath, targetPath);
      else if (activeFile === sourcePath || activeFile.startsWith(sourcePath + '/')) {
        onFileSelect(activeFile.replace(sourcePath, targetPath));
      }
      onFilesChange?.();
    } catch(e:any) {
      alert(e.response?.data?.error || "Move failed");
    }
  };

  const onContextMenu = (e: React.MouseEvent, path: string, type: 'file' | 'folder' | 'root') => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, path, type });
    setSelectedPath(path);
  };

  // --- Render ---
  const renderNode = (node: TreeNode, depth: number = 0) => {
    const isExpanded = expanded.has(node.path);
    const isEditing = renaming === node.path;
    const isSelected = selectedPath === node.path || activeFile === node.path;
    
    return (
      <div key={node.path} className="tree-node-container" style={{ paddingLeft: depth * 12 }}>
        <div 
          className={`tree-node ${isSelected ? 'selected' : ''}`}
          onClick={(e) => {
            e.stopPropagation();
            setSelectedPath(node.path);
            if (node.type === 'folder') toggleExpand(node.path);
            else onFileSelect(node.path);
          }}
          onContextMenu={(e) => onContextMenu(e, node.path, node.type)}
          draggable={!isEditing}
          onDragStart={(e) => onDragStart(e, node.path)}
          onDragOver={(e) => { e.preventDefault(); if (node.type === 'folder') e.currentTarget.classList.add('drag-over'); }}
          onDragLeave={(e) => { e.currentTarget.classList.remove('drag-over'); }}
          onDrop={(e) => { e.currentTarget.classList.remove('drag-over'); if (node.type === 'folder') onDrop(e, node.path); }}
        >
          {node.type === 'folder' && (
            <span className="folder-arrow">{isExpanded ? '▼' : '▶'}</span>
          )}
          {node.type === 'file' && <span className="file-icon">{getIcon(node.name)}</span>}
          
          {isEditing ? (
            <input 
              ref={inputRef}
              className="tree-input"
              value={renameValue}
              onChange={e => setRenameValue(e.target.value)}
              onBlur={handleRename}
              onKeyDown={e => { if(e.key==='Enter') handleRename(); if(e.key==='Escape') setRenaming(null); }}
              onClick={e=>e.stopPropagation()}
            />
          ) : (
            <span className="node-name">{node.name}</span>
          )}
        </div>
        
        {/* Children Render */}
        {node.type === 'folder' && isExpanded && (
          <div className="tree-children">
            {creating?.parent === node.path && (
               <div className="tree-node creating" style={{ paddingLeft: (depth+1) * 12 }}>
                 <span className="file-icon">{creating.type === 'folder' ? '📁' : '📄'}</span>
                 <input 
                   ref={inputRef} className="tree-input" value={createValue}
                   onChange={e=>setCreateValue(e.target.value)}
                   onBlur={handleCreate}
                   onKeyDown={e=>{ if(e.key==='Enter') handleCreate(); if(e.key==='Escape') setCreating(null); }}
                 />
               </div>
            )}
            {node.children.map(c => renderNode(c, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="file-tree" onKeyDown={handleKeyDown} tabIndex={0}
         onContextMenu={(e) => onContextMenu(e, '', 'root')}
         onDragOver={e=>e.preventDefault()} onDrop={e => onDrop(e, '')}>
      <div className="file-tree-header">
        <span className="file-tree-title">📁 EXPLORER</span>
        <div className="header-actions">
          <button onClick={() => { setCreating({type:'file', parent:''}); toggleExpand('', true); }} title="New File">📄</button>
          <button onClick={() => { setCreating({type:'folder', parent:''}); toggleExpand('', true); }} title="New Folder">📁</button>
        </div>
      </div>

      {loading && <div className="file-tree-loading">Loading...</div>}
      
      <div className="file-tree-content">
        {creating?.parent === '' && (
          <div className="tree-node creating">
            <span className="file-icon">{creating.type === 'folder' ? '📁' : '📄'}</span>
            <input 
              ref={inputRef} className="tree-input" value={createValue}
              onChange={e=>setCreateValue(e.target.value)}
              onBlur={handleCreate}
              onKeyDown={e=>{ if(e.key==='Enter') handleCreate(); if(e.key==='Escape') setCreating(null); }}
            />
          </div>
        )}
        {tree.map(node => renderNode(node, 0))}
      </div>

      {contextMenu && (
        <div 
          className="context-menu" 
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={e => e.stopPropagation()}
        >
          {(contextMenu.type === 'folder' || contextMenu.type === 'root') && (
            <>
              <button onClick={() => { setCreating({type:'file', parent:contextMenu.path}); toggleExpand(contextMenu.path, true); setContextMenu(null); }}>📄 New File</button>
              <button onClick={() => { setCreating({type:'folder', parent:contextMenu.path}); toggleExpand(contextMenu.path, true); setContextMenu(null); }}>📁 New Folder</button>
              {clipboard && <button onClick={() => { handlePaste(contextMenu.path); setContextMenu(null); }}>📋 Paste</button>}
              <hr/>
            </>
          )}
          {contextMenu.type !== 'root' && (
            <>
              {contextMenu.type === 'file' && <button onClick={() => { onFileSelect(contextMenu.path); setContextMenu(null); }}>👁️ Open</button>}
              <button onClick={() => { setClipboard({ action: 'copy', path: contextMenu.path }); setContextMenu(null); }}>📑 Copy</button>
              <button onClick={() => { setClipboard({ action: 'cut', path: contextMenu.path }); setContextMenu(null); }}>✂️ Cut</button>
              <button onClick={() => { setRenaming(contextMenu.path); setRenameValue(contextMenu.path.split('/').pop()||''); setContextMenu(null); }}>✏️ Rename</button>
              <button onClick={() => { handleDelete(contextMenu.path); setContextMenu(null); }} className="danger">🗑️ Delete</button>
            </>
          )}
        </div>
      )}
    </div>
  );
};
