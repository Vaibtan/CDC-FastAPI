import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface User {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
}

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
  setUser: (user: User) => void;
}

// Cookie helpers for middleware auth checks
function setAuthCookie(token: string) {
  if (typeof document !== 'undefined') {
    // Set cookie with 7 day expiry, SameSite=Lax for security
    document.cookie = `walstream-token=${token}; path=/; max-age=${7 * 24 * 60 * 60}; SameSite=Lax`;
  }
}

function removeAuthCookie() {
  if (typeof document !== 'undefined') {
    document.cookie = 'walstream-token=; path=/; max-age=0';
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      login: (token, user) => {
        setAuthCookie(token);
        set({
          token,
          user,
          isAuthenticated: true,
        });
      },
      logout: () => {
        removeAuthCookie();
        set({
          token: null,
          user: null,
          isAuthenticated: false,
        });
      },
      setUser: (user) => set({ user }),
    }),
    {
      name: 'walstream-auth',
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
