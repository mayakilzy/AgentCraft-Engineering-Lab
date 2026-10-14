/**
 * useGuestSession — unified guest-session bootstrap hook.
 *
 * Mission I, ISSUE-004 fix. Pages that need a guest session call this
 * hook so the session is created lazily and cached module-level.
 */
import { useEffect, useState } from 'react';
import {
  createGuestSession,
  type GuestCreateResponse,
} from '../api/client';

let cachedSession: GuestCreateResponse | null = null;
let inFlight: Promise<GuestCreateResponse> | null = null;

export function getCachedSession(): GuestCreateResponse | null {
  return cachedSession;
}

export function clearCachedSession(): void {
  cachedSession = null;
  inFlight = null;
}

export function ensureGuestSession(locale: 'en' | 'ar' = 'en'): Promise<GuestCreateResponse> {
  if (cachedSession) {
    return Promise.resolve(cachedSession);
  }
  if (inFlight) {
    return inFlight;
  }
  inFlight = createGuestSession(locale)
    .then((s) => {
      cachedSession = s;
      inFlight = null;
      return s;
    })
    .catch((err) => {
      inFlight = null;
      throw err;
    });
  return inFlight;
}

export function useGuestSession(locale: 'en' | 'ar' = 'en') {
  const [session, setSession] = useState<GuestCreateResponse | null>(cachedSession);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!cachedSession);

  useEffect(() => {
    let cancelled = false;
    if (cachedSession) {
      setSession(cachedSession);
      setLoading(false);
      return;
    }
    setLoading(true);
    ensureGuestSession(locale)
      .then((s) => {
        if (!cancelled) {
          setSession(s);
          setError(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [locale]);

  return { session, error, loading };
}
