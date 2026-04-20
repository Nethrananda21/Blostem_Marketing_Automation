from __future__ import annotations

from apps.api.app import models
from apps.api.app.schemas import (
    AccountBrief,
    AccountSummary,
    AgentResult,
    ActivationBrief,
    ActivityEvent,
    ApprovalDecision,
    CanonicalSignal,
    Citation,
    ComplianceReceipt,
    DiscoveryCandidate,
    DiscoveryCandidateRecord,
    DiscoveryJob,
    DiscoverySignal,
    DraftAsset,
    ModelRouteDecision,
    NurtureSequenceSummary,
    NurtureTouchSummary,
    OperationJobStatus,
    OpportunityHypothesis,
    PersonaBrief,
    QueueItem,
    QueueResponse,
    RationaleStep,
    TelemetryEvent,
    ProductContext,
)


def queue_from_records(
    accounts: list[models.Account],
    opportunities_by_account: dict[str, models.OpportunityHypothesis | None],
    signals_by_account: dict[str, list[models.Signal]],
) -> QueueResponse:
    return QueueResponse(
        items=[
            QueueItem(
                id=account.id,
                name=account.name,
                segment=account.segment,
                pipeline_stage=account.pipeline_stage,
                intent_score=account.intent_score,
                fit_score=account.fit_score,
                freshness_score=account.freshness_score,
                product_context_key=(
                    opportunities_by_account[account.id].product_context_key
                    if opportunities_by_account.get(account.id)
                    else None
                ),
                next_action=account.next_action,
                top_signal=signals_by_account.get(account.id, [None])[0].title
                if signals_by_account.get(account.id)
                else None,
            )
            for account in accounts
        ],
    )


def account_brief_from_records(
    account: models.Account,
    contacts: list[models.Contact],
    signals: list[models.Signal],
    telemetry: list[models.TelemetryEvent],
    opportunities: list[models.OpportunityHypothesis],
    drafts: list[models.DraftAsset],
    nurture_sequences: list[models.NurtureSequence],
    nurture_touches: list[models.NurtureTouch],
    activity: list[models.ActivityEvent],
    activation_briefs: list[models.ActivationBrief],
) -> AccountBrief:
    return AccountBrief(
        account=AccountSummary(
            id=account.id,
            name=account.name,
            segment=account.segment,
            territory=account.territory,
            pipeline_stage=account.pipeline_stage,
            summary=account.summary,
            owner_role=account.owner_role,
            intent_score=account.intent_score,
            fit_score=account.fit_score,
            freshness_score=account.freshness_score,
            next_action=account.next_action,
            last_activity_at=account.last_activity_at,
            metadata=account.metadata_json,
        ),
        contacts=[
            PersonaBrief(
                name=contact.name,
                role=contact.role,
                persona=contact.persona,
                email=contact.email,
                influence_level=contact.influence_level,
                status=contact.status,
                notes=contact.notes,
            )
            for contact in contacts
        ],
        signals=[signal_to_schema(signal) for signal in signals],
        telemetry=[telemetry_to_schema(event) for event in telemetry],
        opportunities=[opportunity_to_schema(opportunity) for opportunity in opportunities],
        drafts=[draft_to_schema(draft) for draft in drafts],
        nurture_sequences=[nurture_sequence_to_schema(sequence) for sequence in nurture_sequences],
        nurture_touches=[nurture_touch_to_schema(touch) for touch in nurture_touches],
        activity=[
            ActivityEvent(
                id=event.id,
                kind=event.kind,
                title=event.title,
                detail=event.detail,
                created_at=event.created_at,
            )
            for event in activity
        ],
        activation_briefs=[activation_to_schema(brief) for brief in activation_briefs],
    )


def account_summary_from_model(account: models.Account) -> AccountSummary:
    return AccountSummary(
        id=account.id,
        name=account.name,
        segment=account.segment,
        territory=account.territory,
        pipeline_stage=account.pipeline_stage,
        summary=account.summary,
        owner_role=account.owner_role,
        intent_score=account.intent_score,
        fit_score=account.fit_score,
        freshness_score=account.freshness_score,
        next_action=account.next_action,
        last_activity_at=account.last_activity_at,
        metadata=account.metadata_json,
    )


def product_context_to_schema(context: models.ProductContext) -> ProductContext:
    return ProductContext(
        id=context.id,
        key=context.key,
        name=context.name,
        version=context.version,
        overview=context.overview,
        icp_segments=context.icp_segments,
        trigger_patterns=context.trigger_patterns,
        disqualifiers=context.disqualifiers,
        approved_claims=context.approved_claims,
        buyer_personas=context.buyer_personas,
        activation_playbook=context.activation_playbook,
    )


def signal_to_schema(signal: models.Signal) -> CanonicalSignal:
    return CanonicalSignal(
        id=signal.id,
        account_id=signal.account_id,
        topic_family=signal.topic_family,
        signal_type=signal.signal_type,
        source_type=signal.source_type,
        title=signal.title,
        summary=signal.summary,
        source_url=signal.source_url,
        detected_at=signal.detected_at,
        facts=signal.facts,
        citations=[Citation(**citation) for citation in signal.citations],
        raw_payload=signal.raw_payload,
    )


def telemetry_to_schema(event: models.TelemetryEvent) -> TelemetryEvent:
    return TelemetryEvent(
        id=event.id,
        account_id=event.account_id,
        event_type=event.event_type,
        topic_family=event.topic_family,
        detected_at=event.detected_at,
        payload=event.payload,
    )


