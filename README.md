# Blostem B2B AI Marketing Engine

Blostem is an India-first BFSI pilot for an internal AI-powered B2B marketing and sales enablement platform. It helps Blostem sales reps find high-intent banks, fintechs, NBFCs, insurers, and agencies from market signals, map the buying committee, generate compliance-safe outreach, manage the account queue, and continue activation nudges after a deal is signed.

The product is not a generic chatbot. It is closer to a sales operations cockpit with an AI agent and automation layer: market data comes in, the backend scores accounts, drafts persona-specific outreach, checks citations and compliance, and keeps the human rep in control before anything external is sent.

## Current Status

This repo currently implements a working pilot version with:

- A `Next.js` sales cockpit frontend.
- A `FastAPI` backend.
- A Postgres-backed Shadow CRM.
- Public market discovery through Google News RSS-style search.
- Sidebar live-company research through Tavily or DuckDuckGo search.
- Scheduled discovery jobs and a candidate inbox.
- AI model routing for Kimi and Gemma provider profiles.
- Compliance claim parsing and citation enforcement.
- Committee-wide draft generation for CTO, CFO, and Legal personas.
- Nurture sequence state for follow-ups.
- Closed-won handoff and telemetry-triggered activation nudges.
- Docker Compose deployment with a single public reverse-proxy entrypoint.

Temporal, Redpanda, ClickHouse, Qdrant, and MinIO are included in Docker as infrastructure services. The pilot still executes most domain workflow logic synchronously in the API, while keeping the architecture ready for deeper Temporal worker execution.

## Architecture

```text
Browser
  |
  | http://localhost:3000
  v
Nginx reverse proxy
  |---- /      -> Next.js web app
  |---- /api  -> FastAPI backend

FastAPI backend
  |---- Postgres: Shadow CRM, workflow state, accounts, contacts, drafts, approvals
  |---- Redpanda: event bus topics for market signals and telemetry
  |---- ClickHouse: analytics/facts service placeholder for hard facts
  |---- Qdrant: retrieval/vector service placeholder
  |---- MinIO: object storage placeholder for raw source documents
  |---- Temporal: workflow infrastructure
  |---- NVIDIA API: Kimi K2.5 complex reasoning profile
  |---- OpenRouter API: Gemma 4 31B executor profile
```

## Feature Guide

### 1. Shadow CRM

The app uses Postgres as the pilot CRM instead of integrating Salesforce/HubSpot in v1.

What it does:

- Stores accounts, contacts, pipeline stage, account scores, next action, activity history, draft status, approvals, nurture sequences, and activation handoffs.
- Keeps data private inside the Blostem-hosted stack.
- Avoids third-party CRM API rate limits during the pilot.

Where it appears:

- Account Queue page.
- Account Detail page.
- Draft Review page.
- Closed-Won Handoff page.

### 2. Product Context Catalog

Product Context describes what Blostem sells and how the AI should reason about it.

What it stores:

- Product key, name, version, and overview.
- ICP segments such as `Bank`, `Fintech`, `NBFC`, or `Insurance`.
- Trigger patterns such as `security`, `fraud`, `digital onboarding`, or `compliance`.
- Disqualifiers.
- Approved claims.
- Buyer personas.
- Activation playbook steps.

Why it matters:

- Discovery uses it to decide what organizations are relevant.
- Draft generation uses it to keep messaging grounded.
- Opportunity scoring uses it to decide fit and next action.

### 3. Market Discovery: Detective Capability

The Detective capability finds net-new organizations that may need Blostem right now.

What it does:

- Accepts a prompt such as: `Find Indian BFSI organizations with recent security, compliance, or digital onboarding triggers.`
- Builds search queries from the prompt and selected Product Context.
- Searches public market/news signals.
- Extracts organization names.
- Cleans and canonicalizes entities.
- Groups duplicate signals by organization.
- Scores each candidate by interest, fit, freshness, confidence, and source count.
- Shows the candidate list before importing anything into the CRM.

