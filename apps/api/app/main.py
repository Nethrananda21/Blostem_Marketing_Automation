from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app import models
from apps.api.app.config import get_settings
from apps.api.app.database import Base, SessionLocal, engine, get_db_session
from apps.api.app.repositories import Repository
from apps.api.app.schemas import (
    AccountBrief,
    AccountCreateRequest,
    AccountSummary,
    AgentResult,
    AgentRunRequest,
    ActivationBrief,
    ApprovalDecision,
    CanonicalSignal,
    ContactCreateRequest,
    DiscoveryCandidateRecord,
    DiscoveryJob,
    DiscoveryJobCreateRequest,
    DiscoveryImportRequest,
    DiscoveryImportResult,
    DiscoverySearchRequest,
    DiscoverySearchResponse,
    DraftAsset,
    DraftDecisionRequest,
    DraftEditRequest,
    PersonaBrief,
    ProductContext,
    ProductContextCreateRequest,
    OperationJobStatus,
    QueueResponse,
    SignalIngestRequest,
    SystemStatus,
    TelemetryEvent,
    TelemetryIngestRequest,
    WorkflowRefreshRequest,
)
from apps.api.app.services.agent import AgentService
from apps.api.app.services.compliance import ComplianceService
from apps.api.app.services.discovery import MarketDiscoveryService
from apps.api.app.services.email_service import EmailService
from apps.api.app.services.integrations import EventPublisher
from apps.api.app.services.model_gateway import ModelGateway
from apps.api.app.services.routing import ModelRouter
from apps.api.app.services.serializers import (
    account_brief_from_records,
    activation_to_schema,
    account_summary_from_model,
    discovery_candidate_record_to_schema,
    discovery_job_to_schema,
    draft_to_schema,
    operation_job_to_schema,
    product_context_to_schema,
    queue_from_records,
    signal_to_schema,
    telemetry_to_schema,
)
from apps.api.app.services.workflow_engine import WorkflowRunner


settings = get_settings()
RUNNING_AGENT_JOBS: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    scheduler_task: asyncio.Task | None = None
    if settings.discovery_scheduler_enabled:
        scheduler_task = asyncio.create_task(_automation_scheduler_loop())
    try:
        yield
    finally:
        if scheduler_task:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task


async def _automation_scheduler_loop() -> None:
    while True:
        try:
            async with SessionLocal() as session:
                discovery_service = build_discovery_service(session)
                await discovery_service.run_due_jobs()
                runner = build_runner(session)
                await runner.run_due_nurture_sequences()
        except Exception:
            pass
        await asyncio.sleep(max(30, settings.automation_poll_seconds))


def _job_progress_for_request(request: AgentRunRequest) -> str:
    normalized = (request.prompt or "").lower()
    if request.automation == "refresh_opportunity":
        return "Refreshing opportunity, mapping committee, and generating persona drafts."
    if request.automation == "review_draft":
        return "Reviewing citations and compliance status for the current draft."
    if request.automation == "build_handoff":
        return "Building post-sale handoff and activation plan."
    if request.automation == "summarize_account":
        return "Summarizing current account context and next actions."
    if any(token in normalized for token in ["find interested", "interested parties", "prospects", "search the web"]):
        return "Searching for interested organizations and ranking signal-backed candidates."
    if any(token in normalized for token in ["deep research", "latest", "recent", "executive", "compliance"]):
        return "Running live research, saving cited findings, and synthesizing the result."
    return "Gathering context and preparing the assistant response."


