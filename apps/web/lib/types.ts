export type Citation = {
  label: string;
  source_url: string;
  claim: string;
  excerpt?: string | null;
  published_at?: string | null;
};

export type RationaleStep = {
  title: string;
  detail: string;
  weight: number;
};

export type ModelRouteDecision = {
  workflow: string;
  target_profile: "complex_reasoner" | "draft_executor";
  provider: "nvidia" | "openrouter" | "local";
  model: string;
  reason: string;
  thinking: boolean;
  requires_manual_review_on_failure: boolean;
};

export type ComplianceClaimCheck = {
  sentence: string;
  sentence_type: "boilerplate" | "factual_claim";
  needs_citation: boolean;
  supported: boolean;
  reason: string;
};

export type ComplianceReceipt = {
  passed: boolean;
  issues: string[];
  claim_checks: ComplianceClaimCheck[];
  route: ModelRouteDecision;
  reviewed_at: string;
};

export type DraftAsset = {
  id: string;
  account_id: string;
  opportunity_id?: string | null;
  persona: string;
  channel: string;
  subject: string;
  body: string;
  edited_body?: string | null;
  status: string;
  citations: Citation[];
  rationale: RationaleStep[];
  model_route: ModelRouteDecision;
  compliance_receipt?: ComplianceReceipt | null;
};

export type OpportunityHypothesis = {
  id: string;
  account_id: string;
  product_context_key: string;
  status: string;
  intent_score: number;
  fit_score: number;
  freshness_score: number;
  recommended_action: string;
  stakeholder_map: Array<Record<string, string>>;
  rationale: RationaleStep[];
  evidence: Citation[];
  model_route: ModelRouteDecision;
};

export type ActivityEvent = {
  id: string;
  kind: string;
  title: string;
  detail: string;
  created_at: string;
};

export type PersonaBrief = {
  name: string;
  role: string;
  persona: string;
  email: string;
  influence_level: string;
  status: string;
  notes: string;
};

export type AccountSummary = {
  id: string;
  name: string;
  segment: string;
  territory: string;
  pipeline_stage: string;
  summary: string;
  owner_role: string;
  intent_score: number;
  fit_score: number;
  freshness_score: number;
  next_action: string;
  last_activity_at?: string | null;
  metadata: Record<string, string>;
};

export type TelemetryEvent = {
  id: string;
  account_id: string;
  event_type: string;
  topic_family: string;
  detected_at: string;
  payload: Record<string, string | number>;
};

export type ActivationBrief = {
  id: string;
  account_id: string;
  deal_label: string;
  stage: string;
  summary: string;
  blockers: Array<Record<string, string>>;
  tasks: Array<Record<string, string>>;
  telemetry_highlights: Array<Record<string, string>>;
  stakeholders: Array<Record<string, string>>;
  created_at: string;
};

export type NurtureSequence = {
  id: string;
  account_id: string;
  product_context_key?: string | null;
  kind: "prospect_outreach" | "post_sale_activation";
  status: string;
  stage: string;
  current_round: number;
  max_rounds: number;
  cadence_days: number;
  next_touch_at?: string | null;
  last_touched_at?: string | null;
  state: Record<string, unknown>;
  exit_reason: string;
};

export type NurtureTouch = {
  id: string;
  sequence_id: string;
  account_id: string;
  draft_id?: string | null;
  persona: string;
  role: string;
  channel: string;
  touch_kind: string;
  step_order: number;
  round_number: number;
  status: string;
  due_at?: string | null;
  completed_at?: string | null;
  summary: string;
  metadata: Record<string, unknown>;
  auto_generated: boolean;
};

export type AccountBrief = {
  account: AccountSummary;
  contacts: PersonaBrief[];
  signals: Array<{
    id: string;
    title: string;
    summary: string;
    signal_type: string;
    source_type: string;
    source_url: string;
    detected_at: string;
    citations: Citation[];
    facts: Record<string, string | number>;
  }>;
  telemetry: TelemetryEvent[];
  opportunities: OpportunityHypothesis[];
  drafts: DraftAsset[];
  nurture_sequences: NurtureSequence[];
  nurture_touches: NurtureTouch[];
  activity: ActivityEvent[];
  activation_briefs: ActivationBrief[];
};

export type QueueItem = {
  id: string;
  name: string;
  segment: string;
  pipeline_stage: string;
  intent_score: number;
  fit_score: number;
  freshness_score: number;
  product_context_key?: string | null;
  next_action: string;
  top_signal?: string | null;
};

export type QueueResponse = {
  items: QueueItem[];
};

export type ProductContext = {
  id: string;
  key: string;
  name: string;
  version: string;
  overview: string;
  icp_segments: string[];
  trigger_patterns: string[];
  disqualifiers: string[];
  approved_claims: Array<Record<string, string>>;
  buyer_personas: Array<Record<string, string>>;
  activation_playbook: Array<Record<string, string>>;
};

export type DiscoverySignal = {
  topic_family: string;
  signal_type: string;
  source_type: string;
  title: string;
  summary: string;
  source_url: string;
  detected_at: string;
  facts: Record<string, string | number>;
  citations: Citation[];
  raw_payload: Record<string, string | number>;
};

export type DiscoveryCandidate = {
  id: string;
  name: string;
  segment: string;
  territory: string;
  summary: string;
  product_context_key: string;
  interest_score: number;
  fit_score: number;
  freshness_score: number;
  top_signal: string;
  reason: string;
  reasons: string[];
  citations: Citation[];
  signals: DiscoverySignal[];
  route: ModelRouteDecision;
};

export type DiscoverySearchResponse = {
  prompt: string;
  product_context_key: string;
  product_context_name: string;
  queries: string[];
  candidates: DiscoveryCandidate[];
  route: ModelRouteDecision;
  notes: string[];
};

export type DiscoveryImportResult = {
  account: AccountSummary;
  existing_account: boolean;
  imported_signal_count: number;
  opportunity_id?: string | null;
  draft_id?: string | null;
};

export type DiscoveryCandidateRecord = {
  id: string;
  discovery_job_id?: string | null;
  status: string;
  confidence_score: number;
  source_count: number;
  first_seen_at: string;
  last_seen_at: string;
  candidate: DiscoveryCandidate;
};

export type DiscoveryJob = {
  id: string;
  product_context_key: string;
  prompt: string;
  cadence_minutes: number;
  limit: number;
  status: string;
  auto_import_threshold: number;
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_result_count: number;
};

export type AgentRunRequest = {
  prompt?: string;
  account_id?: string;
  draft_id?: string;
  automation?: "refresh_opportunity" | "review_draft" | "build_handoff" | "summarize_account";
};

export type AgentResult = {
  prompt: string;
  automation?: string | null;
  summary: string;
  suggested_actions: string[];
  route: ModelRouteDecision;
  citations: Citation[];
  notes: string[];
  entities: Record<string, string | number | null>;
  automation_status: "completed" | "simulated" | "failed";
  used_live_model: boolean;
};

export type AgentJobStatus = {
  id: string;
  job_type: string;
  status: "queued" | "running" | "completed" | "failed";
  account_id?: string | null;
  draft_id?: string | null;
  progress_message: string;
  result?: AgentResult | null;
  error_message: string;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export type SystemStatus = {
  api_status: "ok";
  database_mode: string;
  crm_mode: string;
  llm_mode: string;
  account_count: number;
  product_context_count: number;
  integrations: Record<string, string>;
  notes: string[];
};