Current implementation:

- Uses query-driven public discovery through Google News RSS-style ingestion.
- Does not do uncontrolled open web scraping.
- Stores scheduled results in a reviewable candidate inbox.

UI behavior:

- Use `External Discovery` on the Account Queue page.
- Run a prompt-only search with `Search the public web`.
- Create a recurring job with `Schedule recurring search`.
- Review scheduled candidates in `Candidate Inbox`.
- Click `Add to queue` to convert a candidate into an interested account.

### 4. Scheduled External Ingestion

Discovery is not only prompt-based. The backend can run discovery jobs automatically.

What it does:

- Stores recurring discovery jobs in Postgres.
- Runs due jobs when the API scheduler is enabled.
- Saves candidates into the discovery inbox.
- Allows manual `Run now` from the UI.
- Allows manual backend execution with `POST /automation/run-due`.

Important env vars:

- `DISCOVERY_SCHEDULER_ENABLED=true`
- `AUTOMATION_POLL_SECONDS=300`

### 5. Account Queue

The Account Queue is the rep’s working list of interested organizations.

What it shows:

- Tracked accounts.
- Intent score.
- Fit score.
- Freshness score.
- Primary product context.
- Top signal.
- Recommended next action.

What it is for:

- Prioritizing who the sales rep should work on first.
- Moving from noisy market signals to a focused action queue.

### 6. Account Detail

Account Detail is the glass-box view for one account.

What it shows:

- Account summary and next action.
- Opportunity rationale.
- Cited evidence.
- Buying committee.
- Recent activity.
- Nurture automation sequences.
- Pending touches.

What it is for:

- Understanding why the AI thinks the account is relevant.
- Reviewing evidence before outreach.
- Opening draft review for a specific outreach touch.

### 7. Committee-Wide Outreach: Chameleon Capability

The Chameleon capability adapts messaging by stakeholder.

What it does:

- When opportunity refresh runs, the workflow creates drafts for CTO, CFO, and Legal/Compliance personas.
- CTO messaging focuses on technical/platform/control priorities.
- CFO messaging focuses on operating, financial, and risk priorities.
- Legal messaging focuses on governance, review, and compliance priorities.
- Each draft is stored as a separate reviewable asset.

Human-in-the-loop:

- Drafts are not sent automatically.
- The rep must review and approve.
- Approval state is stored in the Shadow CRM.

### 8. Compliance Review: Lawyer Capability

The Lawyer capability checks generated text before a human rep sees or approves it.

What it does:

- Splits draft text into sentence-level checks.
- Classifies each sentence as boilerplate or factual claim.
- Requires citations for numeric, dated, comparative, regulatory, customer, ROI, security, or compliance claims.
- Allows generic connective prose without citations.
- Fails drafts with unsupported factual claims.

Examples:

- `We noticed your recent RBI penalty` requires a citation.
- `This may be useful to compare notes` can pass as boilerplate.
- Unsupported ROI promises are blocked.
- Unsupported security/compliance assertions are blocked.

### 9. Draft Review

Draft Review is the mandatory human approval gateway.

What it shows:

- Subject line.
- Email body.
- Citations.
- Structured rationale.
- Compliance receipt.
- Claim-by-claim compliance checks.

What the rep can do:

- Approve the draft.
- Reject the draft.
- Edit the draft and re-run compliance.

### 10. Nurture Workflows

Nurture workflows keep track of follow-up state over time.

What it stores:

- Sequence kind: `prospect_outreach` or `post_sale_activation`.
- Current round.
- Max rounds.
- Cadence days.
- Next touch date.
- Touch status.
- Draft linked to each touch.

What it does:

- Creates initial committee outreach touches after opportunity refresh.
- Creates follow-up touches when due automation runs.
- Pauses when max rounds are reached.

### 11. Closed-Won Handoff: Coach Capability

The Coach capability starts after a deal is signed.

What it does:

- Generates a 30-day activation handoff.
- Shows kickoff context, blockers, tasks, stakeholders, and telemetry highlights.
- Creates a post-sale activation sequence.
- Watches telemetry events for signs of activation or stall.
- Generates an activation nudge draft when telemetry suggests setup has started but activation has not completed.

Examples of activation-complete telemetry:

- `login_completed`
- `workspace_activated`
- `activation_completed`
- `first_value_reached`

Examples of stall/early telemetry:

- `setup_started`
- `invite_sent`
- `questionnaire_opened`

### 12. AI Agent Sidebar

The app includes a right-side AI agent sidebar inspired by coding assistant sidebars.

What it does:

- Lets the rep prompt the system from the current workspace.
- Can summarize an account.
- Can trigger `live_company_research` when a prompt asks for recent/deep web research on an open account.
- Saves live research findings back into Account Detail as cited market signals.
- Can refresh opportunity scoring.
- Can review a draft.
- Can build a handoff.
- Shows model/provider status.

Relevant prompts:

- `Find interested Indian banks for this product.`
- `Why is this account high intent right now?`
- `Research this account in detail.`
- `Create CTO, CFO, and Legal outreach for this account.`
- `Review this draft for compliance risks.`
- `Create a 30-day activation handoff.`
- `What should the rep do next?`

The sidebar uses structured actions and backend APIs. It does not expose raw hidden chain-of-thought; the UI shows structured rationale and citations instead.

### 13. Live Company Research Tool

The sidebar agent has a deterministic `live_company_research` tool for prompts that need facts beyond the existing Postgres account record.

What triggers it:

- Prompts containing research intent such as `deep research`, `research`, `latest`, `recent`, `news`, `executive hires`, `compliance issues`, `RBI`, `fine`, `penalty`, or a specific year such as `2026`.
- The prompt must have an account context, for example after opening an account detail page and asking about that company.

What it does:

- Builds a company-specific web query from the open account and the user prompt.
- Uses Tavily if `TAVILY_API_KEY` is configured.
- Falls back to DuckDuckGo HTML search when no Tavily key is available.
- Converts returned articles into `market-signal.ingested` records with source URLs and citations.
- Refreshes the sidebar answer with the new citations.
- Adds an account activity event so the rep can see that live research was saved.

Example flow:

- Open `Axis Bank` in Account Detail.
- Prompt: `Do deep research on Axis Bank's recent executive hires and compliance issues in 2026.`
- The backend calls `live_company_research`.
- New cited search results are saved as account signals.
- The sidebar responds with a source-backed summary and next actions.

## AI Model Routing

The backend uses two pinned model profiles.

### Complex Reasoner

- Profile: `complex_reasoner`
- Provider: NVIDIA
- Model: `moonshotai/kimi-k2.5`
- Used for: signal triage, committee mapping, compliance review, multi-source synthesis, ambiguous product matching, and high-risk tasks.

### Draft Executor

- Profile: `draft_executor`
- Provider: OpenRouter
- Model: `google/gemma-4-31b-it`
- Used for: grounded draft generation, subject variants, short rewrites, summaries, and call briefs.

Rules:

- Compliance and committee tasks should not silently downgrade from Kimi to Gemma.
- If live providers are unavailable, parts of the app use deterministic local fallbacks so the pilot remains testable.
- Secrets must stay in backend environment variables only.

## Data and Event Topics

The platform separates public market signals from internal product telemetry.

Market signal topics:

- `market-signal.ingested`
- `market-signal.normalized`

Product telemetry topics:

- `product-telemetry.ingested`
- `product-telemetry.normalized`

Workflow topics:

- `opportunity.scored`
- `committee.resolved`
- `draft.generated`
- `compliance.checked`
- `approval.recorded`
- `handoff.generated`

Current note:

- Redpanda is provisioned and event publish hooks exist.
- The pilot primarily stores state in Postgres and executes workflow logic in the API.

## Main Screens

### Account Queue

Path: `/`

Purpose:

