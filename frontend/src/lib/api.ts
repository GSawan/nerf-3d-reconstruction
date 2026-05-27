import axios from 'axios';
import { SessionResponse, JobStatusResponse } from '@/types/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001/api/v1';

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

  uploadDataset: async (files: File[]): Promise<SessionResponse> => {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    const res = await apiClient.post<SessionResponse>('/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  startReconstruction: async (sessionId: string, epochs = 100, mode = "mesh"): Promise<JobStatusResponse> => {
    const res = await apiClient.post<JobStatusResponse>(`/reconstruct/${sessionId}`, { epochs, mode });
    return res.data;
  },

  pollStatus: async (sessionId: string): Promise<JobStatusResponse> => {
    const res = await apiClient.get<JobStatusResponse>(`/reconstruct/status/${sessionId}`);
    return res.data;
  },

  getOutputUrl: (sessionId: string, filename: string): string => {
    return `${API_BASE}/outputs/${sessionId}/${filename}`;
  }
};

