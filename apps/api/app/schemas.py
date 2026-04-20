from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    label: str
    source_url: str
    claim: str
    excerpt: str | None = None
    published_at: datetime | None = None


class RationaleStep(BaseModel):
    title: str
    detail: str
    weight: float = 0.0


class ProductContext(BaseModel):
    id: str
    key: str
    name: str
    version: str
    overview: str
    icp_segments: list[str]
    trigger_patterns: list[str]
    disqualifiers: list[str]
    approved_claims: list[dict]
    buyer_personas: list[dict]
    activation_playbook: list[dict]


class ProductContextCreateRequest(BaseModel):
    key: str
    name: str
    version: str = "1.0.0"
    overview: str
    icp_segments: list[str] = Field(default_factory=list)
    trigger_patterns: list[str] = Field(default_factory=list)
    disqualifiers: list[str] = Field(default_factory=list)
    approved_claims: list[dict] = Field(default_factory=list)
    buyer_personas: list[dict] = Field(default_factory=list)
    activation_playbook: list[dict] = Field(default_factory=list)


class CanonicalSignal(BaseModel):
    id: str
    account_id: str
    topic_family: str
    signal_type: str
    source_type: str
    title: str
    summary: str
    source_url: str
    detected_at: datetime
    facts: dict
    citations: list[Citation]
    raw_payload: dict = Field(default_factory=dict)


class TelemetryEvent(BaseModel):
    id: str
    account_id: str
    event_type: str
    topic_family: str = "product-telemetry.ingested"
    detected_at: datetime
    payload: dict = Field(default_factory=dict)


class ModelRouteDecision(BaseModel):
    workflow: str
    target_profile: Literal["complex_reasoner", "draft_executor"]
    provider: Literal["nvidia", "openrouter", "local"]
    model: str
    reason: str
    thinking: bool
    requires_manual_review_on_failure: bool = False


class PersonaBrief(BaseModel):
    name: str
    role: str
    persona: str
    email: str
    influence_level: str
    status: str
    notes: str


class OpportunityHypothesis(BaseModel):
    id: str
    account_id: str
    product_context_key: str
    status: str
    intent_score: float
    fit_score: float
    freshness_score: float
    recommended_action: str
    stakeholder_map: list[dict]
    rationale: list[RationaleStep]
    evidence: list[Citation]
    model_route: ModelRouteDecision


class ClaimCheck(BaseModel):
    sentence: str
    sentence_type: Literal["boilerplate", "factual_claim"]
    needs_citation: bool
    supported: bool
    reason: str


class ComplianceReceipt(BaseModel):
    passed: bool
    issues: list[str]
    claim_checks: list[ClaimCheck]
    route: ModelRouteDecision
    reviewed_at: datetime


class DraftAsset(BaseModel):
    id: str
    account_id: str
    opportunity_id: str | None = None
    persona: str
    channel: str
    subject: str
    body: str
    edited_body: str | None = None
    status: str
    citations: list[Citation]
    rationale: list[RationaleStep]
    model_route: ModelRouteDecision
    compliance_receipt: ComplianceReceipt | None = None


class ApprovalDecision(BaseModel):
    id: str
    draft_id: str
    reviewer_role: str
    decision: Literal["approved", "rejected"]
    notes: str = ""
    created_at: datetime


class ActivationBrief(BaseModel):
    id: str
    account_id: str
    deal_label: str
    stage: str
    summary: str
    blockers: list[dict]
    tasks: list[dict]
    telemetry_highlights: list[dict]
    stakeholders: list[dict]
    created_at: datetime


class ActivityEvent(BaseModel):
    id: str
    kind: str
    title: str
    detail: str
    created_at: datetime


class NurtureTouchSummary(BaseModel):
    id: str
    sequence_id: str
    account_id: str
    draft_id: str | None = None
    persona: str
    role: str
    channel: str
    touch_kind: str
    step_order: int
    round_number: int
    status: str
    due_at: datetime | None = None
    completed_at: datetime | None = None
    summary: str
    metadata: dict = Field(default_factory=dict)
    auto_generated: bool = True


class NurtureSequenceSummary(BaseModel):
    id: str
    account_id: str
    product_context_key: str | None = None
    kind: Literal["prospect_outreach", "post_sale_activation"]
    status: str
    stage: str
    current_round: int
    max_rounds: int
    cadence_days: int
    next_touch_at: datetime | None = None
    last_touched_at: datetime | None = None
    state: dict = Field(default_factory=dict)
    exit_reason: str = ""


class AccountSummary(BaseModel):
    id: str
    name: str
    segment: str
    territory: str
    pipeline_stage: str
    summary: str
    owner_role: str
    intent_score: float
    fit_score: float
    freshness_score: float
    next_action: str
    last_activity_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class AccountCreateRequest(BaseModel):
    name: str
    segment: str
    territory: str
    pipeline_stage: str = "Research"
    summary: str
    owner_role: str = "rep"
    metadata: dict = Field(default_factory=dict)