async def _run_agent_job(job_id: str, request: AgentRunRequest) -> None:
    async with SessionLocal() as session:
        repository = Repository(session)
        job = await repository.get_operation_job(job_id)
        if job is None:
            RUNNING_AGENT_JOBS.pop(job_id, None)
            return
        await repository.update_operation_job(
            job,
            status="running",
            progress_message=_job_progress_for_request(request),
            started_at=datetime.now(UTC),
        )
        agent_service = build_agent_service(session)
        try:
            result = await agent_service.run(request)
        except ValueError as exc:
            await repository.update_operation_job(
                job,
                status="failed",
                error_message=str(exc),
                progress_message="The request could not be completed.",
                finished_at=datetime.now(UTC),
            )
        except RuntimeError as exc:
            await repository.update_operation_job(
                job,
                status="failed",
                error_message=str(exc),
                progress_message="The request failed while calling the configured providers.",
                finished_at=datetime.now(UTC),
            )
        else:
            await repository.update_operation_job(
                job,
                status="completed",
                result_json=result.model_dump(mode="json"),
                progress_message="Completed.",
                finished_at=datetime.now(UTC),
            )
        finally:
            RUNNING_AGENT_JOBS.pop(job_id, None)


app = FastAPI(title=settings.app_name, lifespan=lifespan, root_path=settings.api_root_path)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def build_runner(session: AsyncSession) -> WorkflowRunner:
    repository = Repository(session)
    return WorkflowRunner(
        repository=repository,
        router=ModelRouter(settings),
        model_gateway=ModelGateway(settings),
        compliance_service=ComplianceService(),
    )


def build_agent_service(session: AsyncSession) -> AgentService:
    repository = Repository(session)
    router = ModelRouter(settings)
    model_gateway = ModelGateway(settings)
    runner = WorkflowRunner(
        repository=repository,
        router=router,
        model_gateway=model_gateway,
        compliance_service=ComplianceService(),
    )
    return AgentService(
        repository=repository,
        runner=runner,
        router=router,
        model_gateway=model_gateway,
        settings=settings,
    )


def build_discovery_service(session: AsyncSession) -> MarketDiscoveryService:
    repository = Repository(session)
    router = ModelRouter(settings)
    runner = WorkflowRunner(
        repository=repository,
        router=router,
        model_gateway=ModelGateway(settings),
        compliance_service=ComplianceService(),
    )
    return MarketDiscoveryService(
        repository=repository,
        runner=runner,
        router=router,
        settings=settings,
    )


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/system/status", response_model=SystemStatus)
async def system_status(session: AsyncSession = Depends(get_db_session)) -> SystemStatus:
    return await build_agent_service(session).status()


@app.get("/product-contexts", response_model=list[ProductContext])
async def list_product_contexts(session: AsyncSession = Depends(get_db_session)) -> list[ProductContext]:
    repository = Repository(session)
    return [product_context_to_schema(context) for context in await repository.list_product_contexts()]


