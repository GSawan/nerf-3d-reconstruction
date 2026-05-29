import { create } from 'zustand';
import { JobStatusResponse, SessionResponse } from '@/types/api';
import { NeRFApi } from '@/lib/api';

interface NeRFState {
  activeSessionId: string | null;
  sessionMeta: SessionResponse | null;
  jobStatus: JobStatusResponse | null;
  isPolling: boolean;
  globalError: string | null;
  // Actions
  setSession: (session: SessionResponse) => void;
  setError: (err: string | null) => void;
  startPolling: () => void;
  stopPolling: () => void;
  cancelJob: () => Promise<void>;
  resetStore: () => void;
}

export const useNeRFStore = create<NeRFState>((set, get) => {
  let pollInterval: NodeJS.Timeout | null = null;
  
  const clearPoll = () => {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  };

  return {
    activeSessionId: null,
    sessionMeta: null,
    jobStatus: null,
    isPolling: false,
    globalError: null,
    
    setSession: (session) => {
      clearPoll();
      set({ 
        activeSessionId: session.session_id, 
        sessionMeta: session,
        jobStatus: null,
        globalError: null,
        isPolling: false
      });
    },

    setError: (err) => set({ globalError: err }),

    startPolling: () => {
      const { activeSessionId, isPolling } = get();
      if (!activeSessionId || isPolling) return;
      
      set({ isPolling: true });
      
      pollInterval = setInterval(async () => {
        try {
          const { activeSessionId: sid } = get();
          if (!sid) { clearPoll(); set({ isPolling: false }); return; }
          
          const jobStatus = await NeRFApi.pollStatus(sid);
          set({ jobStatus });
          
          // Stop polling when pipeline is done
          if (['completed', 'failed', 'idle'].includes(jobStatus.status)) {
            // Keep polling slowly on idle (waiting for job to start), stop on terminal
            if (jobStatus.status !== 'idle') {
              clearPoll();
              set({ isPolling: false });
            }
          }
        } catch (err: any) {
          // Don't kill polling on transient network errors — just log
          console.warn('Polling hiccup:', err?.message);
        }
      }, 2000); // 2-second polling
    },
    
    stopPolling: () => {
      clearPoll();
      set({ isPolling: false });
    },
    
    cancelJob: async () => {
      const { activeSessionId } = get();
      if (activeSessionId) {
        try {
          await NeRFApi.cancelReconstruction(activeSessionId);
          // Note: We deliberately do NOT stop polling here. 
          // We wait for the backend worker to explicitly propagate the CANCELLED state.
        } catch (err) {
          console.error("Cancellation failed:", err);
        }
      }
    },

    resetStore: () => {
      clearPoll();
      set({
        activeSessionId: null,
        sessionMeta: null,
        jobStatus: null,
        isPolling: false,
        globalError: null
      });
    }
  };
});
