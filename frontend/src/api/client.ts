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

// ---- Graph ----
export interface CytoscapeNodeData {
  id: string;
  label: string;
  kind: string;
}
export interface CytoscapeEdgeData {
  id: string;
  source: string;
  target: string;
  relation: string;
}
export interface CytoscapeElement {
  group: 'nodes' | 'edges';
  data: CytoscapeNodeData | CytoscapeEdgeData;
}
export interface GraphReadResponse {
  dataset_id: string;
  session_id: string;
  elements: CytoscapeElement[];
  node_count: number;
  edge_count: number;
}
export interface SeedResponse {
  dataset_id: string;
  node_count: number;
  edge_count: number;
}
export interface ShortestPathResponse {
  dataset_id: string;
  source: string;
  target: string;
  path: string[] | null;
  length: number | null;
}
export interface MetricsResponse {
  dataset_id: string;
  node_count: number;
  edge_count: number;
  is_directed: boolean;
  is_dag: boolean;
  weakly_connected_components: number;
  strongly_connected_components: number;
  density: number;
  selfloops: string[];
}

// ---- Sessions ----
export interface GuestCreateResponse {
  session_id: string;
  expires_at: string;
  locale: string;
}

export async function createGuestSession(locale: 'en' | 'ar' = 'en'): Promise<GuestCreateResponse> {
  const res = await fetch('/api/v1/sessions/guest', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-Request-Id': newRequestId(),
    },
    body: JSON.stringify({ locale }),
  });
  return parseResponse<GuestCreateResponse>(res);
}

export async function getGraph(datasetId: string): Promise<GraphReadResponse> {
  return apiGet<GraphReadResponse>(`/api/v1/graph/${encodeURIComponent(datasetId)}`);
}

export async function seedGraph(
  datasetId: string,
  fixtureKey: string,
): Promise<SeedResponse> {
  const res = await fetch(
    `/api/v1/graph/${encodeURIComponent(datasetId)}/seed`,
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-Id': newRequestId(),
      },
      body: JSON.stringify({ dataset_key: fixtureKey }),
    },
  );
  return parseResponse<SeedResponse>(res);
}

export async function shortestPath(
  datasetId: string,
  source: string,
  target: string,
): Promise<ShortestPathResponse> {
  const res = await fetch(
    `/api/v1/graph/${encodeURIComponent(datasetId)}/shortest-path`,
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-Id': newRequestId(),
      },
      body: JSON.stringify({ source, target }),
    },
  );
  return parseResponse<ShortestPathResponse>(res);
}

export async function getMetrics(datasetId: string): Promise<MetricsResponse> {
  return apiGet<MetricsResponse>(
    `/api/v1/graph/${encodeURIComponent(datasetId)}/metrics`,
  );
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
