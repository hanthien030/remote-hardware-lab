// src/api/workspace.ts
// Workspace API client — quản lý file code per-user per-device

import axios from 'axios';
import { useAuthStore } from '../store/authStore';

const getHeaders = () => {
  const token = useAuthStore.getState().token;
  return { Authorization: `Bearer ${token}` };
};

export interface WorkspaceFile {
  filename: string;
  size_bytes?: number;
  updated_at?: number;  // Unix timestamp
  type?: 'file' | 'folder';
}

export const workspaceAPI = {
  // ─── Project System ───
  listProjects: () =>
    axios.get<{ ok: boolean; projects: { name: string }[] }>(
      '/api/workspace/projects',
      { headers: getHeaders() }
    ),

  createProject: (projectName: string) =>
    axios.post<{ ok: boolean; project: { name: string } }>(
      '/api/workspace/projects',
      { project_name: projectName },
      { headers: getHeaders() }
    ),

  deleteProject: (projectName: string) =>
    axios.delete<{ ok: boolean; message: string }>(
      `/api/workspace/projects/${encodeURIComponent(projectName)}`,
      { headers: getHeaders() }
    ),

  // ─── File System ───
  listFiles: (projectName: string) =>
    axios.get<{ ok: boolean; files: WorkspaceFile[]; workspace: string }>(
      `/api/workspace/${encodeURIComponent(projectName)}/files`,
      { headers: getHeaders() }
    ),

  readFile: (projectName: string, filename: string) =>
    axios.get<{ ok: boolean; filename: string; content: string }>(
      `/api/workspace/${encodeURIComponent(projectName)}/files/${encodeURIComponent(filename)}`,
      { headers: getHeaders() }
    ),

  saveFile: (projectName: string, filename: string, content: string) =>
    axios.put<{ ok: boolean; filename: string; size_bytes: number }>(
      `/api/workspace/${encodeURIComponent(projectName)}/files/${encodeURIComponent(filename)}`,
      { content },
      { headers: getHeaders() }
    ),

  createFile: (projectName: string, filename: string, content = '') =>
    axios.post<{ ok: boolean; filename: string }>(
      `/api/workspace/${encodeURIComponent(projectName)}/files`,
      { filename, content },
      { headers: getHeaders() }
    ),

  deleteFile: (projectName: string, filename: string) =>
    axios.delete<{ ok: boolean; message: string }>(
      `/api/workspace/${encodeURIComponent(projectName)}/files/${encodeURIComponent(filename)}`,
      { headers: getHeaders() }
    ),

  renameFile: (projectName: string, oldName: string, newName: string) =>
    axios.patch<{ ok: boolean; old_filename: string; new_filename: string }>(
      `/api/workspace/${encodeURIComponent(projectName)}/files/${encodeURIComponent(oldName)}/rename`,
      { new_filename: newName },
      { headers: getHeaders() }
    ),

  createFolder: (projectName: string, folderPath: string) =>
    axios.post<{ ok: boolean; folder_path: string }>(
      `/api/workspace/${encodeURIComponent(projectName)}/folders`,
      { folder_path: folderPath },
      { headers: getHeaders() }
    ),

  copyItem: (projectName: string, oldName: string, newName: string) =>
    axios.post<{ ok: boolean; old_filename: string; new_filename: string }>(
      `/api/workspace/${encodeURIComponent(projectName)}/files/${encodeURIComponent(oldName)}/copy`,
      { new_filename: newName },
      { headers: getHeaders() }
    ),
};
