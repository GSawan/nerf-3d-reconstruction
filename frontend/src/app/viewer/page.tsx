'use client';
import { useEffect, useRef, useState, Suspense } from 'react';
import { useRouter } from 'next/navigation';
import { useNeRFStore } from '@/store/nerfStore';
import { NeRFApi } from '@/lib/api';
import dynamic from 'next/dynamic';

// Dynamically import the 3D viewer (Three.js) — no SSR
const PLYViewer = dynamic(() => import('@/components/viewer/PLYViewer'), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-[#050505]">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-white/20 border-t-emerald-400 rounded-full animate-spin" />
        <p className="font-mono text-xs text-emerald-400/60 tracking-widest">LOADING VIEWER...</p>
      </div>
    </div>
  ),
});

// Use empty string so requests go through Next.js proxy (/api/* → backend)
// This avoids CORS and works in both dev and prod
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

const PHASE_LABELS: Record<string, string> = {
  queued: 'QUEUED — Waiting to start',
  colmap_features: '1/4 — Extracting Image Features',
  colmap_matching: '2/4 — Matching Features Across Images',
  colmap_sparse: '3/4 — Building 3D Structure (COLMAP)',
  exporting: '4/4 — Exporting 3D Model',
  completed: '✓ RECONSTRUCTION COMPLETE',
  failed: '✗ FAILED',
  idle: 'READY',
};

const PHASE_COLOR: Record<string, string> = {
  queued: 'text-yellow-400',
  colmap_features: 'text-blue-400',
  colmap_matching: 'text-indigo-400',
  colmap_sparse: 'text-purple-400',
  exporting: 'text-orange-400',
  completed: 'text-emerald-400',
  failed: 'text-red-400',
  idle: 'text-white/40',
};

const PHASE_PROGRESS: Record<string, number> = {
  queued: 0,
  colmap_features: 15,
  colmap_matching: 35,
  colmap_sparse: 65,
  exporting: 85,
  completed: 100,
  failed: 0,
};