class ContactCreateRequest(BaseModel):
    name: str
    role: str
    persona: str
    email: str
    influence_level: str = "medium"
    status: str = "research"
    notes: str = ""


class AccountBrief(BaseModel):
    account: AccountSummary
    contacts: list[PersonaBrief]
    signals: list[CanonicalSignal]
    telemetry: list[TelemetryEvent]
    opportunities: list[OpportunityHypothesis]
    drafts: list[DraftAsset]
    nurture_sequences: list[NurtureSequenceSummary]
    nurture_touches: list[NurtureTouchSummary]
    activity: list[ActivityEvent]
    activation_briefs: list[ActivationBrief]


class QueueItem(BaseModel):
    id: str
    name: str
    segment: str
    pipeline_stage: str
    intent_score: float
    fit_score: float
    freshness_score: float
    product_context_key: str | None = None
    next_action: str
    top_signal: str | None = None


class QueueResponse(BaseModel):
    items: list[QueueItem]


class DiscoverySignal(BaseModel):
    topic_family: str = "market-signal.ingested"
    signal_type: str
    source_type: str
    title: str
    summary: str
    source_url: str
    detected_at: datetime
    facts: dict = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)
    raw_payload: dict = Field(default_factory=dict)


class DiscoveryCandidate(BaseModel):
    id: str
    name: str
    segment: str
    territory: str
    summary: str
    product_context_key: str
    interest_score: float
    fit_score: float
    freshness_score: float
    top_signal: str
    reason: str
    reasons: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    signals: list[DiscoverySignal] = Field(default_factory=list)
    route: ModelRouteDecision


class DiscoveryCandidateRecord(BaseModel):
    id: str
    discovery_job_id: str | None = None
    status: str
    confidence_score: float
    source_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    candidate: DiscoveryCandidate


class DiscoverySearchRequest(BaseModel):
    prompt: str
    product_context_key: str | None = None
    limit: int = 8


class DiscoverySearchResponse(BaseModel):
    prompt: str
    product_context_key: str
    product_context_name: str
    queries: list[str]
    candidates: list[DiscoveryCandidate]
    route: ModelRouteDecision
    notes: list[str] = Field(default_factory=list)


class DiscoveryImportRequest(BaseModel):
    candidate: DiscoveryCandidate
    candidate_record_id: str | None = None
    refresh_workflow: bool = True


class DiscoveryImportResult(BaseModel):
    account: AccountSummary
    existing_account: bool
    imported_signal_count: int
    opportunity_id: str | None = None
    draft_id: str | None = None


class DiscoveryJob(BaseModel):
    id: str
    product_context_key: str
    prompt: str
    cadence_minutes: int
    limit: int
    status: str
    auto_import_threshold: float = 0.0
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    last_result_count: int = 0


class DiscoveryJobCreateRequest(BaseModel):
    product_context_key: str
    prompt: str
    cadence_minutes: int = 360
    limit: int = 8
    auto_import_threshold: float = 0.0


class WorkflowRefreshRequest(BaseModel):
    account_id: str


class SignalIngestRequest(BaseModel):
    account_id: str
    topic_family: str = "market-signal.ingested"
    signal_type: str
    source_type: str
    title: str
    summary: str
    source_url: str
    detected_at: datetime
    facts: dict = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)
    raw_payload: dict = Field(default_factory=dict)


class TelemetryIngestRequest(BaseModel):
    account_id: str
    event_type: str
    topic_family: str = "product-telemetry.ingested"
    detected_at: datetime
    payload: dict = Field(default_factory=dict)


class DraftEditRequest(BaseModel):
    body: str


class DraftDecisionRequest(BaseModel):
    reviewer_role: str
    notes: str = ""


class AgentRunRequest(BaseModel):
    prompt: str = ""
    account_id: str | None = None
    draft_id: str | None = None
    automation: Literal[
        "refresh_opportunity",
        "review_draft",
        "build_handoff",
        "summarize_account",
    ] | None = None


class AgentResult(BaseModel):
    prompt: str
    automation: str | None = None
    summary: str
    suggested_actions: list[str]
    route: ModelRouteDecision
    citations: list[Citation]
    notes: list[str]
    entities: dict
    automation_status: Literal["completed", "simulated", "failed"]
    used_live_model: bool


class OperationJobStatus(BaseModel):
    id: str
    job_type: str
    status: Literal["queued", "running", "completed", "failed"]
    account_id: str | None = None
    draft_id: str | None = None
    progress_message: str = ""
    result: AgentResult | None = None
    error_message: str = ""
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SystemStatus(BaseModel):
    api_status: Literal["ok"]
    database_mode: str
    crm_mode: str
    llm_mode: str
    account_count: int
    product_context_count: int
    integrations: dict[str, str]
    notes: list[str]
