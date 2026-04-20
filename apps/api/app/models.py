from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.app.database import Base


JSONType = JSON


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class ProductContext(Base, TimestampMixin):
    __tablename__ = "product_contexts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(32))
    overview: Mapped[str] = mapped_column(Text)
    icp_segments: Mapped[list[str]] = mapped_column(JSONType, default=list)
    trigger_patterns: Mapped[list[str]] = mapped_column(JSONType, default=list)
    disqualifiers: Mapped[list[str]] = mapped_column(JSONType, default=list)
    approved_claims: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    buyer_personas: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    activation_playbook: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    segment: Mapped[str] = mapped_column(String(80))
    territory: Mapped[str] = mapped_column(String(80))
    pipeline_stage: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    owner_role: Mapped[str] = mapped_column(String(80))
    intent_score: Mapped[float] = mapped_column(Float, default=0.0)
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0)
    next_action: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    signals: Mapped[list["Signal"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    telemetry_events: Mapped[list["TelemetryEvent"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    opportunities: Mapped[list["OpportunityHypothesis"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    drafts: Mapped[list["DraftAsset"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    activity_events: Mapped[list["ActivityEvent"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    activation_briefs: Mapped[list["ActivationBrief"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    nurture_sequences: Mapped[list["NurtureSequence"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    nurture_touches: Mapped[list["NurtureTouch"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(120))
    persona: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(160))
    influence_level: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(Text, default="")

    account: Mapped["Account"] = relationship(back_populates="contacts")


class Signal(Base, TimestampMixin):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    topic_family: Mapped[str] = mapped_column(String(64))
    signal_type: Mapped[str] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(500))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    facts: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    account: Mapped["Account"] = relationship(back_populates="signals")


class TelemetryEvent(Base, TimestampMixin):
    __tablename__ = "telemetry_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(120))
    topic_family: Mapped[str] = mapped_column(String(64), default="product-telemetry.ingested")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    account: Mapped["Account"] = relationship(back_populates="telemetry_events")


class OpportunityHypothesis(Base, TimestampMixin):
    __tablename__ = "opportunity_hypotheses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    product_context_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="research")
    intent_score: Mapped[float] = mapped_column(Float, default=0.0)
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0)
    recommended_action: Mapped[str] = mapped_column(Text)
    stakeholder_map: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    rationale: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    model_route: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    account: Mapped["Account"] = relationship(back_populates="opportunities")


class DraftAsset(Base, TimestampMixin):
    __tablename__ = "draft_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"),
        nullable=True,
    )
    persona: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    edited_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    rationale: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    model_route: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    compliance_receipt: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    account: Mapped["Account"] = relationship(back_populates="drafts")


class ApprovalDecision(Base, TimestampMixin):
    __tablename__ = "approval_decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("draft_assets.id"), index=True)
    reviewer_role: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(Text, default="")


class ActivityEvent(Base, TimestampMixin):
    __tablename__ = "activity_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(160))
    detail: Mapped[str] = mapped_column(Text)

    account: Mapped["Account"] = relationship(back_populates="activity_events")


class ActivationBrief(Base, TimestampMixin):
    __tablename__ = "activation_briefs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    deal_label: Mapped[str] = mapped_column(String(160))
    stage: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    blockers: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    tasks: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    telemetry_highlights: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    stakeholders: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)

    account: Mapped["Account"] = relationship(back_populates="activation_briefs")


class DiscoveryJob(Base, TimestampMixin):
    __tablename__ = "discovery_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_context_key: Mapped[str] = mapped_column(String(64), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    cadence_minutes: Mapped[int] = mapped_column(Integer, default=360)
    limit: Mapped[int] = mapped_column(Integer, default=8)
    status: Mapped[str] = mapped_column(String(32), default="active")
    auto_import_threshold: Mapped[float] = mapped_column(Float, default=0.0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result_count: Mapped[int] = mapped_column(Integer, default=0)


class DiscoveryCandidateInbox(Base, TimestampMixin):
    __tablename__ = "discovery_candidate_inbox"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    discovery_job_id: Mapped[str | None] = mapped_column(ForeignKey("discovery_jobs.id"), nullable=True, index=True)
    canonical_name: Mapped[str] = mapped_column(String(160), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    segment: Mapped[str] = mapped_column(String(80))
    territory: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    product_context_key: Mapped[str] = mapped_column(String(64), index=True)
    interest_score: Mapped[float] = mapped_column(Float, default=0.0)
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    top_signal: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    reasons: Mapped[list[str]] = mapped_column(JSONType, default=list)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    source_prompt: Mapped[str] = mapped_column(Text)
    source_queries: Mapped[list[str]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(32), default="new")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class NurtureSequence(Base, TimestampMixin):
    __tablename__ = "nurture_sequences"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    product_context_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    current_round: Mapped[int] = mapped_column(Integer, default=1)
    max_rounds: Mapped[int] = mapped_column(Integer, default=2)
    cadence_days: Mapped[int] = mapped_column(Integer, default=3)
    next_touch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state_json: Mapped[dict[str, Any]] = mapped_column("state", JSONType, default=dict)
    exit_reason: Mapped[str] = mapped_column(Text, default="")

    account: Mapped["Account"] = relationship(back_populates="nurture_sequences")
    touches: Mapped[list["NurtureTouch"]] = relationship(
        back_populates="sequence",
        cascade="all, delete-orphan",
    )


class NurtureTouch(Base, TimestampMixin):
    __tablename__ = "nurture_touches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sequence_id: Mapped[str] = mapped_column(ForeignKey("nurture_sequences.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    draft_id: Mapped[str | None] = mapped_column(ForeignKey("draft_assets.id"), nullable=True, index=True)
    persona: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(120))
    channel: Mapped[str] = mapped_column(String(32), default="email")
    touch_kind: Mapped[str] = mapped_column(String(64))
    step_order: Mapped[int] = mapped_column(Integer, default=1)
    round_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    auto_generated: Mapped[bool] = mapped_column(Boolean, default=True)

    account: Mapped["Account"] = relationship(back_populates="nurture_touches")
    sequence: Mapped["NurtureSequence"] = relationship(back_populates="touches")


class OperationJob(Base, TimestampMixin):
    __tablename__ = "operation_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="queued")
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    draft_id: Mapped[str | None] = mapped_column(ForeignKey("draft_assets.id"), nullable=True, index=True)
    progress_message: Mapped[str] = mapped_column(Text, default="")
    request_json: Mapped[dict[str, Any]] = mapped_column("request", JSONType, default=dict)
    result_json: Mapped[dict[str, Any] | None] = mapped_column("result", JSONType, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
