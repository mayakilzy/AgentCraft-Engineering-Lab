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

// ---- Experiments (G05) ----

export interface ExperimentListResponse {
  count: number;
  ids: string[];
}

export interface LocalizedText {
  en: string;
  ar: string;
}

export interface ManifestStep {
  id: string;
  title: LocalizedText;
  instruction: LocalizedText;
  operation_key: string;
  input_schema_ref: string;
  validator_key: string;
  expected: Record<string, unknown>;
}

export interface ExperimentManifest {
  id: string;
  version: string;
  module_id: string;
  level: 'beginner' | 'intermediate' | 'advanced';
  estimated_minutes: number;
  title: LocalizedText;
  description: LocalizedText;
  technology: string[];
  prerequisites: string[];
  dataset_key: string;
  required_services: string[];
  capabilities: string[];
  public_demo_enabled: boolean;
  steps: ManifestStep[];
  failure_mode?: string;
}

export async function listExperiments(): Promise<ExperimentListResponse> {
  return apiGet<ExperimentListResponse>('/api/v1/experiments');
}

export async function getExperiment(id: string): Promise<ExperimentManifest> {
  return apiGet<ExperimentManifest>(`/api/v1/experiments/${encodeURIComponent(id)}`);
}

// ---- Runs (G05) ----

export interface RunCreateRequest {
  mode: 'guided' | 'challenge';
  inputs: Record<string, unknown>;
}

export interface StepVerdict {
  step_id: string;
  operation_key: string;
  operation_status: string;
  operation_error_code: string | null;
  validator_key: string;
  validator_passed: boolean;
  validator_message: string;
  expected: Record<string, unknown>;
  actual: Record<string, unknown>;
}

export interface RunCreateResponse {
  run_id: string;
  status: string;
  trace_id: string | null;
  error_code: string | null;
  step_verdicts: StepVerdict[];
}

export interface RunRecord {
  run_id: string;
  experiment_id: string;
  mode: string;
  status: string;
  trace_id: string | null;
  error_code: string | null;
  started_at: string | null;
  ended_at: string | null;
  inputs_redacted: Record<string, unknown> | null;
  verification: { step_verdicts?: StepVerdict[] } | null;
  outputs: Record<string, unknown> | null;
}

export interface RunListResponse {
  count: number;
  runs: RunRecord[];
}

export interface ResetResponse {
  run_id: string;
  experiment_id: string;
  dataset_id: string | null;
  deleted_nodes: number;
  deleted_edges: number;
  reset_event_id: string;
}

export interface CompareResponse {
  run_a_id: string;
  run_b_id: string;
  same_experiment: boolean;
  same_final_status: boolean;
  same_step_count: boolean;
  step_diffs: Array<Record<string, unknown>>;
  note: string;
}

export interface ExportResponse {
  format: 'md' | 'json';
  report: unknown;
}

export async function createRun(
  experimentId: string,
  body: RunCreateRequest,
): Promise<RunCreateResponse> {
  const res = await fetch(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}/runs`,
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-Id': newRequestId(),
      },
      body: JSON.stringify(body),
    },
  );
  return parseResponse<RunCreateResponse>(res);
}

export async function getRun(runId: string): Promise<RunRecord> {
  return apiGet<RunRecord>(`/api/v1/runs/${encodeURIComponent(runId)}`);
}

export async function listRuns(
  experimentId?: string,
  limit: number = 50,
): Promise<RunListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (experimentId) params.set('experiment_id', experimentId);
  return apiGet<RunListResponse>(`/api/v1/runs?${params.toString()}`);
}

export async function resetRun(runId: string): Promise<ResetResponse> {
  const res = await fetch(
    `/api/v1/runs/${encodeURIComponent(runId)}/reset`,
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-Id': newRequestId(),
      },
    },
  );
  return parseResponse<ResetResponse>(res);
}

export async function exportRun(
  runId: string,
  format: 'md' | 'json' = 'md',
): Promise<ExportResponse> {
  return apiGet<ExportResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/export?format=${format}`,
  );
}

export async function compareRuns(
  runAId: string,
  runBId: string,
): Promise<CompareResponse> {
  const res = await fetch('/api/v1/runs/compare', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-Request-Id': newRequestId(),
    },
    body: JSON.stringify({ run_a_id: runAId, run_b_id: runBId }),
  });
  return parseResponse<CompareResponse>(res);
}

// ---- Mentor (G06 T22) ----

export interface MentorRequest {
  run_id: string;
  question: string;
  lang: 'en' | 'ar';
}

export interface MentorResponse {
  answer: string;
  diagnosis_state: 'confirmed' | 'likely' | 'insufficient_evidence';
  evidence_refs: Array<Record<string, unknown>>;
  next_checks: string[];
  provider_mode: string;
}

export async function askMentor(
  body: MentorRequest,
): Promise<MentorResponse> {
  const res = await fetch('/api/v1/mentor/explain', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-Request-Id': newRequestId(),
    },
    body: JSON.stringify(body),
  });
  return parseResponse<MentorResponse>(res);
}
