from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app import models


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


class Repository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_accounts(self) -> Sequence[models.Account]:
        result = await self.session.execute(
            select(models.Account).order_by(
                desc(models.Account.intent_score),
                desc(models.Account.fit_score),
                desc(models.Account.freshness_score),
            ),
        )
        return result.scalars().all()

    async def get_account(self, account_id: str) -> models.Account | None:
        return await self.session.get(models.Account, account_id)

    async def get_account_by_name(self, name: str) -> models.Account | None:
        result = await self.session.execute(
            select(models.Account).where(models.Account.name == name),
        )
        return result.scalar_one_or_none()

    async def list_product_contexts(self) -> Sequence[models.ProductContext]:
        result = await self.session.execute(select(models.ProductContext))
        return result.scalars().all()

    async def count_product_contexts(self) -> int:
        return len(await self.list_product_contexts())

    async def get_product_context(self, key: str) -> models.ProductContext | None:
        result = await self.session.execute(
            select(models.ProductContext).where(models.ProductContext.key == key),
        )
        return result.scalar_one_or_none()

    async def create_product_context(self, payload: dict[str, Any]) -> models.ProductContext:
        context = models.ProductContext(id=_new_id("pc"), **payload)
        self.session.add(context)
        await self.session.commit()
        await self.session.refresh(context)
        return context

    async def create_account(self, payload: dict[str, Any]) -> models.Account:
        account = models.Account(
            id=_new_id("acct"),
            intent_score=0.0,
            fit_score=0.0,
            freshness_score=0.0,
            next_action="Awaiting signals and product context.",
            metadata_json=_json_safe(payload.pop("metadata", {})),
            **payload,
        )
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def count_accounts(self) -> int:
        return len(await self.list_accounts())

    async def create_contact(self, account_id: str, payload: dict[str, Any]) -> models.Contact:
        contact = models.Contact(id=_new_id("ctc"), account_id=account_id, **payload)
        self.session.add(contact)
        await self.session.commit()
        await self.session.refresh(contact)
        return contact

    async def create_signal(self, payload: dict[str, Any]) -> models.Signal:
        payload = dict(payload)
        payload["facts"] = _json_safe(payload.get("facts", {}))
        payload["citations"] = _json_safe(payload.get("citations", []))
        payload["raw_payload"] = _json_safe(payload.get("raw_payload", {}))
        signal = models.Signal(id=_new_id("sig"), **payload)
        self.session.add(signal)
        await self.session.commit()
        await self.session.refresh(signal)
        return signal

    async def create_telemetry_event(self, payload: dict[str, Any]) -> models.TelemetryEvent:
        payload = dict(payload)
        payload["payload"] = _json_safe(payload.get("payload", {}))
        event = models.TelemetryEvent(id=_new_id("tele"), **payload)
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def list_contacts(self, account_id: str) -> Sequence[models.Contact]:
        result = await self.session.execute(
            select(models.Contact).where(models.Contact.account_id == account_id),
        )
        return result.scalars().all()

    async def list_signals(self, account_id: str) -> Sequence[models.Signal]:
        result = await self.session.execute(
            select(models.Signal)
            .where(models.Signal.account_id == account_id)
            .order_by(desc(models.Signal.detected_at)),
        )
        return result.scalars().all()

    async def list_telemetry(self, account_id: str) -> Sequence[models.TelemetryEvent]:
        result = await self.session.execute(
            select(models.TelemetryEvent)
            .where(models.TelemetryEvent.account_id == account_id)
            .order_by(desc(models.TelemetryEvent.detected_at)),
        )
        return result.scalars().all()

    async def list_activity(self, account_id: str) -> Sequence[models.ActivityEvent]:
        result = await self.session.execute(
            select(models.ActivityEvent)
            .where(models.ActivityEvent.account_id == account_id)
            .order_by(desc(models.ActivityEvent.created_at)),
        )
        return result.scalars().all()

    async def list_opportunities(self, account_id: str) -> Sequence[models.OpportunityHypothesis]:
        result = await self.session.execute(
            select(models.OpportunityHypothesis)
            .where(models.OpportunityHypothesis.account_id == account_id)
            .order_by(desc(models.OpportunityHypothesis.created_at)),
        )
        return result.scalars().all()

    async def list_drafts(self, account_id: str) -> Sequence[models.DraftAsset]:
        result = await self.session.execute(
            select(models.DraftAsset)
            .where(models.DraftAsset.account_id == account_id)
            .order_by(desc(models.DraftAsset.created_at)),
        )
        return result.scalars().all()

    async def list_activation_briefs(self, account_id: str) -> Sequence[models.ActivationBrief]:
        result = await self.session.execute(
            select(models.ActivationBrief)
            .where(models.ActivationBrief.account_id == account_id)
            .order_by(desc(models.ActivationBrief.created_at)),
        )
        return result.scalars().all()

    async def list_nurture_sequences(self, account_id: str) -> Sequence[models.NurtureSequence]:
        result = await self.session.execute(
            select(models.NurtureSequence)
            .where(models.NurtureSequence.account_id == account_id)
            .order_by(desc(models.NurtureSequence.updated_at)),
        )
        return result.scalars().all()

    async def list_nurture_touches(self, account_id: str) -> Sequence[models.NurtureTouch]:
        result = await self.session.execute(
            select(models.NurtureTouch)
            .where(models.NurtureTouch.account_id == account_id)
            .order_by(desc(models.NurtureTouch.due_at), desc(models.NurtureTouch.created_at)),
        )
        return result.scalars().all()

    async def get_draft(self, draft_id: str) -> models.DraftAsset | None:
        return await self.session.get(models.DraftAsset, draft_id)

    async def get_activation_brief(self, account_id: str) -> models.ActivationBrief | None:
        result = await self.session.execute(
            select(models.ActivationBrief)
            .where(models.ActivationBrief.account_id == account_id)
            .order_by(desc(models.ActivationBrief.created_at)),
        )
        return result.scalars().first()

    async def create_operation_job(self, payload: dict[str, Any]) -> models.OperationJob:
        payload = dict(payload)
        job = models.OperationJob(
            id=_new_id("job"),
            progress_message=payload.pop("progress_message", "Queued for execution."),
            request_json=_json_safe(payload.pop("request_json", {})),
            **payload,
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get_operation_job(self, job_id: str) -> models.OperationJob | None:
        return await self.session.get(models.OperationJob, job_id)

    async def update_operation_job(self, job: models.OperationJob, **fields: Any) -> models.OperationJob:
        payload = dict(fields)
        if "request_json" in payload:
            payload["request_json"] = _json_safe(payload["request_json"])
        if "result_json" in payload and payload["result_json"] is not None:
            payload["result_json"] = _json_safe(payload["result_json"])
        for key, value in payload.items():
            setattr(job, key, value)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def upsert_opportunity(
        self,
        account_id: str,
        product_context_key: str,
        payload: dict[str, Any],
    ) -> models.OpportunityHypothesis:
        result = await self.session.execute(
            select(models.OpportunityHypothesis)
            .where(models.OpportunityHypothesis.account_id == account_id)
            .where(models.OpportunityHypothesis.product_context_key == product_context_key),
        )
        opportunity = result.scalar_one_or_none()
        if opportunity is None:
            opportunity = models.OpportunityHypothesis(
                id=_new_id("opp"),
                account_id=account_id,
                product_context_key=product_context_key,
                **payload,
            )
            self.session.add(opportunity)
        else:
            for key, value in payload.items():
                setattr(opportunity, key, value)
        await self.session.commit()
        await self.session.refresh(opportunity)
        return opportunity

    async def upsert_draft(
        self,
        account_id: str,
        persona: str,
        payload: dict[str, Any],
    ) -> models.DraftAsset:
        result = await self.session.execute(
            select(models.DraftAsset)
            .where(models.DraftAsset.account_id == account_id)
            .where(models.DraftAsset.persona == persona),
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            draft = models.DraftAsset(id=_new_id("draft"), account_id=account_id, persona=persona, **payload)
            self.session.add(draft)
        else:
            for key, value in payload.items():
                setattr(draft, key, value)
        await self.session.commit()
        await self.session.refresh(draft)
        return draft

    async def create_approval(self, payload: dict[str, Any]) -> models.ApprovalDecision:
        approval = models.ApprovalDecision(id=_new_id("apr"), **payload)
        self.session.add(approval)
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def update_draft(self, draft: models.DraftAsset, **fields: Any) -> models.DraftAsset:
        for key, value in fields.items():
            setattr(draft, key, value)
        await self.session.commit()
        await self.session.refresh(draft)
        return draft

    async def upsert_activation_brief(self, account_id: str, payload: dict[str, Any]) -> models.ActivationBrief:
        brief = await self.get_activation_brief(account_id)
        if brief is None:
            brief = models.ActivationBrief(id=_new_id("brief"), account_id=account_id, **payload)
            self.session.add(brief)
        else:
            for key, value in payload.items():
                setattr(brief, key, value)
        await self.session.commit()
        await self.session.refresh(brief)
        return brief

    async def create_discovery_job(self, payload: dict[str, Any]) -> models.DiscoveryJob:
        job = models.DiscoveryJob(id=_new_id("discjob"), **payload)
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get_discovery_job(self, job_id: str) -> models.DiscoveryJob | None:
        return await self.session.get(models.DiscoveryJob, job_id)

    async def list_discovery_jobs(self) -> Sequence[models.DiscoveryJob]:
        result = await self.session.execute(
            select(models.DiscoveryJob).order_by(desc(models.DiscoveryJob.updated_at)),
        )
        return result.scalars().all()

    async def list_due_discovery_jobs(self, now: datetime) -> Sequence[models.DiscoveryJob]:
        result = await self.session.execute(
            select(models.DiscoveryJob)
            .where(models.DiscoveryJob.status == "active")
            .where(
                (models.DiscoveryJob.next_run_at.is_(None))
                | (models.DiscoveryJob.next_run_at <= now)
            )
            .order_by(models.DiscoveryJob.next_run_at),
        )
        return result.scalars().all()

    async def update_discovery_job(
        self,
        job: models.DiscoveryJob,
        **fields: Any,
    ) -> models.DiscoveryJob:
        for key, value in fields.items():
            setattr(job, key, value)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def upsert_discovery_candidate_record(
        self,
        *,
        job_id: str | None,
        canonical_name: str,
        payload: dict[str, Any],
    ) -> models.DiscoveryCandidateInbox:
        result = await self.session.execute(
            select(models.DiscoveryCandidateInbox)
            .where(models.DiscoveryCandidateInbox.canonical_name == canonical_name)
            .where(models.DiscoveryCandidateInbox.product_context_key == payload["product_context_key"]),
        )
        record = result.scalar_one_or_none()
        now = datetime.now(UTC)
        payload = _json_safe(payload)
        if record is None:
            record = models.DiscoveryCandidateInbox(
                id=_new_id("inbox"),
                discovery_job_id=job_id,
                canonical_name=canonical_name,
                first_seen_at=now,
                last_seen_at=now,
                **payload,
            )
            self.session.add(record)
        else:
            for key, value in payload.items():
                setattr(record, key, value)
            record.discovery_job_id = job_id or record.discovery_job_id
            record.last_seen_at = now
            if record.status == "dismissed":
                record.status = "new"
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def list_discovery_candidate_records(
        self,
        status: str | None = None,
    ) -> Sequence[models.DiscoveryCandidateInbox]:
        query = select(models.DiscoveryCandidateInbox).order_by(
            desc(models.DiscoveryCandidateInbox.interest_score),
            desc(models.DiscoveryCandidateInbox.confidence_score),
            desc(models.DiscoveryCandidateInbox.last_seen_at),
        )
        if status:
            query = query.where(models.DiscoveryCandidateInbox.status == status)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_discovery_candidate_record(
        self,
        record_id: str,
    ) -> models.DiscoveryCandidateInbox | None:
        return await self.session.get(models.DiscoveryCandidateInbox, record_id)

    async def update_discovery_candidate_record(
        self,
        record: models.DiscoveryCandidateInbox,
        **fields: Any,
    ) -> models.DiscoveryCandidateInbox:
        for key, value in fields.items():
            setattr(record, key, value)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def upsert_nurture_sequence(
        self,
        *,
        account_id: str,
        kind: str,
        payload: dict[str, Any],
    ) -> models.NurtureSequence:
        result = await self.session.execute(
            select(models.NurtureSequence)
            .where(models.NurtureSequence.account_id == account_id)
            .where(models.NurtureSequence.kind == kind)
            .where(models.NurtureSequence.status.in_(["active", "paused"])),
        )
        sequence = result.scalar_one_or_none()
        payload = dict(payload)
        if "state_json" in payload:
            payload["state_json"] = _json_safe(payload["state_json"])
        if sequence is None:
            sequence = models.NurtureSequence(
                id=_new_id("seq"),
                account_id=account_id,
                kind=kind,
                **payload,
            )
            self.session.add(sequence)
        else:
            for key, value in payload.items():
                setattr(sequence, key, value)
        await self.session.commit()
        await self.session.refresh(sequence)
        return sequence

    async def list_due_nurture_sequences(self, now: datetime) -> Sequence[models.NurtureSequence]:
        result = await self.session.execute(
            select(models.NurtureSequence)
            .where(models.NurtureSequence.status == "active")
            .where(models.NurtureSequence.next_touch_at.is_not(None))
            .where(models.NurtureSequence.next_touch_at <= now)
            .order_by(models.NurtureSequence.next_touch_at),
        )
        return result.scalars().all()

    async def list_sequence_touches(self, sequence_id: str) -> Sequence[models.NurtureTouch]:
        result = await self.session.execute(
            select(models.NurtureTouch)
            .where(models.NurtureTouch.sequence_id == sequence_id)
            .order_by(models.NurtureTouch.round_number, models.NurtureTouch.step_order),
        )
        return result.scalars().all()

    async def create_nurture_touch(self, payload: dict[str, Any]) -> models.NurtureTouch:
        payload = dict(payload)
        if "metadata_json" in payload:
            payload["metadata_json"] = _json_safe(payload["metadata_json"])
        touch = models.NurtureTouch(id=_new_id("touch"), **payload)
        self.session.add(touch)
        await self.session.commit()
        await self.session.refresh(touch)
        return touch

    async def get_nurture_touch_by_draft(self, draft_id: str) -> models.NurtureTouch | None:
        result = await self.session.execute(
            select(models.NurtureTouch).where(models.NurtureTouch.draft_id == draft_id),
        )
        return result.scalar_one_or_none()

    async def update_nurture_touch(
        self,
        touch: models.NurtureTouch,
        **fields: Any,
    ) -> models.NurtureTouch:
        for key, value in fields.items():
            setattr(touch, key, value)
        await self.session.commit()
        await self.session.refresh(touch)
        return touch

    async def log_activity(self, account_id: str, kind: str, title: str, detail: str) -> models.ActivityEvent:
        event = models.ActivityEvent(
            id=_new_id("act"),
            account_id=account_id,
            kind=kind,
            title=title,
            detail=detail,
            created_at=datetime.now(UTC),
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event
