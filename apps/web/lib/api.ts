import type {
  AccountBrief,
  ActivationBrief,
  AgentJobStatus,
  AgentResult,
  AgentRunRequest,
  DiscoveryCandidate,
  DiscoveryCandidateRecord,
  DiscoveryJob,
  DiscoveryImportResult,
  DiscoverySearchResponse,
  DraftAsset,
  ProductContext,
  QueueResponse,
  SystemStatus
} from "./types";

const SERVER_API_BASE = process.env.API_BASE_URL || "http://localhost:8000";
const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api";
const API_BASE = typeof window === "undefined" ? SERVER_API_BASE : PUBLIC_API_BASE;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text();
    throw new ApiError(message || `HTTP ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    cache: "no-store"
  });
  return readJson<T>(response);
}

async function postJson<T, TBody>(path: string, body: TBody): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });
  return readJson<T>(response);
}

export function getApiBaseUrl(): string {
  return PUBLIC_API_BASE;
}

export function getQueue(): Promise<QueueResponse> {
  return fetchJson("/accounts");
}

export function getProductContexts(): Promise<ProductContext[]> {
  return fetchJson("/product-contexts");
}

export function getAccountBrief(accountId: string): Promise<AccountBrief> {
  return fetchJson(`/accounts/${accountId}/brief`);
}

export function getDraft(draftId: string): Promise<DraftAsset> {
  return fetchJson(`/drafts/${draftId}`);
}

export function getHandoff(accountId: string): Promise<ActivationBrief> {
  return fetchJson(`/deals/${accountId}/handoff`);
}

export function runAgent(body: AgentRunRequest): Promise<AgentResult> {
  return postJson("/agent/run", body);
}

export function createAgentJob(body: AgentRunRequest): Promise<AgentJobStatus> {
  return postJson("/agent/jobs", body);
}

export function getAgentJob(jobId: string): Promise<AgentJobStatus> {
  return fetchJson(`/agent/jobs/${jobId}`);
}

export function getSystemStatus(): Promise<SystemStatus> {
  return fetchJson("/system/status");
}

export function searchDiscovery(body: {
  prompt: string;
  product_context_key?: string;
  limit?: number;
}): Promise<DiscoverySearchResponse> {
  return postJson("/discovery/search", body);
}

export function addDiscoveryCandidate(body: {
  candidate: DiscoveryCandidate;
  candidate_record_id?: string;
  refresh_workflow?: boolean;
}): Promise<DiscoveryImportResult> {
  return postJson("/discovery/candidates/add", body);
}

export function getDiscoveryJobs(): Promise<DiscoveryJob[]> {
  return fetchJson("/discovery/jobs");
}

export function getDiscoveryInbox(): Promise<DiscoveryCandidateRecord[]> {
  return fetchJson("/discovery/inbox");
}

export function createDiscoveryJob(body: {
  product_context_key: string;
  prompt: string;
  cadence_minutes?: number;
  limit?: number;
  auto_import_threshold?: number;
}): Promise<DiscoveryJob> {
  return postJson("/discovery/jobs", body);
}

export function runDiscoveryJob(jobId: string): Promise<{ job: DiscoveryJob; stored_count: number }> {
  return postJson(`/discovery/jobs/${jobId}/run`, {});
}

export function runDueAutomation(): Promise<{ discovery: Record<string, number>; nurture: Record<string, string> }> {
  return postJson("/automation/run-due", {});
}

export async function createProductContext(body: {
  key: string;
  name: string;
  version?: string;
  overview: string;
  icp_segments?: string[];
  trigger_patterns?: string[];
  disqualifiers?: string[];
  approved_claims?: Array<Record<string, string>>;
  buyer_personas?: Array<Record<string, string>>;
  activation_playbook?: Array<Record<string, string>>;
}) {
  return postJson("/product-contexts", body);
}

export async function createAccount(body: {
  name: string;
  segment: string;
  territory: string;
  summary: string;
  pipeline_stage?: string;
  owner_role?: string;
  metadata?: Record<string, string>;
}) {
  return postJson("/accounts", body);
}

export async function createContact(
  accountId: string,
  body: {
    name: string;
    role: string;
    persona: string;
    email: string;
    influence_level?: string;
    status?: string;
    notes?: string;
  }
) {
  return postJson(`/accounts/${accountId}/contacts`, body);
}

export async function ingestSignal(body: {
  account_id: string;
  signal_type: string;
  source_type: string;
  title: string;
  summary: string;
  source_url: string;
  detected_at: string;
  facts?: Record<string, string | number>;
  citations?: Array<{
    label: string;
    source_url: string;
    claim: string;
    excerpt?: string | null;
    published_at?: string | null;
  }>;
  raw_payload?: Record<string, string>;
}) {
  return postJson("/signals/ingest", body);
}

export async function ingestTelemetry(body: {
  account_id: string;
  event_type: string;
  detected_at: string;
  payload?: Record<string, string | number>;
}) {
  return postJson("/telemetry/ingest", body);
}

export async function refreshOpportunity(accountId: string) {
  return postJson("/workflows/opportunity-refresh", { account_id: accountId });
}

export async function createHandoff(accountId: string) {
  return postJson(`/deals/${accountId}/handoff`, {});
}

export async function approveDraft(draftId: string, reviewerRole: string, notes?: string) {
  return postJson(`/drafts/${draftId}/approve`, { reviewer_role: reviewerRole, notes: notes ?? "" });
}

export async function rejectDraft(draftId: string, reviewerRole: string, notes?: string) {
  return postJson(`/drafts/${draftId}/reject`, { reviewer_role: reviewerRole, notes: notes ?? "" });
}

export async function editDraft(draftId: string, body: string) {
  return postJson<{ id: string; status: string; edited_body: string }, { body: string }>(
    `/drafts/${draftId}/edit`,
    { body }
  );
}
