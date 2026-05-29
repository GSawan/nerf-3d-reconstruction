import axios from 'axios';
import { SessionResponse, JobStatusResponse } from '@/types/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const NeRFApi = {
  checkHealth: async () => {
    const res = await apiClient.get('/health/');
    return res.data;
  },

  uploadDataset: async (files: File[], mode: string = "high"): Promise<SessionResponse> => {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    formData.append('mode', mode);
    const res = await apiClient.post<SessionResponse>('/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  startReconstruction: async (sessionId: string): Promise<JobStatusResponse> => {
    const res = await apiClient.post<JobStatusResponse>(`/reconstruct/${sessionId}`, {});
    return res.data;
  },

  pollStatus: async (sessionId: string): Promise<JobStatusResponse> => {
    const res = await apiClient.get<JobStatusResponse>(`/reconstruct/status/${sessionId}`);
    return res.data;
  },

  getOutputUrl: (sessionId: string, filename: string): string => {
    return `${API_BASE}/outputs/${sessionId}/${filename}`;
  },

  launchViewer: async (sessionId: string): Promise<any> => {
    const res = await apiClient.post(`/reconstruct/launch_viewer/${sessionId}`);
    return res.data;
  },

  cancelReconstruction: async (sessionId: string): Promise<any> => {
    // Attempt cancellation if backend supports it
    const res = await apiClient.post(`/reconstruct/cancel/${sessionId}`);
    return res.data;
  }
};