def opportunity_to_schema(opportunity: models.OpportunityHypothesis) -> OpportunityHypothesis:
    return OpportunityHypothesis(
        id=opportunity.id,
        account_id=opportunity.account_id,
        product_context_key=opportunity.product_context_key,
        status=opportunity.status,
        intent_score=opportunity.intent_score,
        fit_score=opportunity.fit_score,
        freshness_score=opportunity.freshness_score,
        recommended_action=opportunity.recommended_action,
        stakeholder_map=opportunity.stakeholder_map,
        rationale=[RationaleStep(**step) for step in opportunity.rationale],
        evidence=[Citation(**citation) for citation in opportunity.evidence],
        model_route=ModelRouteDecision(**opportunity.model_route),
    )


def draft_to_schema(draft: models.DraftAsset) -> DraftAsset:
    receipt = ComplianceReceipt(**draft.compliance_receipt) if draft.compliance_receipt else None
    return DraftAsset(
        id=draft.id,
        account_id=draft.account_id,
        opportunity_id=draft.opportunity_id,
        persona=draft.persona,
        channel=draft.channel,
        subject=draft.subject,
        body=draft.body,
        edited_body=draft.edited_body,
        status=draft.status,
        citations=[Citation(**citation) for citation in draft.citations],
        rationale=[RationaleStep(**step) for step in draft.rationale],
        model_route=ModelRouteDecision(**draft.model_route),
        compliance_receipt=receipt,
    )


def activation_to_schema(brief: models.ActivationBrief) -> ActivationBrief:
    return ActivationBrief(
        id=brief.id,
        account_id=brief.account_id,
        deal_label=brief.deal_label,
        stage=brief.stage,
        summary=brief.summary,
        blockers=brief.blockers,
        tasks=brief.tasks,
        telemetry_highlights=brief.telemetry_highlights,
        stakeholders=brief.stakeholders,
        created_at=brief.created_at,
    )


def nurture_sequence_to_schema(sequence: models.NurtureSequence) -> NurtureSequenceSummary:
    return NurtureSequenceSummary(
        id=sequence.id,
        account_id=sequence.account_id,
        product_context_key=sequence.product_context_key,
        kind=sequence.kind,
        status=sequence.status,
        stage=sequence.stage,
        current_round=sequence.current_round,
        max_rounds=sequence.max_rounds,
        cadence_days=sequence.cadence_days,
        next_touch_at=sequence.next_touch_at,
        last_touched_at=sequence.last_touched_at,
        state=sequence.state_json,
        exit_reason=sequence.exit_reason,
    )


def nurture_touch_to_schema(touch: models.NurtureTouch) -> NurtureTouchSummary:
    return NurtureTouchSummary(
        id=touch.id,
        sequence_id=touch.sequence_id,
        account_id=touch.account_id,
        draft_id=touch.draft_id,
        persona=touch.persona,
        role=touch.role,
        channel=touch.channel,
        touch_kind=touch.touch_kind,
        step_order=touch.step_order,
        round_number=touch.round_number,
        status=touch.status,
        due_at=touch.due_at,
        completed_at=touch.completed_at,
        summary=touch.summary,
        metadata=touch.metadata_json,
        auto_generated=touch.auto_generated,
    )


def discovery_job_to_schema(job: models.DiscoveryJob) -> DiscoveryJob:
    return DiscoveryJob(
        id=job.id,
        product_context_key=job.product_context_key,
        prompt=job.prompt,
        cadence_minutes=job.cadence_minutes,
        limit=job.limit,
        status=job.status,
        auto_import_threshold=job.auto_import_threshold,
        last_run_at=job.last_run_at,
        next_run_at=job.next_run_at,
        last_result_count=job.last_result_count,
    )


def discovery_candidate_record_to_schema(record: models.DiscoveryCandidateInbox) -> DiscoveryCandidateRecord:
    candidate = DiscoveryCandidate(
        id=record.id,
        name=record.name,
        segment=record.segment,
        territory=record.territory,
        summary=record.summary,
        product_context_key=record.product_context_key,
        interest_score=record.interest_score,
        fit_score=record.fit_score,
        freshness_score=record.freshness_score,
        top_signal=record.top_signal,
        reason=record.reason,
        reasons=list(record.reasons or []),
        citations=[Citation(**citation) for citation in record.citations],
        signals=[DiscoverySignal(**signal) for signal in record.signals],
        route=ModelRouteDecision(
            workflow="signal-triage",
            target_profile="complex_reasoner",
            provider="local",
            model="scheduled_discovery_record",
            reason="Stored scheduled-discovery candidate reconstructed from the inbox.",
            thinking=False,
            requires_manual_review_on_failure=True,
        ),
    )
    return DiscoveryCandidateRecord(
        id=record.id,
        discovery_job_id=record.discovery_job_id,
        status=record.status,
        confidence_score=record.confidence_score,
        source_count=record.source_count,
        first_seen_at=record.first_seen_at,
        last_seen_at=record.last_seen_at,
        candidate=candidate,
    )


def operation_job_to_schema(job: models.OperationJob) -> OperationJobStatus:
    return OperationJobStatus(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        account_id=job.account_id,
        draft_id=job.draft_id,
        progress_message=job.progress_message,
        result=AgentResult.model_validate(job.result_json) if job.result_json else None,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
