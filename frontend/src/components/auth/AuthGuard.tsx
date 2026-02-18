'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { Loader2 } from 'lucide-react';

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, token } = useAuthStore();
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Wait for hydration
    const checkAuth = () => {
      if (!isAuthenticated || !token) {
        // Redirect to login with return URL
        router.replace(`/login?redirect=${encodeURIComponent(pathname)}`);
      } else {
        setIsLoading(false);
      }
    };

    // Small delay to ensure Zustand has hydrated from localStorage
    const timer = setTimeout(checkAuth, 50);
    return () => clearTimeout(timer);
  }, [isAuthenticated, token, router, pathname]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
