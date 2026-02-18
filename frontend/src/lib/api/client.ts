import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';

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
      const stored = localStorage.getItem('walstream-auth');
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
        localStorage.removeItem('walstream-auth');
        document.cookie = 'walstream-token=; path=/; max-age=0';
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
