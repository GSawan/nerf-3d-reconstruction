'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  session_count: number;
}

export default function DashboardPage() {
  const router = useRouter();
  const { user, accessToken, isAuthenticated, clearAuth } = useAuthStore();

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login');
      return;
    }
    fetchProjects();
  }, [isAuthenticated]);

  const fetchProjects = async () => {
    try {
      const res = await fetch(`${API}/api/v1/projects/`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.status === 401) { clearAuth(); router.push('/login'); return; }
      const data = await res.json();
      setProjects(Array.isArray(data) ? data : []);
    } catch {
      setError('Failed to load projects');
    } finally {
      setLoading(false);
    }
  };

  const createProject = async () => {
    if (!newProjectName.trim()) return;
    setCreating(true);
    try {
      const res = await fetch(`${API}/api/v1/projects/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ name: newProjectName.trim() }),
      });
      if (!res.ok) throw new Error('Failed to create project');
      setNewProjectName('');
      setShowCreateForm(false);
      await fetchProjects();
    } catch {
      setError('Failed to create project');
    } finally {
      setCreating(false);
    }
  };

  const handleLogout = () => {
    clearAuth();
    router.push('/login');
  };

  return (
    <div className="min-h-screen bg-[#080808] text-white" style={{ fontFamily: 'monospace' }}>
      {/* Background grid */}
      <div className="fixed inset-0 opacity-[0.02] pointer-events-none"
        style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,0.5) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.5) 1px,transparent 1px)', backgroundSize: '40px 40px' }} />

      {/* Header */}
      <header className="border-b border-white/10 bg-[#0d0d0d] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-6 h-6 border border-white/20 rotate-45 flex items-center justify-center">
            <div className="w-2 h-2 bg-white/80 rotate-45" />
          </div>
          <span className="text-sm font-bold tracking-[0.3em] uppercase">Neo3D</span>
          <span className="text-white/20 text-xs">/ Dashboard</span>
        </div>
        <div className="flex items-center gap-6">
          <button
            onClick={() => router.push('/upload')}
            className="px-4 py-2 bg-white text-black text-xs font-bold tracking-widest uppercase hover:bg-white/90 transition-all"
          >
            + New Reconstruction
          </button>
          <div className="text-xs text-white/40">
            {user?.display_name || user?.email}
          </div>
          <button
            onClick={handleLogout}
            className="text-xs text-white/30 hover:text-white/60 transition-colors"
          >
            Sign Out
          </button>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-5xl mx-auto px-6 py-10">

        {/* Welcome */}
        <div className="mb-10">
          <h1 className="text-2xl font-bold tracking-widest uppercase mb-1">
            Welcome back, <span className="text-white/60">{user?.display_name || 'User'}</span>
          </h1>
          <p className="text-white/25 text-xs tracking-wider">Manage your 3D reconstruction projects below.</p>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-4 mb-10">
          {[
            { label: 'Total Projects', value: projects.length },
            { label: 'Reconstructions', value: projects.reduce((a, p) => a + (p.session_count || 0), 0) },
            { label: 'Status', value: 'Active' },
          ].map(({ label, value }) => (
            <div key={label} className="border border-white/10 p-5 bg-[#0d0d0d]">
              <p className="text-[10px] text-white/30 tracking-widest uppercase mb-2">{label}</p>
              <p className="text-2xl font-light text-white">{value}</p>
            </div>
          ))}
        </div>

        {/* Projects */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs text-white/40 tracking-widest uppercase">Your Projects</h2>
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="text-xs border border-white/20 px-3 py-1.5 text-white/50 hover:text-white hover:border-white/40 transition-all"
          >
            {showCreateForm ? '× Cancel' : '+ New Project'}
          </button>
        </div>

        {/* Create form */}
        {showCreateForm && (
          <div className="border border-white/10 bg-[#0d0d0d] p-5 mb-4 flex gap-3">
            <input
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && createProject()}
              placeholder="Project name..."
              autoFocus
              className="flex-1 bg-transparent border border-white/15 px-4 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/40"
            />
            <button
              onClick={createProject}
              disabled={creating || !newProjectName.trim()}
              className="px-5 py-2 bg-white text-black text-xs font-bold tracking-widest uppercase hover:bg-white/90 disabled:opacity-40"
            >
              {creating ? 'Creating...' : 'Create'}
            </button>
          </div>
        )}

        {error && (
          <div className="border border-red-800/40 bg-red-950/20 px-4 py-3 mb-4">
            <p className="text-red-400 text-xs">{error}</p>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20 text-white/20 text-xs tracking-widest animate-pulse">
            LOADING PROJECTS...
          </div>
        ) : projects.length === 0 ? (
          <div className="border border-white/5 bg-[#0d0d0d] p-12 text-center">
            <p className="text-4xl mb-4 opacity-20">◈</p>
            <p className="text-white/30 text-xs tracking-widest mb-2">NO PROJECTS YET</p>
            <p className="text-white/15 text-[10px]">Create a project or start a reconstruction directly.</p>
            <button
              onClick={() => router.push('/upload')}
              className="mt-6 px-6 py-2.5 bg-white text-black text-xs font-bold tracking-widest uppercase hover:bg-white/90 transition-all"
            >
              Start First Reconstruction →
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {projects.map((project) => (
              <div
                key={project.id}
                className="border border-white/10 bg-[#0d0d0d] p-5 hover:border-white/20 transition-all cursor-pointer flex items-center justify-between group"
                onClick={() => router.push('/upload')}
              >
                <div>
                  <p className="text-sm text-white font-medium mb-1">{project.name}</p>
                  <p className="text-[10px] text-white/25">
                    {project.session_count} reconstruction{project.session_count !== 1 ? 's' : ''} ·{' '}
                    {new Date(project.updated_at).toLocaleDateString()}
                  </p>
                </div>
                <span className="text-white/20 group-hover:text-white/50 transition-colors text-xs tracking-widest">→</span>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
