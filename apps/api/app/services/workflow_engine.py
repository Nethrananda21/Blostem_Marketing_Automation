from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from apps.api.app import models
from apps.api.app.repositories import Repository
from apps.api.app.schemas import Citation, ComplianceReceipt, ModelRouteDecision
from apps.api.app.services.compliance import ComplianceService
from apps.api.app.services.model_gateway import ModelGateway
from apps.api.app.services.routing import ModelRouter


class WorkflowRunner:
    def __init__(
        self,
        repository: Repository,
        router: ModelRouter,
        model_gateway: ModelGateway,
        compliance_service: ComplianceService,
    ) -> None:
        self.repository = repository
        self.router = router
        self.model_gateway = model_gateway
        self.compliance_service = compliance_service

    async def refresh_opportunity(self, account_id: str) -> tuple[models.OpportunityHypothesis, models.DraftAsset]:
        account = await self.repository.get_account(account_id)
        if account is None:
            raise ValueError("Account not found")
        signals = list(await self.repository.list_signals(account_id))
        contacts = list(await self.repository.list_contacts(account_id))
        product_contexts = list(await self.repository.list_product_contexts())
        selected_context = self._select_product_context(account, signals, product_contexts)
        evidence = self._collect_evidence(signals)
        triage_route = self.router.decide(
            "signal-triage",
            evidence_count=len(evidence),
            tool_count=2,
            ambiguous=selected_context is None,
            high_risk=True,
        )
        if selected_context is None:
            raise ValueError("No product context available")
        opportunity_payload = self._build_opportunity_payload(account, contacts, selected_context, evidence, triage_route)
        opportunity = await self.repository.upsert_opportunity(account_id, selected_context.key, opportunity_payload)

        committee = self._target_committee(contacts, selected_context)
        drafts: list[models.DraftAsset] = []
        for member in committee:
            draft = await self._draft_for_persona(
                account=account,
                persona=member["persona"],
                product_name=selected_context.name,
                recommended_action=opportunity.recommended_action,
                evidence=evidence,
                opportunity_id=opportunity.id,
                rationale=opportunity_payload["rationale"],
                touch_kind="initial_outreach",
            )
            drafts.append(draft)

        await self._ensure_committee_sequence(
            account=account,
            context=selected_context,
            committee=committee,
            drafts=drafts,
        )
        account.intent_score = opportunity.intent_score
        account.fit_score = opportunity.fit_score
        account.freshness_score = opportunity.freshness_score
        account.next_action = (
            f"Review the {len(drafts)}-persona committee sequence, then approve compliant outreach."
        )
        account.last_activity_at = datetime.now(UTC)
        await self.repository.session.commit()
        await self.repository.log_activity(
            account_id,
            "workflow",
            "Opportunity refreshed",
            f"Built hypothesis for {selected_context.name} and updated {len(drafts)} committee drafts.",
        )
        return opportunity, drafts[0]

    async def build_handoff(self, account_id: str) -> models.ActivationBrief:
        account = await self.repository.get_account(account_id)
        if account is None:
            raise ValueError("Account not found")
        telemetry = list(await self.repository.list_telemetry(account_id))
        contacts = list(await self.repository.list_contacts(account_id))
        tasks = [
            {"title": "Schedule security discovery", "owner": "rep", "window": "Day 1-3"},
            {"title": "Confirm data-flow review with InfoSec", "owner": "compliance", "window": "Day 3-7"},
            {"title": "Map deployment dependencies", "owner": "solutions", "window": "Day 7-14"},
        ]
        blockers = [
            {"title": "Procurement review may lag technical approval", "severity": "medium"},
            {"title": "Activation depends on named InfoSec sponsor", "severity": "high"},
        ]
        highlights = [
            {
                "title": event.event_type,
                "detail": str(event.payload),
                "detected_at": event.detected_at.isoformat(),
            }
            for event in telemetry[:4]
        ]
        payload = {
            "deal_label": f"{account.name} pilot activation",
            "stage": "closed_won_handoff",
            "summary": (
                f"Carry momentum into implementation by aligning the technical sponsor group, "
                f"front-loading compliance review, and anchoring the kickoff to the most recent usage signals."
            ),
            "blockers": blockers,
            "tasks": tasks,
            "telemetry_highlights": highlights,
            "stakeholders": [
                {
                    "name": contact.name,
                    "role": contact.role,
                    "persona": contact.persona,
                    "status": contact.status,
                }
                for contact in contacts
            ],
        }
        brief = await self.repository.upsert_activation_brief(account_id, payload)
        await self._ensure_post_sale_sequence(account)
        await self.repository.log_activity(
            account_id,
            "handoff",
            "Closed-won handoff created",
            "Generated a 30-day activation brief with blockers and telemetry highlights.",
        )
        return brief

    async def run_due_nurture_sequences(self) -> dict[str, str]:
        due_sequences = list(await self.repository.list_due_nurture_sequences(datetime.now(UTC)))
        results: dict[str, str] = {}
        for sequence in due_sequences:
            account = await self.repository.get_account(sequence.account_id)
            if account is None:
                results[sequence.id] = "skipped_missing_account"
                continue
            if sequence.kind == "prospect_outreach":
                results[sequence.id] = await self._run_prospect_follow_up(account, sequence)
            elif sequence.kind == "post_sale_activation":
                results[sequence.id] = await self._create_activation_nudge(account, sequence, "scheduled_check")
            else:
                results[sequence.id] = "skipped_unknown_sequence"
        return results

    async def evaluate_post_sale_nudge(self, account_id: str) -> str:
        account = await self.repository.get_account(account_id)
        if account is None:
            raise ValueError("Account not found")
        telemetry = list(await self.repository.list_telemetry(account_id))
        activation_brief = await self.repository.get_activation_brief(account_id)
        if activation_brief is None and account.pipeline_stage.lower() not in {"closed won", "closed_won", "closed-won"}:
            return "no_handoff"

        completed_events = {"login_completed", "workspace_activated", "activation_completed", "first_value_reached"}
        if any(event.event_type in completed_events for event in telemetry):
            sequence = await self.repository.upsert_nurture_sequence(
                account_id=account.id,
                kind="post_sale_activation",
                payload={
                    "product_context_key": None,
                    "status": "completed",
                    "stage": "activated",
                    "current_round": 1,
                    "max_rounds": 3,
                    "cadence_days": 3,
                    "next_touch_at": None,
                    "last_touched_at": datetime.now(UTC),
                    "state_json": {"completed_event": telemetry[0].event_type if telemetry else "activation_completed"},
                    "exit_reason": "Telemetry showed activation completion.",
                },
            )
            return f"completed:{sequence.id}"

        sequence = await self._ensure_post_sale_sequence(account)
        return await self._create_activation_nudge(account, sequence, "telemetry_trigger")

    def recheck_compliance(
        self,
        text: str,
        citations: list[Citation],
        route: ModelRouteDecision,
    ) -> ComplianceReceipt:
        return self.compliance_service.review(draft_text=text, citations=citations, route=route)

    def _select_product_context(
        self,
        account: models.Account,
        signals: list[models.Signal],
        contexts: list[models.ProductContext],
    ) -> models.ProductContext | None:
        best_context: models.ProductContext | None = None
        best_score = -1
        signal_blob = " ".join(f"{signal.title} {signal.summary}" for signal in signals).lower()
        for context in contexts:
            score = 0
            if account.segment.lower() in [segment.lower() for segment in context.icp_segments]:
                score += 3
            for pattern in context.trigger_patterns:
                if pattern.lower() in signal_blob:
                    score += 2
            for disqualifier in context.disqualifiers:
                if disqualifier.lower() in signal_blob:
                    score -= 1
            if score > best_score:
                best_context = context
                best_score = score
        return best_context

    def _collect_evidence(self, signals: list[models.Signal]) -> list[Citation]:
        evidence: list[Citation] = []
        for signal in signals[:6]:
            for citation in signal.citations:
                evidence.append(Citation(**citation))
            if not signal.citations:
                evidence.append(
                    Citation(
                        label=signal.title,
                        source_url=signal.source_url,
                        claim=signal.summary,
                        excerpt=signal.summary,
                        published_at=signal.detected_at,
                    ),
                )
        return evidence

    def _build_opportunity_payload(
        self,
        account: models.Account,
        contacts: list[models.Contact],
        context: models.ProductContext,
        evidence: list[Citation],
        route: ModelRouteDecision,
    ) -> dict:
        intent_score = min(98.0, 55.0 + len(evidence) * 5)
        fit_score = 92.0 if account.segment.lower() in [segment.lower() for segment in context.icp_segments] else 74.0
        freshness_score = 88.0 if evidence else 60.0
        rationale = [
            {
                "title": "Market trigger alignment",
                "detail": f"{account.name} shows trigger patterns matching {context.name}.",
                "weight": 0.46,
            },
            {
                "title": "Persona coverage",
                "detail": f"Buying committee mapped across {len(contacts)} tracked stakeholders.",
                "weight": 0.24,
            },
            {
                "title": "Compliance-safe narrative",
                "detail": "Available sources support a focused outreach sequence without unsupported claims.",
                "weight": 0.30,
            },
        ]
        stakeholders = [
            {
                "name": contact.name,
                "role": contact.role,
                "persona": contact.persona,
                "influence_level": contact.influence_level,
                "status": contact.status,
            }
            for contact in contacts
        ]
        recommended_action = (
            f"Call the {contacts[0].role if contacts else 'technology lead'} today with a source-backed "
            f"{context.name} brief anchored to the latest trigger."
        )
        return {
            "status": "draft",
            "intent_score": intent_score,
            "fit_score": fit_score,
            "freshness_score": freshness_score,
            "recommended_action": recommended_action,
            "stakeholder_map": stakeholders,
            "rationale": rationale,
            "evidence": [citation.model_dump(mode="json") for citation in evidence],
            "model_route": route.model_dump(mode="json"),
        }

    async def _draft_for_persona(
        self,
        *,
        account: models.Account,
        persona: str,
        product_name: str,
        recommended_action: str,
        evidence: list[Citation],
        opportunity_id: str | None,
        rationale: list[dict],
        touch_kind: str,
    ) -> models.DraftAsset:
        draft_route = self.router.decide(
            "draft-generation",
            evidence_count=len(evidence),
            tool_count=1,
        )
        try:
            generated = await self.model_gateway.generate_draft(
                route=draft_route,
                account_name=account.name,
                persona=persona,
                product_name=product_name,
                recommended_action=recommended_action,
                citations=evidence,
            )
            effective_draft_route = cast(ModelRouteDecision, generated.get("route", draft_route))
        except RuntimeError:
            generated, effective_draft_route = self._build_local_draft_fallback(
                account_name=account.name,
                persona=persona,
                product_name=product_name,
                recommended_action=recommended_action,
                citations=evidence,
                touch_kind=touch_kind,
            )
        compliance_route = self.router.decide(
            "compliance-review",
            evidence_count=len(evidence),
            tool_count=1,
            high_risk=True,
        )
        compliance_receipt = self.compliance_service.review(
            draft_text=generated["body"],
            citations=evidence,
            route=compliance_route,
        )
        return await self.repository.upsert_draft(
            account.id,
            persona,
            {
                "opportunity_id": opportunity_id,
                "channel": "email",
                "subject": generated["subject"],
                "body": generated["body"],
                "edited_body": None,
                "status": "pending_human_approval" if compliance_receipt.passed else "needs_revision",
                "citations": [citation.model_dump(mode="json") for citation in evidence],
                "rationale": rationale,
                "model_route": effective_draft_route.model_dump(mode="json"),
                "compliance_receipt": compliance_receipt.model_dump(mode="json"),
            },
        )

    async def _ensure_committee_sequence(
        self,
        *,
        account: models.Account,
        context: models.ProductContext,
        committee: list[dict[str, str]],
        drafts: list[models.DraftAsset],
    ) -> models.NurtureSequence:
        now = datetime.now(UTC)
        sequence = await self.repository.upsert_nurture_sequence(
            account_id=account.id,
            kind="prospect_outreach",
            payload={
                "product_context_key": context.key,
                "status": "active",
                "stage": "committee_sequence_ready",
                "current_round": 1,
                "max_rounds": 3,
                "cadence_days": 3,
                "next_touch_at": now + timedelta(days=3),
                "last_touched_at": now,
                "state_json": {
                    "committee": committee,
                    "product_name": context.name,
                },
                "exit_reason": "",
            },
        )
        existing = list(await self.repository.list_sequence_touches(sequence.id))
        existing_keys = {(touch.persona, touch.round_number, touch.touch_kind) for touch in existing}
        role_by_persona = {member["persona"]: member["role"] for member in committee}
        for index, draft in enumerate(drafts, start=1):
            key = (draft.persona, 1, "initial_outreach")
            if key in existing_keys:
                continue
            await self.repository.create_nurture_touch(
                {
                    "sequence_id": sequence.id,
                    "account_id": account.id,
                    "draft_id": draft.id,
                    "persona": draft.persona,
                    "role": role_by_persona.get(draft.persona, draft.persona),
                    "channel": draft.channel,
                    "touch_kind": "initial_outreach",
                    "step_order": index,
                    "round_number": 1,
                    "status": "ready_for_review",
                    "due_at": now,
                    "summary": f"Initial {draft.persona} outreach awaiting human approval.",
                    "metadata_json": {"subject": draft.subject},
                    "auto_generated": True,
                },
            )
        return sequence

    async def _ensure_post_sale_sequence(self, account: models.Account) -> models.NurtureSequence:
        now = datetime.now(UTC)
        return await self.repository.upsert_nurture_sequence(
            account_id=account.id,
            kind="post_sale_activation",
            payload={
                "product_context_key": None,
                "status": "active",
                "stage": "activation_watch",
                "current_round": 1,
                "max_rounds": 3,
                "cadence_days": 3,
                "next_touch_at": now + timedelta(days=3),
                "last_touched_at": None,
                "state_json": {"goal": "Detect activation stall and generate rep-approved nudges."},
                "exit_reason": "",
            },
        )

    async def _run_prospect_follow_up(
        self,
        account: models.Account,
        sequence: models.NurtureSequence,
    ) -> str:
        if sequence.current_round >= sequence.max_rounds:
            await self.repository.upsert_nurture_sequence(
                account_id=account.id,
                kind=sequence.kind,
                payload={
                    "product_context_key": sequence.product_context_key,
                    "status": "paused",
                    "stage": "max_rounds_reached",
                    "current_round": sequence.current_round,
                    "max_rounds": sequence.max_rounds,
                    "cadence_days": sequence.cadence_days,
                    "next_touch_at": None,
                    "last_touched_at": datetime.now(UTC),
                    "state_json": sequence.state_json,
                    "exit_reason": "Maximum nurture rounds reached; needs human review.",
                },
            )
            return "paused_max_rounds"

        contacts = list(await self.repository.list_contacts(account.id))
        contexts = list(await self.repository.list_product_contexts())
        context = next((item for item in contexts if item.key == sequence.product_context_key), contexts[0] if contexts else None)
        if context is None:
            return "skipped_no_product_context"
        signals = list(await self.repository.list_signals(account.id))
        evidence = self._collect_evidence(signals)
        committee = self._target_committee(contacts, context)
        next_round = sequence.current_round + 1
        rationale = [
            {
                "title": "Nurture follow-up",
                "detail": f"Round {next_round} follow-up generated from the active sequence state.",
                "weight": 1.0,
            },
        ]
        for index, member in enumerate(committee, start=1):
            draft = await self._draft_for_persona(
                account=account,
                persona=member["persona"],
                product_name=context.name,
                recommended_action=f"Send a concise round {next_round} follow-up to the {member['role']}.",
                evidence=evidence,
                opportunity_id=None,
                rationale=rationale,
                touch_kind="follow_up",
            )
            await self.repository.create_nurture_touch(
                {
                    "sequence_id": sequence.id,
                    "account_id": account.id,
                    "draft_id": draft.id,
                    "persona": member["persona"],
                    "role": member["role"],
                    "channel": "email",
                    "touch_kind": "follow_up",
                    "step_order": index,
                    "round_number": next_round,
                    "status": "ready_for_review",
                    "due_at": datetime.now(UTC),
                    "summary": f"Round {next_round} follow-up for {member['persona']} awaiting approval.",
                    "metadata_json": {"subject": draft.subject},
                    "auto_generated": True,
                },
            )
        await self.repository.upsert_nurture_sequence(
            account_id=account.id,
            kind=sequence.kind,
            payload={
                "product_context_key": sequence.product_context_key,
                "status": "active",
                "stage": "follow_up_ready",
                "current_round": next_round,
                "max_rounds": sequence.max_rounds,
                "cadence_days": sequence.cadence_days,
                "next_touch_at": datetime.now(UTC) + timedelta(days=sequence.cadence_days),
                "last_touched_at": datetime.now(UTC),
                "state_json": sequence.state_json,
                "exit_reason": "",
            },
        )
        await self.repository.log_activity(
            account.id,
            "nurture",
            "Follow-up sequence generated",
            f"Generated round {next_round} committee follow-ups for human approval.",
        )
        return "follow_up_ready"

    async def _create_activation_nudge(
        self,
        account: models.Account,
        sequence: models.NurtureSequence,
        trigger: str,
    ) -> str:
        existing = list(await self.repository.list_sequence_touches(sequence.id))
        if any(touch.status in {"ready_for_review", "pending_human_approval"} for touch in existing):
            return "pending_nudge_exists"

        telemetry = list(await self.repository.list_telemetry(account.id))
        latest = telemetry[0].event_type if telemetry else "no_recent_activation_event"
        route = self.router.decide("draft-generation", evidence_count=0, tool_count=1)
        subject = f"{account.name}: activation next steps"
        body = "\n".join(
            [
                "Hi there,",
                "",
                "Sharing a quick activation checkpoint so we can keep the rollout moving.",
                f"Our latest internal telemetry checkpoint is: {latest}.",
                "Would it help to schedule a short technical kickoff and confirm the next setup owner?",
                "",
                "Best,",
                "Blostem",
            ],
        )
        compliance_route = self.router.decide("compliance-review", evidence_count=0, tool_count=1, high_risk=True)
        compliance_receipt = self.compliance_service.review(
            draft_text=body,
            citations=[],
            route=compliance_route,
        )
        draft = await self.repository.upsert_draft(
            account.id,
            "Activation",
            {
                "opportunity_id": None,
                "channel": "email",
                "subject": subject,
                "body": body,
                "edited_body": None,
                "status": "pending_human_approval" if compliance_receipt.passed else "needs_revision",
                "citations": [],
                "rationale": [
                    {
                        "title": "Telemetry-triggered nudge",
                        "detail": f"Generated because activation sequence observed {latest}.",
                        "weight": 1.0,
                    },
                ],
                "model_route": route.model_dump(mode="json"),
                "compliance_receipt": compliance_receipt.model_dump(mode="json"),
            },
        )
        next_round = min(sequence.current_round + 1, sequence.max_rounds)
        await self.repository.create_nurture_touch(
            {
                "sequence_id": sequence.id,
                "account_id": account.id,
                "draft_id": draft.id,
                "persona": "Activation",
                "role": "Customer success owner",
                "channel": "email",
                "touch_kind": "activation_nudge",
                "step_order": len(existing) + 1,
                "round_number": sequence.current_round,
                "status": "ready_for_review",
                "due_at": datetime.now(UTC),
                "summary": "Activation nudge generated for rep approval.",
                "metadata_json": {"trigger": trigger, "latest_telemetry": latest},
                "auto_generated": True,
            },
        )
        await self.repository.upsert_nurture_sequence(
            account_id=account.id,
            kind=sequence.kind,
            payload={
                "product_context_key": sequence.product_context_key,
                "status": "active" if next_round < sequence.max_rounds else "paused",
                "stage": "activation_nudge_ready",
                "current_round": next_round,
                "max_rounds": sequence.max_rounds,
                "cadence_days": sequence.cadence_days,
                "next_touch_at": datetime.now(UTC) + timedelta(days=sequence.cadence_days)
                if next_round < sequence.max_rounds
                else None,
                "last_touched_at": datetime.now(UTC),
                "state_json": sequence.state_json,
                "exit_reason": "" if next_round < sequence.max_rounds else "Maximum activation nudges reached.",
            },
        )
        await self.repository.log_activity(
            account.id,
            "activation",
            "Activation nudge generated",
            f"Created a post-sale nudge draft from {trigger}.",
        )
        return "activation_nudge_ready"

    def _target_committee(
        self,
        contacts: list[models.Contact],
        context: models.ProductContext,
    ) -> list[dict[str, str]]:
        committee: list[dict[str, str]] = []
        seen: set[str] = set()
        for contact in contacts:
            persona = self._normalize_persona(contact.persona or contact.role)
            if persona in seen:
                continue
            seen.add(persona)
            committee.append({"persona": persona, "role": contact.role})

        for persona_data in context.buyer_personas:
            raw_persona = str(persona_data.get("persona") or persona_data.get("name") or persona_data.get("role") or "")
            persona = self._normalize_persona(raw_persona)
            if persona and persona not in seen:
                seen.add(persona)
                committee.append({"persona": persona, "role": str(persona_data.get("role") or persona)})

        defaults = [
            {"persona": "CTO", "role": "Chief Technology Officer"},
            {"persona": "CFO", "role": "Chief Financial Officer"},
            {"persona": "Legal", "role": "Legal or Compliance Lead"},
        ]
        for item in defaults:
            if item["persona"] not in seen:
                seen.add(item["persona"])
                committee.append(item)
        ordered = sorted(committee, key=lambda item: {"CTO": 0, "CFO": 1, "Legal": 2}.get(item["persona"], 3))
        return ordered[:5]

    def _normalize_persona(self, value: str) -> str:
        normalized = value.strip().lower()
        if "chief technology" in normalized or normalized in {"cto", "technology", "tech"}:
            return "CTO"
        if "chief financial" in normalized or normalized in {"cfo", "finance"}:
            return "CFO"
        if "legal" in normalized or "compliance" in normalized or "risk" in normalized:
            return "Legal"
        if "security" in normalized or "ciso" in normalized:
            return "CTO"
        return value.strip()[:32] or "CTO"

    def _build_local_draft_fallback(
        self,
        *,
        account_name: str,
        persona: str,
        product_name: str,
        recommended_action: str,
        citations: list[Citation],
        touch_kind: str = "initial_outreach",
    ) -> tuple[dict[str, str], ModelRouteDecision]:
        evidence_lines = [citation.claim for citation in citations[:2]]
        while len(evidence_lines) < 2:
            evidence_lines.append("Recent public developments were reviewed before outreach.")

        persona_bridge = {
            "CTO": "current platform and control priorities",
            "CFO": "current operating and control priorities",
            "Legal": "current review and governance priorities",
            "Activation": "current activation and rollout priorities",
        }.get(persona, "current priorities")

        subject_prefix = "Follow-up" if touch_kind == "follow_up" else "Recent public developments"
        subject = f"{account_name}: {subject_prefix.lower()}"
        body = "\n".join(
            [
                "Hi there,",
                "",
                f"I noticed two recent public developments involving {account_name}:",
                f"- {evidence_lines[0]}",
                f"- {evidence_lines[1]}",
                "",
                f"Given those developments, it may be useful to compare notes on {persona_bridge}.",
                "If helpful, I can send a short note before a call.",
                "",
                "Best,",
                "Blostem",
            ],
        )

        route = ModelRouteDecision(
            workflow="draft-generation",
            target_profile="draft_executor",
            provider="local",
            model="deterministic_template",
            reason="Local deterministic fallback used because live draft providers were unavailable.",
            thinking=False,
            requires_manual_review_on_failure=True,
        )
        return {"subject": subject, "body": body}, route
