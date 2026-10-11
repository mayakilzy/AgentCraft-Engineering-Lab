/**
 * API client — thin typed wrapper around fetch. Adds the guest cookie
 * (same-origin), an X-Request-Id header for correlation, and surfaces
 * the contract error body shape on failure.
 *
 * Endpoints actually wired in later groups; G01 only needs the typed
 * surface and the health endpoint to prove the dev loop.
 */
export interface ApiError {
  code: string;
  message: string;
  request_id: string;
  details?: Record<string, unknown>;
}

function newRequestId(): string {
  return `web-${Math.random().toString(36).slice(2, 10)}`;
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    method: 'GET',
    credentials: 'same-origin',
    headers: { 'X-Request-Id': newRequestId() },
  });
  return parseResponse<T>(res);
}

async function parseResponse<T>(res: Response): Promise<T> {
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err: ApiError =
      body && typeof body === 'object' && 'code' in body
        ? (body as ApiError)
        : { code: 'http_error', message: `HTTP ${res.status}`, request_id: '-' };
    throw err;
  }
  return body as T;
}

export interface LiveResponse {
  status: 'ok';
  app: string;
}

export interface ReadyResponse {
  status: 'ready' | 'degraded' | 'not_ready';
  services: Record<string, { state: string; detail: string | null }>;
  app_env: string;
}

export interface ModulesResponse {
  count: number;
  ids: string[];
}

export async function getHealthLive(): Promise<LiveResponse> {
  return apiGet<LiveResponse>('/api/v1/health/live');
}

export async function getHealthReady(): Promise<ReadyResponse> {
  return apiGet<ReadyResponse>('/api/v1/health/ready');
}

export async function getModules(): Promise<ModulesResponse> {
  return apiGet<ModulesResponse>('/api/v1/modules');
}