export default function ViewerPage() {
  const router = useRouter();
  const { activeSessionId } = useNeRFStore();
  const logsEndRef = useRef<HTMLDivElement>(null);

  const [status, setStatus] = useState('idle');
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [modelUrl, setModelUrl] = useState<string | null>(null);
  const [pointCount, setPointCount] = useState(0);
  const [cameraCount, setCameraCount] = useState(0);
  const [isStarting, setIsStarting] = useState(false);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const isActive = ['queued', 'colmap_features', 'colmap_matching', 'colmap_sparse', 'exporting'].includes(status);
  const isCompleted = status === 'completed';
  const isFailed = status === 'failed';

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs.length]);

  // Poll status
  const poll = async () => {
    if (!activeSessionId) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/reconstruct/status/${activeSessionId}`);
      if (!res.ok) return;
      const data = await res.json();
      setStatus(data.status || 'idle');
      setProgress(data.progress ?? 0);
      setLogs(data.logs || []);
      setError(data.error || null);
      if (data.model_url) setModelUrl(data.model_url);
      if (data.point_count) setPointCount(data.point_count);
      if (data.camera_count) setCameraCount(data.camera_count);

      // Stop polling when done
      if (data.status === 'completed' || data.status === 'failed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      }
    } catch (e) {
      console.error('Poll error:', e);
    }
  };

  useEffect(() => {
    if (!activeSessionId) return;
    poll(); // Immediate first poll
    pollingRef.current = setInterval(poll, 2000);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [activeSessionId]);

  const handleStart = async () => {
    if (!activeSessionId || isStarting || isActive) return;
    setIsStarting(true);
    setError(null);
    setModelUrl(null);
    setStatus('queued');
    setProgress(0);
    setLogs([]);
    try {
      const res = await fetch(`${API_BASE}/api/v1/reconstruct/${activeSessionId}`, {
        method: 'POST',
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to start pipeline');
      }
      // Start polling
      if (pollingRef.current) clearInterval(pollingRef.current);
      pollingRef.current = setInterval(poll, 2000);
    } catch (e: any) {
      setError(e.message);
      setStatus('failed');
    } finally {
      setIsStarting(false);
    }
  };

  const displayProgress = isCompleted ? 100 : (isActive ? Math.max(progress, PHASE_PROGRESS[status] || 0) : progress);

  return (
    <div className="h-screen bg-[#0a0a0a] text-white flex flex-col overflow-hidden" style={{ fontFamily: 'monospace' }}>

      {/* ── Header ── */}
      <header className="border-b border-white/10 px-6 py-4 flex items-center justify-between shrink-0 bg-[#0d0d0d]">
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.push('/upload')}
            className="text-xs text-white/40 hover:text-white transition-colors border border-white/10 px-3 py-1.5 hover:border-white/30"
          >
            ← BACK
          </button>
          <div>
            <h1 className="text-sm font-bold tracking-[0.3em] uppercase text-white">NeRF 3D Reconstruction</h1>
            <p className="text-[10px] text-white/25 tracking-wider mt-0.5">{activeSessionId || 'no session'}</p>
          </div>
        </div>

        <button
          onClick={handleStart}
          disabled={!activeSessionId || isActive || isStarting}
          className={`px-5 py-2 text-xs font-bold tracking-[0.2em] uppercase transition-all disabled:cursor-not-allowed ${
            isCompleted
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 cursor-default'
              : isActive || isStarting
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30 cursor-wait animate-pulse'
              : 'bg-white text-black hover:bg-white/90 active:scale-95'
          }`}
        >
          {isStarting ? 'STARTING...' : isActive ? 'PROCESSING...' : isCompleted ? '✓ DONE' : 'START RECONSTRUCTION'}
        </button>
      </header>

      {/* ── Main Layout ── */}
      <div className="flex-1 grid grid-cols-5 min-h-0 divide-x divide-white/5">

        {/* ── Left Panel: Controls & Stats ── */}
        <div className="col-span-1 flex flex-col p-4 gap-4 overflow-y-auto bg-[#0d0d0d]">

          {/* Phase */}
          <div className="border border-white/10 p-4">
            <p className="text-[10px] text-white/30 tracking-widest uppercase mb-2">Phase</p>
            <p className={`text-xs font-bold leading-relaxed ${PHASE_COLOR[status] || 'text-white'} ${isActive ? 'animate-pulse' : ''}`}>
              {PHASE_LABELS[status] || status.toUpperCase()}
            </p>
          </div>

          {/* Progress Bar */}
          <div className="border border-white/10 p-4">
            <div className="flex justify-between text-[10px] text-white/30 mb-2">
              <span>PROGRESS</span>
              <span>{displayProgress}%</span>
            </div>
            <div className="w-full h-1 bg-white/5 overflow-hidden">
              <div
                className={`h-full transition-all duration-700 ease-out ${
                  isCompleted ? 'bg-emerald-400' : isFailed ? 'bg-red-500' : 'bg-blue-400'
                }`}
                style={{ width: `${displayProgress}%` }}
              />
            </div>
          </div>

          {/* Stats */}
          <div className="border border-white/10 p-4 space-y-3">
            <p className="text-[10px] text-white/30 tracking-widest uppercase border-b border-white/5 pb-2">Stats</p>
            <div>
              <p className="text-[10px] text-blue-400/60 uppercase mb-1">Cameras Registered</p>
              <p className="text-lg font-light text-blue-300">{cameraCount || '—'}</p>
            </div>
            <div>
              <p className="text-[10px] text-yellow-400/60 uppercase mb-1">Sparse 3D Points</p>
              <p className="text-lg font-light text-yellow-300">
                {pointCount > 0 ? pointCount.toLocaleString() : '—'}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-purple-400/60 uppercase mb-1">Output Format</p>
              <p className="text-xs font-light text-purple-300">PLY Point Cloud</p>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="border border-red-800/40 bg-red-950/30 p-4">
              <p className="text-[10px] font-bold text-red-400 uppercase tracking-widest mb-2">Error</p>
              <p className="text-red-300/80 text-[10px] leading-relaxed break-words">{error}</p>
            </div>
          )}

          {/* Download button */}
          {isCompleted && modelUrl && (
            <a
              href={`${API_BASE}${modelUrl}`}
              download="model.ply"
              className="block text-center border border-emerald-500/40 bg-emerald-950/30 text-emerald-400 text-xs py-3 px-4 hover:bg-emerald-950/60 transition-colors tracking-widest uppercase"
            >
              ↓ Download .PLY
            </a>
          )}
        </div>

        {/* ── Center: 3D VIEWER ── */}
        <div className="col-span-3 flex flex-col min-h-0 bg-[#050505]">
          <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between shrink-0">
            <p className="text-[10px] text-white/30 tracking-widest uppercase">3D Reconstruction Viewer</p>
            {isCompleted && modelUrl && (
              <span className="text-[10px] text-emerald-400 tracking-wider">● LIVE — Three.js PLY Renderer</span>
            )}
          </div>
          <div className="flex-1 min-h-0 relative">
            {isCompleted && modelUrl ? (
              <PLYViewer modelUrl={`${API_BASE}${modelUrl}`} />
            ) : (
              <div className="w-full h-full flex flex-col items-center justify-center gap-4">
                {isActive ? (
                  <>
                    {/* Animated reconstruction visualization */}
                    <div className="relative w-32 h-32">
                      <div className="absolute inset-0 border border-blue-500/20 rounded-full animate-ping" />
                      <div className="absolute inset-2 border border-blue-500/30 rounded-full animate-ping" style={{ animationDelay: '0.3s' }} />
                      <div className="absolute inset-4 border border-blue-500/40 rounded-full animate-ping" style={{ animationDelay: '0.6s' }} />
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="w-3 h-3 bg-blue-400 rounded-full animate-pulse" />
                      </div>
                    </div>
                    <p className="text-xs text-blue-400/60 tracking-widest animate-pulse">
                      BUILDING 3D MODEL...
                    </p>
                    <p className="text-[10px] text-white/20 tracking-wider">
                      {PHASE_LABELS[status] || status}
                    </p>
                  </>
                ) : isFailed ? (
                  <div className="text-center">
                    <p className="text-4xl mb-4">✗</p>
                    <p className="text-red-400 text-xs tracking-widest">RECONSTRUCTION FAILED</p>
                    <p className="text-white/20 text-[10px] mt-2">Check the error panel on the left</p>
                  </div>
                ) : (
                  <div className="text-center">
                    {/* 3D cube wireframe animation */}
                    <div className="mb-6 relative w-20 h-20 mx-auto">
                      <svg viewBox="0 0 100 100" className="w-full h-full" style={{ animation: 'spin 8s linear infinite' }}>
                        <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
                        <polygon points="50,10 90,35 90,65 50,90 10,65 10,35" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="1"/>
                        <polygon points="50,25 75,37 75,62 50,75 25,62 25,37" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="1"/>
                        <line x1="50" y1="10" x2="50" y2="25" stroke="rgba(255,255,255,0.1)" strokeWidth="1"/>
                        <line x1="90" y1="35" x2="75" y2="37" stroke="rgba(255,255,255,0.1)" strokeWidth="1"/>
                        <line x1="90" y1="65" x2="75" y2="62" stroke="rgba(255,255,255,0.1)" strokeWidth="1"/>
                        <line x1="50" y1="90" x2="50" y2="75" stroke="rgba(255,255,255,0.1)" strokeWidth="1"/>
                        <line x1="10" y1="65" x2="25" y2="62" stroke="rgba(255,255,255,0.1)" strokeWidth="1"/>
                        <line x1="10" y1="35" x2="25" y2="37" stroke="rgba(255,255,255,0.1)" strokeWidth="1"/>
                      </svg>
                    </div>
                    <p className="text-white/20 text-xs tracking-widest mb-1">AWAITING RECONSTRUCTION</p>
                    <p className="text-white/10 text-[10px]">Press "START RECONSTRUCTION" to begin</p>
                  </div>
                )}
              </div>
            )}
          </div>
          {isCompleted && modelUrl && (
            <div className="px-4 py-2 border-t border-white/5 shrink-0 flex items-center gap-6 text-[10px] text-white/25">
              <span>🖱 Left drag: rotate</span>
              <span>🖱 Right drag / scroll: zoom</span>
              <span>🖱 Middle drag: pan</span>
            </div>
          )}
        </div>

        {/* ── Right Panel: Pipeline Logs ── */}
        <div className="col-span-1 flex flex-col min-h-0 bg-[#080808]">
          <div className="px-4 py-3 border-b border-white/5 flex items-center gap-2 shrink-0">
            <div className="w-1.5 h-1.5 rounded-full bg-red-500/50" />
            <div className="w-1.5 h-1.5 rounded-full bg-yellow-500/50" />
            <div className="w-1.5 h-1.5 rounded-full bg-green-500/50" />
            <span className="ml-2 text-[10px] text-white/20 tracking-widest">PIPELINE LOGS</span>
          </div>
          <div className="flex-1 p-4 overflow-y-auto text-[10px] leading-relaxed text-white/50 tracking-wide space-y-1">
            {!logs.length ? (
              <div className="h-full flex items-center justify-center text-white/15 animate-pulse text-[10px] tracking-widest">
                AWAITING START...
              </div>
            ) : (
              logs.map((log, i) => {
                const isErr = log.includes('❌') || log.includes('failed') || log.includes('ERROR');
                const isOk = log.includes('✓') || log.includes('🎉') || log.includes('complete');
                const isWarn = log.includes('Warning') || log.includes('WARN');
                return (
                  <div key={i} className="flex gap-2 leading-snug">
                    <span className="text-white/15 shrink-0">›</span>
                    <span className={
                      isErr ? 'text-red-400' :
                      isOk ? 'text-emerald-400' :
                      isWarn ? 'text-yellow-400' : ''
                    }>
                      {log}
                    </span>
                  </div>
                );
              })
            )}
            <div ref={logsEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}