- Show ranked interested accounts.
- Run prompt-based market discovery.
- Manage scheduled discovery jobs.
- Review candidate inbox.
- Add selected candidates to the interested queue.

### Account Detail

Path: `/accounts/:id`

Purpose:

- Show why this account matters.
- Show cited evidence and rationale.
- Show stakeholders.
- Show nurture sequences and pending touches.
- Open draft review.

### Draft Review

Path: `/drafts/:id`

Purpose:

- Review generated outreach.
- Inspect citations.
- Inspect compliance receipt.
- Approve, reject, or edit.

### Closed-Won Handoff

Path: `/deals/:id/handoff`

Purpose:

- Generate/view activation handoff.
- Show blockers, tasks, telemetry, and stakeholders.
- Start post-sale activation tracking.

## Internal APIs

### System

- `GET /health`
- `GET /system/status`

### Product Context

- `GET /product-contexts`
- `POST /product-contexts`

### Shadow CRM

- `GET /accounts`
- `POST /accounts`
- `GET /accounts/:id/brief`
- `POST /accounts/:id/contacts`

### Signal and Telemetry Ingestion

- `POST /signals/ingest`
- `POST /telemetry/ingest`

### Workflows and Agent

- `POST /workflows/opportunity-refresh`
- `POST /agent/run`
- `POST /automation/run-due`

### Discovery

- `POST /discovery/search`
- `GET /discovery/jobs`
- `POST /discovery/jobs`
- `POST /discovery/jobs/:id/run`
- `GET /discovery/inbox`
- `POST /discovery/candidates/add`

### Drafts and Approvals

- `GET /drafts/:id`
- `POST /drafts/:id/edit`
- `POST /drafts/:id/approve`
- `POST /drafts/:id/reject`

### Handoff

- `GET /deals/:id/handoff`
- `POST /deals/:id/handoff`

## Docker Run

Copy env values:

```bash
cp .env.example .env
```

Fill in provider secrets in `.env`:

```bash
NVIDIA_API_KEY=your_nvidia_key
OPENROUTER_API_KEY=your_openrouter_key
```

Start the full stack:

```bash
docker compose up -d --build
```

Open the app:

```text
http://localhost:3000
```

Health check:

```text
http://localhost:3000/api/health
```

API docs:

```text
http://localhost:3000/api/docs
```

Stop the stack:

```bash
docker compose down
```

## Cloud Deploy

For a single cloud VM or single-host deployment, the command stays the same:

```bash
docker compose up -d --build
```

Recommended public env values:

```bash
APP_PORT=80
APP_PUBLIC_ORIGIN=https://your-domain
NEXT_PUBLIC_API_BASE_URL=/api
API_BASE_URL=http://api:8000
DISCOVERY_SCHEDULER_ENABLED=true
AUTOMATION_POLL_SECONDS=300
```

Keep internal service URLs on Docker hostnames:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/blostem
CLICKHOUSE_URL=http://clickhouse:8123
QDRANT_URL=http://qdrant:6333
REDPANDA_BROKERS=redpanda:9092
OBJECT_STORAGE_ENDPOINT=http://minio:9000
TEMPORAL_SERVER_URL=temporal:7233
```

Only the reverse proxy should be public. Admin/debug ports for Postgres, MinIO, Temporal UI, ClickHouse, and Qdrant are bound to `127.0.0.1` on the Docker host by default.

## Environment Variables

Core app:

- `APP_PORT`: public host port for Nginx proxy.
- `APP_PUBLIC_ORIGIN`: public app origin used in provider headers.
- `API_ROOT_PATH`: API mount path behind proxy, default `/api`.
- `NEXT_PUBLIC_API_BASE_URL`: browser API base, default `/api`.
- `API_BASE_URL`: server/container API base.

Models:

- `NVIDIA_API_KEY`
- `NVIDIA_BASE_URL`
- `NVIDIA_MODEL_KIMI`
- `NVIDIA_KIMI_FALLBACK_MODELS`: ordered comma-separated NVIDIA Kimi fallback models, defaulting to `moonshotai/kimi-k2-thinking,moonshotai/kimi-k2-instruct-0905,moonshotai/kimi-k2-instruct`.
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_MODEL_GEMMA`

