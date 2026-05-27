'use client';
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useNeRFStore } from '@/store/nerfStore';
import { NeRFApi } from '@/lib/api';
import ModelViewer from '@/components/ModelViewer';
import { ErrorBoundary } from '@/components/ErrorBoundary';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001';

const PHASE_LABELS: Record<string, string> = {
  queued: 'QUEUED',
  sparse_reconstruction: '1/4 SPARSE RECONSTRUCTION',
  dense_reconstruction: '2/4 DENSE STEREO',
  meshing: '3/4 SURFACE MESHING',
  completed: 'COMPLETED',
  failed: 'FAILED',
  idle: 'IDLE',
};

const PHASE_COLOR: Record<string, string> = {
  queued: 'text-yellow-400',
  sparse_reconstruction: 'text-blue-400 animate-pulse',
  dense_reconstruction: 'text-indigo-400 animate-pulse',
  meshing: 'text-purple-400 animate-pulse',
  completed: 'text-emerald-400',
  failed: 'text-red-400',
  idle: 'text-[#e2e0d8]/50',
};

export default function ViewerDashboard() {
  const router = useRouter();
  const { activeSessionId, jobStatus, startPolling, stopPolling } = useNeRFStore();
  const logsEndRef = useRef<HTMLDivElement>(null);
  const [activePreview, setActivePreview] = useState<string | null>(null);
  const [isInitializing, setIsInitializing] = useState(false);
  const [debugView, setDebugView] = useState<'model' | 'mesh' | 'dense' | 'sparse'>('model');

  useEffect(() => {
    if (activeSessionId) startPolling();
    return () => stopPolling();
  }, [activeSessionId, startPolling, stopPolling]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [jobStatus?.logs?.length]);

  // Remove auto-select latest preview so 3D viewer is visible by default
  // useEffect(() => {
  //   if (jobStatus?.previews?.length) {
  //     const last = jobStatus.previews[jobStatus.previews.length - 1];
  //     setActivePreview(last);
  //   }
  // }, [jobStatus?.previews?.length]);

  const handleStart = async () => {
    if (!activeSessionId) return;
    setIsInitializing(true);
    try {
      await NeRFApi.startReconstruction(activeSessionId, 100);
      startPolling();
    } catch (e: any) {
      console.error('Failed to start pipeline:', e?.response?.data || e.message);
      setIsInitializing(false);
    }
  };

  const status = jobStatus?.status || 'idle';
  const isActive = ['queued', 'sparse_reconstruction', 'dense_reconstruction', 'meshing'].includes(status);
  const isCompleted = status === 'completed';
  const isFailed = status === 'failed';
  
  // Auto-clear initializing state once pipeline starts moving
  useEffect(() => {
    if (isActive || isCompleted || isFailed) {
      setIsInitializing(false);
    }
  }, [isActive, isCompleted, isFailed]);

  const progress = jobStatus?.progress ?? 0;
  const previews = jobStatus?.previews ?? [];
  const logs = jobStatus?.logs || [];
  
  // Extract metrics from logs
  const registeredCamerasLog = logs.find(l => l.includes('Registered cameras:')) || '';
  const registeredCameras = registeredCamerasLog.split('Registered cameras: ')[1] || '-';
  
  const sparsePointsLog = logs.find(l => l.includes('Sparse points:')) || '';
  const sparsePoints = sparsePointsLog.split('Sparse points: ')[1] || '-';
  
  const generatedSplatsLog = logs.find(l => l.includes('Exporting optimized .ply format (')) || '';
  const totalSplats = generatedSplatsLog.match(/\(([\d]+)\s/)?.[1] || '-';

  return (
    <div className="h-screen bg-[#080808] text-[#e2e0d8] flex flex-col overflow-hidden">
      {/* Header */}
      <header className="border-b border-white/10 px-8 py-5 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-6">
          <button 
            onClick={() => router.push('/upload')}
            className="text-xs text-[#e2e0d8]/50 hover:text-white transition-colors border border-white/10 px-3 py-1 bg-[#111]"
          >
            ← BACK TO UPLOAD
          </button>
          <div>
            <h1 className="text-3xl font-light tracking-[0.15em] uppercase">
              Reconstruction Telemetry
            </h1>
            <p className="text-xs font-mono text-[#e2e0d8]/30 mt-1 tracking-widest">
              {activeSessionId || 'NO ACTIVE SESSION'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={handleStart}
            disabled={!activeSessionId || isActive || isCompleted || isInitializing}
            className={`px-6 py-2 text-xs font-bold tracking-[0.2em] uppercase transition-colors disabled:cursor-not-allowed ${
              isInitializing 
                ? 'bg-emerald-500 text-black animate-pulse' 
                : 'bg-[#e2e0d8] text-[#080808] hover:bg-white disabled:opacity-50'
            }`}
          >
            {isInitializing ? 'PIPELINE INITIALIZED!...' : isActive ? 'PIPELINE RUNNING' : isCompleted ? '✓ COMPLETE' : 'INITIALIZE PIPELINE'}
          </button>
        </div>
      </header>

      {/* Main Grid */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-0 divide-x divide-white/5 min-h-0">

        {/* Left: Metrics Panel */}
        <div className="p-6 flex flex-col gap-5 overflow-y-auto">
          {/* Phase */}
          <div className="bg-[#111] border border-white/10 p-5">
            <p className="text-xs tracking-widest uppercase text-[#e2e0d8]/40 mb-3">Phase</p>
            <p className={`text-lg font-mono font-bold tracking-wide ${PHASE_COLOR[status] || 'text-[#e2e0d8]'}`}>
              {PHASE_LABELS[status] || status.toUpperCase()}
            </p>
          </div>

          {/* Progress bar */}
          <div className="bg-[#111] border border-white/10 p-5">
            <div className="flex justify-between text-xs text-[#e2e0d8]/40 uppercase tracking-widest mb-3">
              <span>Progress</span><span>{progress}%</span>
            </div>
            <div className="w-full h-1.5 bg-black/50 overflow-hidden">
              <div
                className={`h-full transition-all duration-700 ease-out ${isCompleted ? 'bg-emerald-400' : isFailed ? 'bg-red-500' : 'bg-[#e2e0d8]'}`}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* Pipeline Metrics */}
          <div className="bg-[#111] border border-white/10 p-5 space-y-4">
            <p className="text-xs tracking-widest uppercase text-[#e2e0d8]/40 border-b border-white/5 pb-3">Reconstruction Metrics</p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-[#e2e0d8]/40 uppercase tracking-wider mb-1">Status</p>
                <p className="text-sm font-mono font-light text-[#e2e0d8]">
                  {status === 'idle' ? 'STANDBY' : isActive ? 'PROCESSING' : 'DONE'}
                </p>
              </div>
              <div>
                <p className="text-xs text-[#e2e0d8]/40 uppercase tracking-wider mb-1">Render Outputs</p>
                <p className="text-xl font-mono font-light text-[#e2e0d8]">{previews.length}</p>
              </div>
              
              {/* Registration Telemetry */}
              <div className="col-span-2 grid grid-cols-3 gap-4 pt-3 border-t border-white/5">
                <div>
                  <p className="text-xs text-blue-400/60 uppercase tracking-wider mb-1">Cameras</p>
                  <p className="text-sm font-mono font-light text-blue-300">{registeredCameras}</p>
                </div>
                <div>
                  <p className="text-xs text-yellow-400/60 uppercase tracking-wider mb-1">Sparse Points</p>
                  <p className="text-sm font-mono font-light text-yellow-300">{sparsePoints}</p>
                </div>
                <div>
                  <p className="text-xs text-purple-400/60 uppercase tracking-wider mb-1">Volumetric</p>
                  <p className="text-sm font-mono font-light text-purple-300">{totalSplats}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Error Box */}
          {jobStatus?.error && (
            <div className="bg-red-950/30 border border-red-800/40 p-4">
              <p className="text-xs font-bold text-red-400 uppercase tracking-widest mb-2">Critical Error</p>
              <p className="text-red-300/80 font-mono text-xs leading-relaxed">{jobStatus.error}</p>
            </div>
          )}
        </div>

        {/* Center: Preview Viewer */}
        <div className="p-6 flex flex-col gap-4 lg:col-span-1 min-h-0 relative">
          
          {/* Cinematic Overlay on Completion */}
          {isCompleted && (
            <div className="absolute inset-0 pointer-events-none bg-emerald-900/10 mix-blend-screen z-10 transition-opacity duration-1000" />
          )}

          <div className="flex items-center justify-between shrink-0 z-20">
            <p className="text-xs tracking-widest uppercase text-[#e2e0d8]/40">Interactive 3D Reconstruction</p>
            <div className="flex gap-4">
              {isCompleted && activeSessionId && (
                <div className="flex gap-2 mr-4">
                  {(['model', 'mesh', 'dense', 'sparse'] as const).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => { setDebugView(mode); setActivePreview(null); }}
                      className={`text-xs tracking-widest uppercase transition-colors px-2 py-1 border ${
                        debugView === mode && !activePreview
                          ? 'border-emerald-400 text-emerald-400 bg-emerald-900/20'
                          : 'border-white/10 text-white/40 hover:text-white hover:border-white/30'
                      }`}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
              )}
              {isCompleted && activeSessionId && (
                <a 
                  href={`${API_BASE}/datasets/${activeSessionId}/model/${debugView}.ply`}
                  download={`${debugView}-${activeSessionId}.ply`}
                  className="text-xs tracking-widest uppercase text-purple-400 hover:text-white transition-colors"
                >
                  [ DOWNLOAD .PLY ]
                </a>
              )}
              {activePreview && (
                <button 
                  onClick={() => setActivePreview(null)}
                  className="text-xs tracking-widest uppercase text-emerald-400 hover:text-white transition-colors"
                >
                  [ VIEW 3D MODEL ]
                </button>
              )}
            </div>
          </div>

          <div className="flex-1 min-h-0 bg-[#050505] border border-white/10 flex items-center justify-center relative overflow-hidden">
            {activePreview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={`${API_BASE}${activePreview}`}
                alt="Novel view render"
                className="w-full h-full object-contain"
              />
            ) : status === 'completed' && activeSessionId ? (
              <ErrorBoundary>
                <ModelViewer url={`${API_BASE}/datasets/${activeSessionId}/model/${debugView}.ply`} />
              </ErrorBoundary>
            ) : status === 'sparse_reconstruction' ? (
              <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border border-white/20 border-t-emerald-400 rounded-full animate-spin" />
                <p className="font-mono text-xs tracking-widest text-emerald-400">EXTRACTING SPARSE FEATURES...</p>
              </div>
            ) : status === 'dense_reconstruction' ? (
              <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border border-white/20 border-t-blue-400 rounded-full animate-spin" />
                <p className="font-mono text-xs tracking-widest text-blue-400">RUNNING PATCH MATCH STEREO...</p>
              </div>
            ) : status === 'meshing' ? (
              <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border border-white/20 border-t-purple-400 rounded-full animate-spin" />
                <p className="font-mono text-xs tracking-widest text-purple-400">GENERATING POISSON MESH...</p>
              </div>
            ) : (
              <div className="text-center text-[#e2e0d8]/20">
                {isActive ? (
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-8 h-8 border border-white/20 border-t-white/60 rounded-full animate-spin" />
                    <p className="font-mono text-xs tracking-widest">PROCESSING...</p>
                  </div>
                ) : (
                  <p className="font-mono text-xs tracking-widest">AWAITING PIPELINE</p>
                )}
              </div>
            )}
          </div>

          {/* Preview thumbnails */}
          {previews.length > 0 && (
            <div className="grid grid-cols-4 gap-2">
              {previews.map((p, i) => (
                <button
                  key={i}
                  onClick={() => setActivePreview(p)}
                  className={`aspect-square bg-[#050505] border overflow-hidden transition-all ${activePreview === p ? 'border-[#e2e0d8]' : 'border-white/10 hover:border-white/30'}`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`${API_BASE}${p}`} alt={`Preview ${i}`} className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          )}

          {/* Download button when complete */}
          {isCompleted && previews.length > 0 && (
            <a
              href={`${API_BASE}${previews[0]}`}
              download
              className="block w-full text-center py-3 border border-emerald-800/50 text-emerald-400 text-xs font-semibold uppercase tracking-[0.2em] hover:bg-emerald-900/20 transition-all"
            >
              Download Novel View
            </a>
          )}
        </div>

        {/* Right: Terminal Logs */}
        <div className="flex flex-col min-h-0 border-l border-white/5">
          <div className="px-6 py-4 border-b border-white/5 flex items-center gap-2 shrink-0">
            <div className="w-2 h-2 rounded-full bg-red-500/50" />
            <div className="w-2 h-2 rounded-full bg-yellow-500/50" />
            <div className="w-2 h-2 rounded-full bg-green-500/50" />
            <span className="ml-2 font-mono text-xs text-[#e2e0d8]/30 tracking-widest">STDOUT / PIPELINE LOGS</span>
          </div>
          <div className="flex-1 p-5 overflow-y-auto font-mono text-xs leading-relaxed text-[#e2e0d8]/70 tracking-wide">
            {!jobStatus?.logs?.length ? (
              <div className="h-full flex items-center justify-center text-[#e2e0d8]/20 animate-pulse text-xs tracking-widest">
                AWAITING INITIALIZATION...
              </div>
            ) : (
              <div className="space-y-1.5">
                {jobStatus.logs.map((log, i) => {
                  const isError = log.includes('failed') || log.includes('ERROR') || log.includes('crash');
                  const isGood = log.includes('successfully') || log.includes('complete') || log.includes('PSNR');
                  const isEpoch = log.includes('Epoch');
                  return (
                    <div key={i} className="flex gap-3 leading-snug">
                      <span className="text-[#e2e0d8]/20 shrink-0 select-none">›</span>
                      <span className={isError ? 'text-red-400' : isGood ? 'text-emerald-400' : isEpoch ? 'text-blue-300' : ''}>
                        {log}
                      </span>
                    </div>
                  );
                })}
                <div ref={logsEndRef} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
