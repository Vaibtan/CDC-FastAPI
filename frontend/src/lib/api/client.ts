import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { LOCAL_STORAGE_KEY, COOKIE_NAME } from '@/lib/constants';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for auth token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Get token from localStorage (client-side only)
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(LOCAL_STORAGE_KEY);
      if (stored) {
        try {
          const { state } = JSON.parse(stored);
          if (state?.token) {
            config.headers.Authorization = `Bearer ${state.token}`;
          }
        } catch {
          // Ignore parse errors
        }
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for 401 handling
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Clear BOTH localStorage and auth cookie to prevent redirect loops.
      // Middleware checks cookie; API client checks localStorage.
      if (typeof window !== 'undefined') {
        localStorage.removeItem(LOCAL_STORAGE_KEY);
        document.cookie = `${COOKIE_NAME}=; path=/; max-age=0`;

        // Check if the backend flagged the token as expired
        const isExpired = error.response.headers['x-token-expired'] === 'true';
        window.location.href = isExpired ? '/login?expired=true' : '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
