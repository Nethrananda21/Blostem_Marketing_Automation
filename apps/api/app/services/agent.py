from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from apps.api.app import models
from apps.api.app.config import Settings
from apps.api.app.repositories import Repository
from apps.api.app.schemas import AgentResult, AgentRunRequest, Citation, ModelRouteDecision, SystemStatus
from apps.api.app.services.discovery import classify_signal
from apps.api.app.services.live_search import LiveCompanyResearchFinding, LiveCompanyResearchTool
from apps.api.app.services.model_gateway import ModelGateway
from apps.api.app.services.routing import ModelRouter
from apps.api.app.services.workflow_engine import WorkflowRunner


class AgentService:
    def __init__(
        self,
        *,
        repository: Repository,
        runner: WorkflowRunner,
        router: ModelRouter,
        model_gateway: ModelGateway,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.runner = runner
        self.router = router
        self.model_gateway = model_gateway
        self.settings = settings
        self.live_research_tool = LiveCompanyResearchTool(settings)

    async def run(self, request: AgentRunRequest) -> AgentResult:
        draft = await self.repository.get_draft(request.draft_id) if request.draft_id else None
        account_id = request.account_id or (draft.account_id if draft else None)
        account = await self.repository.get_account(account_id) if account_id else None
        queue_context = await self._queue_context() if account is None else []
        signals = list(await self.repository.list_signals(account.id)) if account else []
        contacts = list(await self.repository.list_contacts(account.id)) if account else []
        opportunities = list(await self.repository.list_opportunities(account.id)) if account else []
        drafts = list(await self.repository.list_drafts(account.id)) if account else []
        handoffs = list(await self.repository.list_activation_briefs(account.id)) if account else []
        citations = self._collect_citations(signals, draft)
        if account is None:
            citations = self._extend_citations_with_queue(citations, queue_context)
        live_research_notes: list[str] = []
        live_research_saved_signal_count = 0

        if account is not None and self._should_use_live_research(request.prompt):
            research_route = self.router.decide(
                "agent-live-research",
                evidence_count=max(len(citations), 1),
                tool_count=2,
                ambiguous=True,
                high_risk=self._is_high_risk_research_prompt(request.prompt),
            )
            findings = await self.live_research_tool.live_company_research(
                company_name=account.name,
                prompt=request.prompt,
                limit=self.settings.live_search_max_results,
            )
            live_research_saved_signal_count = await self._save_live_research_findings(
                account=account,
                findings=findings,
            )
            if findings:
                signals = list(await self.repository.list_signals(account.id))
                citations = self._collect_citations(signals, draft)
                live_research_notes.append(
                    f"Used live_company_research and saved {live_research_saved_signal_count} new cited market signals."
                )
                live_research_notes.append(
                    "The live-search tool is deterministic and runs before model synthesis; raw hidden reasoning is not exposed."
                )
            else:
                live_research_notes.append("live_company_research ran but returned no usable cited results.")
            if research_route.provider == "nvidia":
                live_research_notes.append("Routed live research synthesis to the complex_reasoner profile.")

        if request.automation == "refresh_opportunity":
            if account is None:
                raise ValueError("Account context is required for refresh automation.")
            opportunity, refreshed_draft = await self.runner.refresh_opportunity(account.id)
            return AgentResult(
                prompt=request.prompt,
                automation=request.automation,
                summary=(
                    f"Refreshed {account.name}. Intent is now {opportunity.intent_score:.0f}, "
                    f"fit is {opportunity.fit_score:.0f}, and the primary draft is {refreshed_draft.status}."
                ),
                suggested_actions=[
                    opportunity.recommended_action,
                    f"Open draft {refreshed_draft.id} for human review.",
                    "Check the compliance receipt before sending anything externally.",
                ],
                route=ModelRouteDecision(**opportunity.model_route),
                citations=[Citation(**citation) for citation in opportunity.evidence],
                notes=self._common_notes(),
                entities={
                    "account_id": account.id,
                    "draft_id": refreshed_draft.id,
                    "product_context_key": opportunity.product_context_key,
                },
                automation_status="completed",
                used_live_model=self._route_has_live_model(ModelRouteDecision(**opportunity.model_route)),
            )

        if request.automation == "review_draft":
            if draft is None:
                raise ValueError("Draft context is required for draft review automation.")
            draft_schema = self._draft_schema(draft)
            receipt = draft_schema.compliance_receipt
            return AgentResult(
                prompt=request.prompt,
                automation=request.automation,
                summary=(
                    f"Draft {draft.id} is {draft.status}. "
                    f"Compliance is {'passing' if receipt and receipt.passed else 'not passing'} "
                    f"with {len(receipt.issues) if receipt else 0} blocking issues."
                ),
                suggested_actions=[
                    "Inspect all citation-backed sentences in the receipt.",
                    "Edit unsupported claims before approval." if receipt and not receipt.passed else "Proceed to human approval if the messaging tone looks right.",
                    "Keep raw reasoning private and rely on the structured rationale panel.",
                ],
                route=draft_schema.model_route,
                citations=draft_schema.citations,
                notes=self._common_notes(),
                entities={
                    "account_id": draft.account_id,
                    "draft_id": draft.id,
                    "status": draft.status,
                },
                automation_status="completed",
                used_live_model=self._route_has_live_model(draft_schema.model_route),
            )

        if request.automation == "build_handoff":
            if account is None:
                raise ValueError("Account context is required for handoff automation.")
            brief = await self.runner.build_handoff(account.id)
            route = self.router.decide(
                "closed-won-handoff",
                evidence_count=max(len(citations), 1),
                tool_count=2,
                ambiguous=True,
                high_risk=False,
            )
            return AgentResult(
                prompt=request.prompt,
                automation=request.automation,
                summary=(
                    f"Built a closed-won handoff for {account.name} with {len(brief.tasks)} tasks and "
                    f"{len(brief.blockers)} tracked blockers."
                ),
                suggested_actions=[
                    "Use the day 1-3 tasks to book kickoff immediately.",
                    "Assign blocker owners before the deal loses momentum.",
                    "Cross-check telemetry highlights with the implementation sponsor.",
                ],
                route=route,
                citations=citations[:4],
                notes=self._common_notes(),
                entities={
                    "account_id": account.id,
                    "handoff_id": brief.id,
                    "stage": brief.stage,
                },
                automation_status="completed",
                used_live_model=self._route_has_live_model(route),
            )

        if request.automation == "summarize_account":
            if account is None:
                raise ValueError("Account context is required for account summary automation.")
            route = self._route_prompt(
                prompt=request.prompt or f"Summarize the account {account.name}.",
                evidence_count=len(citations),
                has_account=True,
            )
            summary, suggested_actions, notes, used_live_model, actual_route = await self._answer_prompt(
                route=route,
                prompt=request.prompt or f"Summarize the account {account.name}.",
                account=account,
                queue_context=queue_context,
                contacts=contacts,
                opportunities=opportunities,
                drafts=drafts,
                handoffs=handoffs,
                citations=citations,
            )
            return AgentResult(
                prompt=request.prompt,
                automation=request.automation,
                summary=summary,
                suggested_actions=suggested_actions,
                route=actual_route,
                citations=citations[:5],
                notes=notes,
                entities={"account_id": account.id},
                automation_status="completed",
                used_live_model=used_live_model,
            )

        route = self._route_prompt(
            prompt=request.prompt,
            evidence_count=len(citations),
            has_account=account is not None,
            has_draft=draft is not None,
        )
        summary, suggested_actions, notes, used_live_model, actual_route = await self._answer_prompt(
            route=route,
            prompt=request.prompt,
            account=account,
            queue_context=queue_context,
            contacts=contacts,
            opportunities=opportunities,
            drafts=drafts,
            handoffs=handoffs,
            citations=citations,
        )
        notes = live_research_notes + notes
        return AgentResult(
            prompt=request.prompt,
            automation=request.automation,
            summary=summary,
            suggested_actions=suggested_actions,
            route=actual_route,
            citations=citations[:5],
            notes=notes,
            entities={
                "account_id": account.id if account else None,
                "draft_id": draft.id if draft else None,
                "live_research_saved_signal_count": live_research_saved_signal_count,
            },
            automation_status="completed",
            used_live_model=used_live_model,
        )

    async def status(self) -> SystemStatus:
        account_count = await self.repository.count_accounts()
        product_context_count = await self.repository.count_product_contexts()
        database_mode = "sqlite" if self.settings.database_url.startswith("sqlite") else "postgres"
        nvidia_ready = bool(self.settings.nvidia_api_key)
        openrouter_ready = bool(self.settings.openrouter_api_key)
        provider_health = self.model_gateway.provider_health_snapshot()
        crm_mode = "shadow_crm_empty" if account_count == 0 else "shadow_crm_live"
        return SystemStatus(
            api_status="ok",
            database_mode=database_mode,
            crm_mode=crm_mode,
            llm_mode=(
                "nvidia_ready_openrouter_degraded"
                if nvidia_ready and openrouter_ready and provider_health["openrouter"]["status"] == "error"
                else "both_models_configured"
                if nvidia_ready and openrouter_ready
                else "partial_provider_configured"
                if nvidia_ready or openrouter_ready
                else "providers_missing"
            ),
            account_count=account_count,
            product_context_count=product_context_count,
            integrations={
                "shadow_crm": "The running API writes live data into the configured transactional database.",
                "redpanda": "Provisioned for ingestion, but request-time workflows do not consume broker events yet.",
                "clickhouse": "Provisioned, but analytics writes are not on the request path yet.",
                "qdrant": "Provisioned, but vector retrieval is not on the request path yet.",
                "temporal": "Provisioned, but workflows currently execute synchronously inside the API.",
                "models": (
                    f"NVIDIA: {provider_health['nvidia']['status']}"
                    + (f" ({provider_health['nvidia']['detail']})" if provider_health["nvidia"]["detail"] else "")
                    + " | "
                    + f"OpenRouter: {provider_health['openrouter']['status']}"
                    + (
                        f" ({provider_health['openrouter']['detail']})"
                        if provider_health["openrouter"]["detail"]
                        else ""
                    )
                ),
            },
            notes=[
                "The application starts empty until you load product context and account data.",
                "The sidebar works only against live API responses.",
            ],
        )

    async def _answer_prompt(
        self,
        *,
        route: ModelRouteDecision,
        prompt: str,
        account: models.Account | None,
        queue_context: list[dict[str, str]],
        contacts: list[models.Contact],
        opportunities: list[models.OpportunityHypothesis],
        drafts: list[models.DraftAsset],
        handoffs: list[models.ActivationBrief],
        citations: list[Citation],
    ) -> tuple[str, list[str], list[str], bool, ModelRouteDecision]:
        context_summary = self._build_context_summary(
            account=account,
            queue_context=queue_context,
            contacts=contacts,
            opportunities=opportunities,
            drafts=drafts,
            handoffs=handoffs,
        )
        notes = self._common_notes()
        try:
            response = await self.model_gateway.answer_agent_prompt(
                route=route,
                prompt=prompt or "Summarize the current account and recommend the next move.",
                context_summary=context_summary,
                citations=citations,
            )
        except RuntimeError as exc:
            fallback_route = ModelRouteDecision(
                workflow=route.workflow,
                target_profile=route.target_profile,
                provider="local",
                model="deterministic_agent_summary",
                reason=f"Local fallback used because live model prompting failed: {exc.__class__.__name__}.",
                thinking=False,
                requires_manual_review_on_failure=True,
            )
            summary = self._local_agent_summary(account=account, queue_context=queue_context, citations=citations)
            actions = self._local_agent_actions(account=account, drafts=drafts, handoffs=handoffs, citations=citations)
            notes.insert(0, "Answered with local:deterministic_agent_summary because live model prompting was unavailable.")
            return summary, actions, notes, False, fallback_route
        actual_route = response["route"]
        notes.insert(0, f"Answered with {actual_route.provider}:{actual_route.model}.")
        notes.extend(response.get("notes", []))
        return response["summary"], response["suggested_actions"], notes, response["used_live_model"], actual_route

    def _build_context_summary(
        self,
        *,
        account: models.Account | None,
        queue_context: list[dict[str, str]],
        contacts: list[models.Contact],
        opportunities: list[models.OpportunityHypothesis],
        drafts: list[models.DraftAsset],
        handoffs: list[models.ActivationBrief],
    ) -> str:
        if account is None:
            if queue_context:
                ranked = " | ".join(
                    f"{item['name']} intent={item['intent_score']} fit={item['fit_score']} signal={item['top_signal']}"
                    for item in queue_context
                )
                return (
                    "No specific account is open. Use the ranked queue snapshot to answer questions about which accounts appear most interested. "
                    f"Queue snapshot: {ranked}. "
                    "Only claim interest when tied to the provided signals and scores."
                )
            return (
                "No account context is open. The workspace may still be empty. "
                "If no product contexts or accounts are loaded, tell the operator to create a product context, "
                "then create an account and contacts, then ingest cited market signals or telemetry before asking for outreach guidance. "
                "Do not invent login, approval, or security workflows that are not part of the provided context."
            )
        opportunity = opportunities[0] if opportunities else None
        draft = drafts[0] if drafts else None
        handoff = handoffs[0] if handoffs else None
        return (
            f"Account: {account.name}. Segment: {account.segment}. Stage: {account.pipeline_stage}. "
            f"Summary: {account.summary} Next action: {account.next_action}. "
            f"Contacts: {', '.join(f'{contact.name} ({contact.role})' for contact in contacts[:4]) or 'none'}. "
            f"Opportunity: {opportunity.product_context_key if opportunity else 'none'}. "
            f"Draft status: {draft.status if draft else 'none'}. "
            f"Handoff stage: {handoff.stage if handoff else 'none'}."
        )

    def _route_prompt(
        self,
        *,
        prompt: str,
        evidence_count: int,
        has_account: bool,
        has_draft: bool = False,
    ) -> ModelRouteDecision:
        normalized = prompt.lower()
        complex_markers = [
            "why",
            "compare",
            "committee",
            "stakeholder",
            "compliance",
            "regulatory",
            "legal",
            "automation",
            "sequence",
            "multi-step",
            "activation",
        ]
        is_complex = len(prompt.split()) > 14 or any(marker in normalized for marker in complex_markers)
        high_risk = any(marker in normalized for marker in ["compliance", "legal", "regulatory", "security", "rbi"])
        tool_count = 2 if has_account or has_draft else 0
        return self.router.decide(
            "agent-assistant",
            evidence_count=evidence_count,
            tool_count=tool_count,
            ambiguous=is_complex,
            high_risk=high_risk,
        )

    def _should_use_live_research(self, prompt: str) -> bool:
        normalized = prompt.lower()
        research_markers = [
            "deep research",
            "research",
            "live search",
            "search the web",
            "recent",
            "latest",
            "news",
            "executive hire",
            "executive hires",
            "compliance issue",
            "compliance issues",
            "fine",
            "penalty",
            "rbi",
            "2026",
        ]
        return any(marker in normalized for marker in research_markers)

    def _is_high_risk_research_prompt(self, prompt: str) -> bool:
        normalized = prompt.lower()
        return any(marker in normalized for marker in ["compliance", "rbi", "fine", "penalty", "security", "breach"])

    async def _save_live_research_findings(
        self,
        *,
        account: models.Account,
        findings: list[LiveCompanyResearchFinding],
    ) -> int:
        existing = {(signal.title, signal.source_url) for signal in await self.repository.list_signals(account.id)}
        saved_count = 0
        for finding in findings:
            dedupe_key = (finding.title, finding.source_url)
            if dedupe_key in existing:
                continue
            citation = Citation(
                label=finding.provider,
                source_url=finding.source_url,
                claim=finding.title,
                excerpt=finding.summary,
                published_at=finding.published_at,
            )
            await self.repository.create_signal(
                {
                    "account_id": account.id,
                    "topic_family": "market-signal.ingested",
                    "signal_type": classify_signal(f"{finding.title} {finding.summary}"),
                    "source_type": "live_company_research",
                    "title": finding.title,
                    "summary": finding.summary,
                    "source_url": finding.source_url,
                    "detected_at": finding.published_at or datetime.now(UTC),
                    "facts": {
                        "tool": "live_company_research",
                        "provider": finding.provider,
                        "query": finding.query,
                    },
                    "citations": [citation.model_dump(mode="json")],
                    "raw_payload": {
                        "title": finding.title,
                        "summary": finding.summary,
                        "source_url": finding.source_url,
                        "provider": finding.provider,
                        "query": finding.query,
                    },
                },
            )
            existing.add(dedupe_key)
            saved_count += 1
        if saved_count:
            account.last_activity_at = datetime.now(UTC)
            account.next_action = "Review fresh live research, then decide whether to refresh the committee sequence."
            await self.repository.session.commit()
            await self.repository.log_activity(
                account.id,
                "research",
                "Live company research saved",
                f"Saved {saved_count} cited findings from live_company_research.",
            )
        return saved_count

    def _collect_citations(
        self,
        signals: list[models.Signal],
        draft: models.DraftAsset | None,
    ) -> list[Citation]:
        citations: list[Citation] = []
        for signal in signals[:6]:
            if signal.citations:
                citations.extend(Citation(**citation) for citation in signal.citations)
            else:
                citations.append(
                    Citation(
                        label=signal.title,
                        source_url=signal.source_url,
                        claim=signal.summary,
                        excerpt=signal.summary,
                        published_at=signal.detected_at,
                    ),
                )
        if draft:
            citations.extend(Citation(**citation) for citation in draft.citations[:3])
        return citations

    async def _queue_context(self) -> list[dict[str, str]]:
        accounts = list(await self.repository.list_accounts())
        ranked: list[dict[str, str]] = []
        for account in accounts[:5]:
            signals = list(await self.repository.list_signals(account.id))
            ranked.append(
                {
                    "account_id": account.id,
                    "name": account.name,
                    "intent_score": f"{account.intent_score:.0f}",
                    "fit_score": f"{account.fit_score:.0f}",
                    "next_action": account.next_action,
                    "top_signal": signals[0].summary if signals else "No recent signals",
                },
            )
        return ranked

    def _extend_citations_with_queue(
        self,
        citations: list[Citation],
        queue_context: list[dict[str, str]],
    ) -> list[Citation]:
        if citations or not queue_context:
            return citations
        queue_citations: list[Citation] = []
        for item in queue_context[:4]:
            queue_citations.append(
                Citation(
                    label=item["name"],
                    source_url=f"/accounts/{item['account_id']}",
                    claim=item["top_signal"],
                    excerpt=item["next_action"],
                    published_at=None,
                ),
            )
        return queue_citations

    def _local_agent_summary(
        self,
        *,
        account: models.Account | None,
        queue_context: list[dict[str, str]],
        citations: list[Citation],
    ) -> str:
        if account is not None:
            if citations:
                return (
                    f"{account.name} now has {len(citations)} cited evidence items in the Shadow CRM. "
                    "Review the newest signals on Account Detail, then refresh the opportunity sequence if the facts change the outreach angle."
                )
            return (
                f"{account.name} is open, but there are no cited facts available yet. "
                "Run live research or ingest market signals before relying on AI outreach."
            )
        if queue_context:
            top = queue_context[0]
            return f"The highest-ranked queued account is {top['name']} with intent {top['intent_score']} and fit {top['fit_score']}."
        return "No account context is open and the queue is empty. Create a product context, then run discovery or ingest cited signals."

    def _local_agent_actions(
        self,
        *,
        account: models.Account | None,
        drafts: list[models.DraftAsset],
        handoffs: list[models.ActivationBrief],
        citations: list[Citation],
    ) -> list[str]:
        if account is None:
            return [
                "Create or select a product context.",
                "Run external discovery to find interested organizations.",
                "Add a candidate to the queue before asking for account-level research.",
            ]
        actions = ["Review the latest cited signals in Account Detail."]
        if citations:
            actions.append("Run opportunity refresh to regenerate CTO/CFO/Legal outreach from the new evidence.")
        if drafts:
            actions.append("Open Draft Review and inspect the compliance receipt before approval.")
        if handoffs:
            actions.append("Check telemetry and create an activation nudge if the account has stalled.")
        return actions

    def _draft_schema(self, draft: models.DraftAsset):
        from apps.api.app.services.serializers import draft_to_schema

        return draft_to_schema(draft)

    def _route_has_live_model(self, route: ModelRouteDecision) -> bool:
        if route.provider == "nvidia":
            return bool(self.settings.nvidia_api_key)
        if route.provider == "openrouter":
            return bool(self.settings.openrouter_api_key)
        return False

    def _common_notes(self) -> list[str]:
        return [
            "Automations operate against the running Shadow CRM database.",
            "Redpanda, ClickHouse, Qdrant, and Temporal are provisioned but not yet on the critical request path for sidebar actions.",
        ]
