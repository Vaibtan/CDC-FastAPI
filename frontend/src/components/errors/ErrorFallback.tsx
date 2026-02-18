'use client';

import { AlertTriangle, RefreshCw, Home } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';

interface ErrorFallbackProps {
  error: Error & { digest?: string };
  reset?: () => void;
  title?: string;
  showHomeButton?: boolean;
}

export function ErrorFallback({
  error,
  reset,
  title = 'Something went wrong',
  showHomeButton = true,
}: ErrorFallbackProps) {
  return (
    <div className="flex items-center justify-center min-h-[400px] p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-4">
            <div className="p-3 rounded-full bg-destructive/10">
              <AlertTriangle className="h-8 w-8 text-destructive" />
            </div>
          </div>
          <CardTitle className="text-xl">{title}</CardTitle>
        </CardHeader>
        <CardContent className="text-center">
          <p className="text-muted-foreground mb-4">
            {error.message || 'An unexpected error occurred. Please try again.'}
          </p>
          {error.digest && (
            <p className="text-xs text-muted-foreground font-mono bg-muted p-2 rounded">
              Error ID: {error.digest}
            </p>
          )}
        </CardContent>
        <CardFooter className="flex justify-center gap-3">
          {reset && (
            <Button onClick={reset} variant="default">
              <RefreshCw className="h-4 w-4 mr-2" />
              Try Again
            </Button>
          )}
          {showHomeButton && (
            <Button variant="outline" asChild>
              <a href="/">
                <Home className="h-4 w-4 mr-2" />
                Go Home
              </a>
            </Button>
          )}
        </CardFooter>
      </Card>
    </div>
  );
}