Automation:

- `DISCOVERY_SCHEDULER_ENABLED`
- `AUTOMATION_POLL_SECONDS`
- `LIVE_SEARCH_PROVIDER`: `auto`, `tavily`, or `duckduckgo`.
- `LIVE_SEARCH_MAX_RESULTS`: max live research results saved per prompt.
- `TAVILY_API_KEY`: optional Tavily key. If omitted, the agent uses DuckDuckGo fallback.

Data services:

- `DATABASE_URL`
- `CLICKHOUSE_URL`
- `CLICKHOUSE_DATABASE`
- `QDRANT_URL`
- `REDPANDA_BROKERS`
- `OBJECT_STORAGE_ENDPOINT`
- `OBJECT_STORAGE_BUCKET`
- `OBJECT_STORAGE_ACCESS_KEY`
- `OBJECT_STORAGE_SECRET_KEY`
- `TEMPORAL_SERVER_URL`
- `TEMPORAL_NAMESPACE`

## Bootstrap Data

To seed the workspace with public BFSI targets plus Google News RSS signals:

```bash
docker compose exec api python apps/api/scripts/seed_real_data.py
```

If you have the real Blostem product context as JSON:

```bash
docker compose exec api python apps/api/scripts/seed_real_data.py --product-context-file /app/path/to/product-context.json --build-handoffs
```

## Testing

Backend tests:

```bash
python -m pytest apps/api/tests -q
```

Frontend typecheck:

```bash
npm run lint --workspace web
```

Frontend production build:

```bash
npm run build --workspace web
```

Docker config validation:

```bash
docker compose config --quiet
```

## What Is Real vs Pilot-Limited

Implemented and working in the pilot:

- Shadow CRM records in Postgres.
- Product contexts.
- Account/contact creation.
- Signal and telemetry ingestion.
- Prompt-based market discovery.
- Sidebar live-company research with cited signal persistence.
- Scheduled discovery jobs and candidate inbox.
- Candidate cleaning, grouping, scoring, and import.
- Opportunity scoring and account next action.
- CTO/CFO/Legal draft creation.
- Compliance receipts with citation-required claim checks.
- Human approval/rejection/edit endpoints.
- Nurture sequence and touch state.
- Closed-won handoff generation.
- Telemetry-triggered activation nudge drafts.
- Dockerized full-stack deployment.

Pilot limitations:

- Discovery uses structured public news/search ingestion, not a full autonomous crawler of the entire internet.
- Live company research is query-driven through Tavily or DuckDuckGo. It does not browse private/paywalled sources or execute arbitrary web scraping.
- External email sending is not enabled; drafts stop at human approval.
- Temporal is provisioned, but most workflow logic currently runs synchronously inside the API.
- ClickHouse, Qdrant, and MinIO are included as infrastructure foundations, but the current pilot leans mostly on Postgres.
- CRM sync adapters are deferred; the Postgres Shadow CRM is the system of record for v1.
- Live model quality depends on valid NVIDIA and OpenRouter keys. Deterministic local fallbacks keep the app testable when providers are unavailable.

## Suggested Demo Flow

1. Start Docker with `docker compose up -d --build`.
2. Open `http://localhost:3000`.
3. Create or seed a Product Context.
4. Run External Discovery with a prompt like `Find Indian banks with security, fraud, or compliance triggers`.
5. Review ranked candidates.
6. Add one candidate to the interested queue.
7. Open the account detail page.
8. Review the opportunity rationale, citations, stakeholder map, and nurture state.
9. Open Draft Review for CTO/CFO/Legal drafts.
10. Inspect the compliance receipt and approve or reject the draft.
11. Create a closed-won handoff.
12. Ingest telemetry such as `setup_started`.
13. Confirm the system creates an activation nudge draft for review.