@app.post("/product-contexts", response_model=ProductContext)
async def create_product_context(
    request: ProductContextCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProductContext:
    repository = Repository(session)
    existing = await repository.get_product_context(request.key)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Product context key already exists")
    context = await repository.create_product_context(request.model_dump())
    return product_context_to_schema(context)


@app.get("/accounts", response_model=QueueResponse)
async def list_accounts(session: AsyncSession = Depends(get_db_session)) -> QueueResponse:
    repository = Repository(session)
    accounts = list(await repository.list_accounts())
    signals_by_account: dict[str, list[models.Signal]] = defaultdict(list)
    latest_opportunities: dict[str, models.OpportunityHypothesis | None] = {}
    for account in accounts:
        signals_by_account[account.id] = list(await repository.list_signals(account.id))
        opportunities = list(await repository.list_opportunities(account.id))
        latest_opportunities[account.id] = opportunities[0] if opportunities else None
    return queue_from_records(accounts, latest_opportunities, signals_by_account)


@app.post("/accounts", response_model=AccountSummary)
async def create_account(
    request: AccountCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AccountSummary:
    repository = Repository(session)
    account = await repository.create_account(request.model_dump())
    return account_summary_from_model(account)


@app.post("/accounts/{account_id}/contacts", response_model=PersonaBrief)
async def create_contact(
    account_id: str,
    request: ContactCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> PersonaBrief:
    repository = Repository(session)
    account = await repository.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    contact = await repository.create_contact(account_id, request.model_dump())
    return PersonaBrief(
        name=contact.name,
        role=contact.role,
        persona=contact.persona,
        email=contact.email,
        influence_level=contact.influence_level,
        status=contact.status,
        notes=contact.notes,
    )


@app.get("/accounts/{account_id}/brief", response_model=AccountBrief)
async def get_account_brief(account_id: str, session: AsyncSession = Depends(get_db_session)) -> AccountBrief:
    repository = Repository(session)
    account = await repository.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    contacts = list(await repository.list_contacts(account_id))
    signals = list(await repository.list_signals(account_id))
    telemetry = list(await repository.list_telemetry(account_id))
    opportunities = list(await repository.list_opportunities(account_id))
    drafts = list(await repository.list_drafts(account_id))
    nurture_sequences = list(await repository.list_nurture_sequences(account_id))
    nurture_touches = list(await repository.list_nurture_touches(account_id))
    activity = list(await repository.list_activity(account_id))
    activation_briefs = list(await repository.list_activation_briefs(account_id))
    return account_brief_from_records(
        account,
        contacts,
        signals,
        telemetry,
        opportunities,
        drafts,
        nurture_sequences,
        nurture_touches,
        activity,
        activation_briefs,
    )


@app.post("/signals/ingest", response_model=CanonicalSignal)
async def ingest_signal(
    request: SignalIngestRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CanonicalSignal:
    repository = Repository(session)
    account = await repository.get_account(request.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    signal_payload = request.model_dump(mode="python")
    signal = await repository.create_signal(signal_payload)
    await EventPublisher(settings).publish("market-signal.ingested", request.model_dump(mode="json"))
    return signal_to_schema(signal)


@app.post("/telemetry/ingest", response_model=TelemetryEvent)
async def ingest_telemetry(
    request: TelemetryIngestRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TelemetryEvent:
    repository = Repository(session)
    account = await repository.get_account(request.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    telemetry_payload = request.model_dump(mode="python")
    event = await repository.create_telemetry_event(telemetry_payload)
    await EventPublisher(settings).publish("product-telemetry.ingested", request.model_dump(mode="json"))
    runner = build_runner(session)
    await runner.evaluate_post_sale_nudge(request.account_id)
    return telemetry_to_schema(event)


@app.post("/workflows/opportunity-refresh")
async def refresh_workflow(
    request: WorkflowRefreshRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    runner = build_runner(session)
    try:
        opportunity, draft = await runner.refresh_opportunity(request.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "opportunity": opportunity.id,
        "draft": draft.id,
        "status": draft.status,
    }


@app.post("/agent/run", response_model=AgentResult)
async def run_agent(
    request: AgentRunRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AgentResult:
    agent_service = build_agent_service(session)
    try:
        return await agent_service.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/agent/jobs", response_model=OperationJobStatus)
async def create_agent_job(
    request: AgentRunRequest,
    session: AsyncSession = Depends(get_db_session),
) -> OperationJobStatus:
    repository = Repository(session)
    account_id = request.account_id
    draft_id = request.draft_id
    if draft_id and not account_id:
        draft = await repository.get_draft(draft_id)
        if draft is not None:
            account_id = draft.account_id
    job = await repository.create_operation_job(
        {
            "job_type": "agent_run",
            "status": "queued",
            "account_id": account_id,
            "draft_id": draft_id,
            "progress_message": _job_progress_for_request(request),
            "request_json": request.model_dump(mode="json"),
            "result_json": None,
            "error_message": "",
            "started_at": None,
            "finished_at": None,
        },
    )
    RUNNING_AGENT_JOBS[job.id] = asyncio.create_task(_run_agent_job(job.id, request))
    return operation_job_to_schema(job)


@app.get("/agent/jobs/{job_id}", response_model=OperationJobStatus)
async def get_agent_job(job_id: str, session: AsyncSession = Depends(get_db_session)) -> OperationJobStatus:
    repository = Repository(session)
    job = await repository.get_operation_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Agent job not found")
    return operation_job_to_schema(job)


@app.post("/discovery/search", response_model=DiscoverySearchResponse)
async def search_discovery(
    request: DiscoverySearchRequest,
    session: AsyncSession = Depends(get_db_session),
) -> DiscoverySearchResponse:
    discovery_service = build_discovery_service(session)
    try:
        return await discovery_service.search(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/discovery/candidates/add", response_model=DiscoveryImportResult)
async def add_discovery_candidate(
    request: DiscoveryImportRequest,
    session: AsyncSession = Depends(get_db_session),
) -> DiscoveryImportResult:
    discovery_service = build_discovery_service(session)
    try:
        return await discovery_service.import_candidate(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/discovery/jobs", response_model=list[DiscoveryJob])
async def list_discovery_jobs(session: AsyncSession = Depends(get_db_session)) -> list[DiscoveryJob]:
    repository = Repository(session)
    return [discovery_job_to_schema(job) for job in await repository.list_discovery_jobs()]


@app.post("/discovery/jobs", response_model=DiscoveryJob)
async def create_discovery_job(
    request: DiscoveryJobCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> DiscoveryJob:
    repository = Repository(session)
    context = await repository.get_product_context(request.product_context_key)
    if context is None:
        raise HTTPException(status_code=404, detail="Product context not found")
    job = await repository.create_discovery_job(
        {
            **request.model_dump(),
            "status": "active",
            "next_run_at": datetime.now(UTC),
            "last_run_at": None,
            "last_result_count": 0,
        },
    )
    return discovery_job_to_schema(job)


@app.post("/discovery/jobs/{job_id}/run")
async def run_discovery_job(job_id: str, session: AsyncSession = Depends(get_db_session)) -> dict:
    repository = Repository(session)
    job = await repository.get_discovery_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    discovery_service = build_discovery_service(session)
    try:
        stored_count = await discovery_service.run_discovery_job(job)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "job": discovery_job_to_schema(job),
        "stored_count": stored_count,
    }


@app.get("/discovery/inbox", response_model=list[DiscoveryCandidateRecord])
async def list_discovery_inbox(
    status: str | None = "new",
    session: AsyncSession = Depends(get_db_session),
) -> list[DiscoveryCandidateRecord]:
    repository = Repository(session)
    records = list(await repository.list_discovery_candidate_records(status=status))
    return [discovery_candidate_record_to_schema(record) for record in records]


@app.post("/automation/run-due")
async def run_due_automation(session: AsyncSession = Depends(get_db_session)) -> dict:
    discovery_service = build_discovery_service(session)
    runner = build_runner(session)
    discovery_results = await discovery_service.run_due_jobs()
    nurture_results = await runner.run_due_nurture_sequences()
    return {
        "discovery": discovery_results,
        "nurture": nurture_results,
    }


@app.get("/drafts/{draft_id}", response_model=DraftAsset)
async def get_draft(draft_id: str, session: AsyncSession = Depends(get_db_session)) -> DraftAsset:
    repository = Repository(session)
    draft = await repository.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft_to_schema(draft)


@app.post("/drafts/{draft_id}/edit", response_model=DraftAsset)
async def edit_draft(
    draft_id: str,
    request: DraftEditRequest,
    session: AsyncSession = Depends(get_db_session),
) -> DraftAsset:
    repository = Repository(session)
    draft = await repository.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    runner = build_runner(session)
    receipt = runner.recheck_compliance(
        request.body,
        draft_to_schema(draft).citations,
        route=draft_to_schema(draft).model_route,
    )
    updated = await repository.update_draft(
        draft,
        edited_body=request.body,
        status="pending_human_approval" if receipt.passed else "needs_revision",
        compliance_receipt=receipt.model_dump(mode="json"),
    )
    return draft_to_schema(updated)


@app.post("/drafts/{draft_id}/approve", response_model=ApprovalDecision)
async def approve_draft(
    draft_id: str,
    request: DraftDecisionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalDecision:
    repository = Repository(session)
    draft = await repository.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    updated = await repository.update_draft(draft, status="approved")
    touch = await repository.get_nurture_touch_by_draft(updated.id)
    if touch is not None:
        await repository.update_nurture_touch(
            touch,
            status="approved",
            completed_at=datetime.now(UTC),
        )
    approval = await repository.create_approval(
        {
            "draft_id": updated.id,
            "reviewer_role": request.reviewer_role,
            "decision": "approved",
            "notes": request.notes,
        },
    )
    await repository.log_activity(
        updated.account_id,
        "approval",
        "Draft approved",
        f"{request.reviewer_role} approved the outreach draft.",
    )

    # ── Send email (demo mode: always redirected to DEMO_EMAIL_OVERRIDE) ──────
    account = await repository.get_account(updated.account_id)
    contacts = list(await repository.list_contacts(updated.account_id)) if account else []
    primary_contact = next(
        (c for c in contacts if c.persona == updated.persona),
        contacts[0] if contacts else None,
    )
    to_email = primary_contact.email if primary_contact else "unknown@example.com"
    to_name  = primary_contact.name  if primary_contact else updated.persona
    email_service = EmailService(settings)
    email_result = email_service.send_draft(
        to_email=to_email,
        to_name=to_name,
        subject=updated.subject,
        body=updated.edited_body or updated.body,
        account_name=account.name if account else "",
        persona=updated.persona,
        approved_by=request.reviewer_role,
    )
    await repository.log_activity(
        updated.account_id,
        "email",
        f"Outreach email {email_result['status']}",
        (
            f"Sent to {email_result.get('recipient')} "
            f"(original: {email_result.get('original_to')}, "
            f"demo override: {email_result.get('overridden', False)})"
            if email_result["status"] == "sent"
            else email_result.get("reason", "")
        ),
    )

    return ApprovalDecision(
        id=approval.id,
        draft_id=approval.draft_id,
        reviewer_role=approval.reviewer_role,
        decision="approved",
        notes=approval.notes,
        created_at=approval.created_at,
    )


@app.post("/drafts/{draft_id}/reject", response_model=ApprovalDecision)
async def reject_draft(
    draft_id: str,
    request: DraftDecisionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalDecision:
    repository = Repository(session)
    draft = await repository.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    updated = await repository.update_draft(draft, status="rejected")
    touch = await repository.get_nurture_touch_by_draft(updated.id)
    if touch is not None:
        await repository.update_nurture_touch(
            touch,
            status="needs_revision",
            completed_at=datetime.now(UTC),
        )
    approval = await repository.create_approval(
        {
            "draft_id": updated.id,
            "reviewer_role": request.reviewer_role,
            "decision": "rejected",
            "notes": request.notes,
        },
    )
    await repository.log_activity(
        updated.account_id,
        "approval",
        "Draft rejected",
        f"{request.reviewer_role} rejected the outreach draft.",
    )
    return ApprovalDecision(
        id=approval.id,
        draft_id=approval.draft_id,
        reviewer_role=approval.reviewer_role,
        decision="rejected",
        notes=approval.notes,
        created_at=approval.created_at,
    )


@app.get("/deals/{account_id}/handoff", response_model=ActivationBrief)
async def get_handoff(account_id: str, session: AsyncSession = Depends(get_db_session)) -> ActivationBrief:
    repository = Repository(session)
    brief = await repository.get_activation_brief(account_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="Handoff not found")
    return activation_to_schema(brief)


@app.post("/deals/{account_id}/handoff", response_model=ActivationBrief)
async def create_handoff(account_id: str, session: AsyncSession = Depends(get_db_session)) -> ActivationBrief:
    runner = build_runner(session)
    try:
        brief = await runner.build_handoff(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return activation_to_schema(brief)
