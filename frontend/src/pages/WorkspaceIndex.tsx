import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { workspaceAPI } from '../api/workspace';
import { useAuthStore } from '../store/authStore';

interface Project {
  name: string;
}

export const WorkspaceIndex: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetchProjects();
  }, []);

  const fetchProjects = async () => {
    try {
      setLoading(true);
      const res = await workspaceAPI.listProjects();
      setProjects(res.data.projects);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to load projects');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await workspaceAPI.createProject(newProjectName);
      setShowModal(false);
      setNewProjectName('');
      // Chuyển hướng ngay vào dự án mới
      navigate(`/workspace/${res.data.project.name}`);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to create project');
    }
  };

  const handleDeleteProject = async (projectName: string) => {
    if (!window.confirm(`Delete project "${projectName}"? This cannot be undone.`)) return;
    try {
      await workspaceAPI.deleteProject(projectName);
      fetchProjects();
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to delete project');
    }
  };

  return (
    <div style={{ padding: '20px 40px', color: 'var(--vscode-text-main)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h1>💻 Làm việc (Workspace)</h1>
        <button 
          className="btn-primary" 
          onClick={() => setShowModal(true)}
          style={{ padding: '10px 20px', fontSize: '16px' }}
        >
          + Tạo dự án mới
        </button>
      </div>

      {error && <div className="error-message" style={{ backgroundColor: 'var(--vscode-bg-panel)', color: 'var(--vscode-error)', border: '1px solid var(--vscode-error)', padding: 10, borderRadius: 4, marginBottom: 20 }}>{error}</div>}

      {loading ? (
        <p>Loading projects...</p>
      ) : projects.length === 0 ? (
        <div style={{ 
          textAlign: 'center', 
          padding: '60px 20px', 
          backgroundColor: 'var(--vscode-bg-panel)', 
          borderRadius: 8,
          border: '1px dashed var(--vscode-border)'
        }}>
          <h2>Chưa có dự án nào</h2>
          <p style={{ color: 'var(--vscode-text-muted)', marginTop: 10, marginBottom: 20 }}>Hãy tạo một dự án để bắt đầu viết code lập trình.</p>
          <button className="btn-primary" onClick={() => setShowModal(true)}>+ Tạo dự án mới</button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20 }}>
          {projects.map((p) => (
            <div 
              key={p.name} 
              style={{
                backgroundColor: 'var(--vscode-bg-panel)',
                padding: 20,
                borderRadius: 8,
                width: 250,
                border: '1px solid var(--vscode-border)',
                cursor: 'pointer',
                transition: 'transform 0.2s',
              }}
              onClick={() => navigate(`/workspace/${p.name}`)}
              onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-5px)'}
              onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}
            >
              <h3 style={{ margin: '0 0 15px 0', color: 'var(--vscode-accent)' }}>📁 {p.name}</h3>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button 
                  className="btn-danger" 
                  onClick={(e) => { e.stopPropagation(); handleDeleteProject(p.name); }}
                  style={{ padding: '6px 12px', fontSize: '12px' }}
                >
                  Xóa
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <div className="modal" style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, 
          backgroundColor: 'rgba(0,0,0,0.7)', display: 'flex', 
          alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }}>
          <div className="modal-content" style={{
            backgroundColor: 'var(--vscode-bg-editor)', padding: 30, borderRadius: 8, width: 400, border: '1px solid var(--vscode-border)'
          }}>
            <h2 style={{ marginTop: 0 }}>Dự án mới</h2>
            <form onSubmit={handleCreateProject}>
              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', marginBottom: 8, color: 'var(--vscode-text-muted)' }}>Tên dự án (không dấu, không cách):</label>
                <input
                  type="text"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  pattern="^[\w\-]+$"
                  title="Chỉ chứa chữ cái, số, gạch dưới và gạch ngang"
                  required
                  style={{
                    width: '100%', padding: '10px', borderRadius: 4, 
                    border: '1px solid var(--vscode-border)', backgroundColor: 'var(--vscode-bg-hover)', color: 'var(--vscode-text-main)'
                  }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)} style={{ backgroundColor: 'var(--vscode-bg-hover)', color: 'var(--vscode-text-main)' }}>Hủy</button>
                <button type="submit" className="btn-primary" style={{ backgroundColor: 'var(--vscode-accent)', color: 'white', fontWeight: 'bold' }}>Tạo</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
