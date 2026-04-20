# Blostem B2B AI Marketing Engine

Blostem is an India-first BFSI pilot for an internal AI-powered sales and marketing engine. It helps sales reps discover high-intent enterprise accounts, map buying committees, generate compliant persona-specific outreach, manage a Shadow CRM, and keep post-sale momentum moving through activation handoff and nudging.

This is not a generic chatbot. It is a workflow-driven sales cockpit with an AI copilot and automation layer:

`Product Context -> Market Discovery -> AI Triage -> Human Queue -> Deep Research -> Committee Mapping -> Persona Drafting -> Compliance Gate -> Human Approval -> Reachout -> Post-Sale Nudging`

## What the Product Does

Blostem solves four core problems in enterprise BFSI selling:

- Targeting friction: find which banks, fintechs, NBFCs, insurers, or agencies have a reason to care right now.
- Buying committee complexity: generate different messaging for CTO, CFO, and Legal/Compliance instead of one generic email.
- Compliance risk: block unsupported or uncited claims before anything reaches a customer.
- Activation stall: continue tracking momentum after closed-won and generate nudges when rollout slows down.

## Current Implementation Status

The repo currently contains a working pilot with:

- `Next.js` frontend for the sales cockpit.
- `FastAPI` backend for APIs, orchestration, and AI routing.
- `Postgres` Shadow CRM for accounts, contacts, drafts, approvals, activity, nurture state, and handoff state.
- Public market discovery for net-new accounts.
- A right-rail AI copilot sidebar with async job execution.
- Live company research using Tavily or DuckDuckGo fallback.
- Committee-wide drafting for `CTO`, `CFO`, and `Legal`.
- Sentence-level compliance review with citation enforcement.
- Human approval and reachout flow.
- Nurture sequences with follow-up state.
- Closed-won handoff plus telemetry-triggered activation nudges.
- Full Docker deployment through one `docker compose` command.

Infrastructure services are provisioned in Docker:

- `Postgres`
- `Redpanda`
- `ClickHouse`
- `Qdrant`
- `MinIO`
- `Temporal`
- `Temporal UI`
- `Nginx` reverse proxy

The pilot still executes most business workflows directly in the API service, while the stack is already shaped for deeper Temporal worker expansion.

## Product Features

### 1. Shadow CRM

The pilot uses Postgres as the CRM system of record instead of Salesforce or HubSpot.

What it stores:

- Accounts
- Contacts
- Pipeline stages
- Scores and next actions
- Opportunities
- Draft assets
- Approvals and review history
- Activity log
- Nurture sequences and touches
- Activation briefs
- Discovery jobs and candidate inbox records

Why it exists:

- Zero third-party CRM dependency in v1
- Better data privacy for BFSI
- Faster internal workflows without external API latency

### 2. Product Context Catalog

Product Context tells the system what Blostem sells and how to reason about relevance.

Each Product Context can define:

- `key`, `name`, `version`, `overview`
- ICP segments such as `Bank`, `Fintech`, `NBFC`, `Insurance`
- Trigger patterns such as `security`, `fraud`, `digital onboarding`, `compliance`
- Disqualifiers
- Approved claims
- Buyer personas
- Activation playbook steps

Why it matters:

- Discovery uses it to search the right market signals
- Scoring uses it to estimate fit
- Drafting uses it to anchor messaging
- Committee mapping uses it to decide which stakeholders matter

### 3. External Discovery

This is the “Detective” capability for finding net-new interested organizations.

What it does:

- Accepts a prompt like `Find Indian banks with recent compliance or security triggers`
- Builds search queries from the Product Context and prompt
- Pulls structured public search/news results
- Extracts likely organization names
- Cleans and canonicalizes entities
- Groups duplicate hits
- Scores candidates by:
  - interest
  - fit
  - freshness
  - confidence
  - source count
- Shows a reviewable candidate list before import

What is supported now:

- Prompt-based discovery
- Scheduled discovery jobs
- Candidate inbox
- Manual import into the interested queue

What is not yet a full web crawler:

- It does not scrape the whole web indiscriminately
- It relies on controlled public search/news ingestion

### 4. Scheduled External Ingestion

Discovery can run on a schedule, not only from a manual prompt.

What it does:

- Stores recurring discovery jobs in Postgres
- Runs due jobs through the scheduler or `POST /automation/run-due`
- Saves results into a reviewable inbox
- Keeps prompt-only discovery working too

Useful env vars:

- `DISCOVERY_SCHEDULER_ENABLED`
- `AUTOMATION_POLL_SECONDS`

### 5. Account Queue

The queue is the rep’s working CRM list.

What it shows:

- tracked accounts
- intent score
- fit score
- freshness score
- top signal
- primary product context
- recommended next action

Why it matters:

- Reps stop working from a cold list
- They start from ranked, evidence-backed priorities

### 6. Account Detail

This is the “glass box” screen for one account.

What it shows:

- account summary
- current next action
- cited signals
- opportunity rationale
- stakeholder map
- recent activity
- nurture sequences
- pending touches
- draft links
- activation handoff if present

Why it matters:

- The rep can see why the system thinks this account matters
- Every important claim is backed by evidence

### 7. AI Copilot Sidebar

The app includes a right-side copilot-style sidebar for prompting and automation.

What it can do:

- summarize the current account
- explain why an account is high intent
- refresh opportunity scoring
- review a draft
- build a handoff
- run deep live research on an open account
- run discovery-style prompts when no account is open

Important implementation detail:

- Sidebar requests now run asynchronously through job polling
- The UI no longer has to sit on one long blocking request

Related endpoints:

- `POST /agent/run`
- `POST /agent/jobs`
- `GET /agent/jobs/:id`

### 8. Live Company Research

This is the agent’s deterministic live research tool.

What triggers it:

- prompts like `deep research`, `latest`, `recent`, `executive hires`, `RBI`, `penalty`, `compliance issues`, or year-based research requests

What it does:

- searches the public web with account-aware queries
- uses Tavily when configured
- falls back to DuckDuckGo when Tavily is not configured
- converts findings into cited market signals
- saves those signals to the account record
- answers the user with a fresh, grounded summary

Result:

- research does not live only in chat
- it becomes reusable account evidence inside the app

### 9. Committee Mapping and Persona Drafting

This is the “Chameleon” capability.

What it does:

- maps the buying committee
- creates stakeholder-specific outreach drafts
- currently targets:
  - `CTO`
  - `CFO`
  - `Legal`

Drafts are tailored differently:

- CTO: technical priorities, controls, platform concerns
- CFO: operational risk, financial implications, prioritization
- Legal: governance, compliance posture, review concerns

The system stores separate drafts and touches for each persona.

### 10. Compliance Review

This is the “Lawyer” capability.

What it does:

- splits text into sentence-level checks
- classifies sentences as factual claims or allowed boilerplate
- requires support for sensitive factual claims
- blocks unsupported:
  - numeric claims
  - dated claims
  - comparative claims
  - ROI claims
  - security claims
  - compliance claims
  - customer claims

What passes without citation:

- simple connective or introductory language like:
  - `This may be useful to compare notes.`
  - `I thought this might be relevant to your team.`

### 11. Draft Review and Human Approval

Nothing should go out without a human in the loop.

What the rep can do:

- open a draft
- inspect citations
- inspect structured rationale
- inspect the compliance receipt
- edit the draft
- re-run compliance on the edited version
- approve or reject

Approval also updates related nurture state.

### 12. Reachout

Approved drafts can be handed to the outbound email layer.

Current behavior:

- outbound send support exists through SMTP
- demo/test mode can redirect every email to a safe override inbox
- if SMTP is not configured, approval still works and the send is skipped cleanly

### 13. Nurture Sequences

Nurture is tracked as explicit sequence state, not just free-form chat.

What it stores:

- sequence kind
- current round
- max rounds
- cadence days
- next touch time
- touch records
- linked drafts

What it does:

- creates initial committee outreach touches
- creates follow-up touches when due
- pauses when max rounds are reached

### 14. Closed-Won Handoff and Activation Nudging

This is the “Coach” capability.

What it does:

- creates a 30-day activation handoff
- captures blockers, tasks, stakeholders, and telemetry highlights
- starts a post-sale sequence
- watches telemetry
- creates activation nudge drafts when rollout appears stalled

Examples of completion telemetry:

- `login_completed`
- `workspace_activated`
- `activation_completed`
- `first_value_reached`

Examples of early or stalled rollout telemetry:

- `setup_started`
- `invite_sent`
- `questionnaire_opened`

## End-to-End Flow

The currently implemented flow is:

1. Create a Product Context.
2. Run prompt-based discovery or scheduled discovery.
3. Review ranked candidates in the candidate inbox.
4. Import a candidate into the interested account queue.
5. Open the account.
6. Run opportunity refresh.
7. Review the committee drafts for CTO, CFO, and Legal.
8. Run or inspect compliance.
9. Approve or reject the draft.
10. Send or record reachout.
11. Create a closed-won handoff.
12. Ingest telemetry.
13. Review activation nudge drafts if rollout is slow.

## AI Model Routing

The backend uses two pinned model profiles.

### Complex Reasoner

- provider: `NVIDIA`
- primary model: `moonshotai/kimi-k2.5`
- fallback models:
  - `moonshotai/kimi-k2-thinking`
  - `moonshotai/kimi-k2-instruct-0905`
  - `moonshotai/kimi-k2-instruct`

Used for:

- signal triage
- committee mapping
- compliance review
- ambiguous or high-risk reasoning
- multi-source synthesis
- deep live research summarization

### Draft Executor

- provider: `OpenRouter`
- model: `google/gemma-4-31b-it`

Used for:

- grounded draft generation
- short rewrites
- summaries
- subject line variants
- formatted call briefs

### Reliability Behavior

To keep the pilot usable in the real world, the system also includes:

- deterministic local fallbacks when providers fail
- NVIDIA model fallback order
- provider error cooldowns so repeated failures do not stall the whole workflow
- shorter draft timeouts than deep-research/agent timeouts

## Reliability and Operational Guards

Recent reliability work includes:

- async sidebar jobs instead of one long blocking prompt request
- provider fallback for NVIDIA Kimi models
- provider health cooldown so repeated bad upstream responses do not keep blocking every request
- faster event-bus publish failure handling when Redpanda is unavailable
- test-safe scheduler behavior

These changes reduce the “working on that…” stall behavior and make the local and Docker workflows degrade more gracefully.

## Architecture

```text
Browser
  |
  | http://localhost:3000
  v
Nginx reverse proxy
  |---- /      -> Next.js web app
  |---- /api   -> FastAPI backend

FastAPI backend
  |---- Postgres   -> Shadow CRM + workflow state
  |---- Redpanda   -> event topics
  |---- ClickHouse -> analytics / facts foundation
  |---- Qdrant     -> retrieval foundation
  |---- MinIO      -> raw source document foundation
  |---- Temporal   -> workflow infrastructure
  |---- NVIDIA     -> Kimi complex reasoner
  |---- OpenRouter -> Gemma draft executor
```

## Main Screens

### Account Queue

Path: `/`

Used for:

- seeing ranked accounts
- running discovery
- managing scheduled jobs
- reviewing candidate inbox
- importing candidates into the queue

### Account Detail

Path: `/accounts/:id`

Used for:

- seeing account rationale
- reviewing signals and citations
- reviewing stakeholders
- tracking nurture state
- launching deeper research and draft review

### Draft Review

Path: `/drafts/:id`

Used for:

- reading the draft
- reviewing compliance
- editing
- approving or rejecting

### Handoff

Path: `/deals/:id/handoff`

Used for:

- creating and reviewing the activation brief
- seeing blockers and tasks
- checking telemetry context

## Internal API Surface

### Health and Status

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

### Signal and Telemetry

- `POST /signals/ingest`
- `POST /telemetry/ingest`

### Discovery

- `POST /discovery/search`
- `GET /discovery/jobs`
- `POST /discovery/jobs`
- `POST /discovery/jobs/:id/run`
- `GET /discovery/inbox`
- `POST /discovery/candidates/add`

### Workflow and Agent

- `POST /workflows/opportunity-refresh`
- `POST /agent/run`
- `POST /agent/jobs`
- `GET /agent/jobs/:id`
- `POST /automation/run-due`

### Drafts and Approvals

- `GET /drafts/:id`
- `POST /drafts/:id/edit`
- `POST /drafts/:id/approve`
- `POST /drafts/:id/reject`

### Handoff

- `GET /deals/:id/handoff`
- `POST /deals/:id/handoff`

## Event Topic Families

Market signals:

- `market-signal.ingested`
- `market-signal.normalized`

Product telemetry:

- `product-telemetry.ingested`
- `product-telemetry.normalized`

Workflow events:

- `opportunity.scored`
- `committee.resolved`
- `draft.generated`
- `compliance.checked`
- `approval.recorded`
- `handoff.generated`

## Environment Variables

### Core App

- `APP_PORT`
- `APP_PUBLIC_ORIGIN`
- `API_ROOT_PATH`
- `NEXT_PUBLIC_API_BASE_URL`
- `API_BASE_URL`
- `DATABASE_URL`

### AI Providers

- `NVIDIA_API_KEY`
- `NVIDIA_BASE_URL`
- `NVIDIA_MODEL_KIMI`
- `NVIDIA_KIMI_FALLBACK_MODELS`
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_MODEL_GEMMA`

### Reliability and Automation

- `DISCOVERY_SCHEDULER_ENABLED`
- `AUTOMATION_POLL_SECONDS`
- `PROVIDER_ERROR_COOLDOWN_SECONDS`
- `DRAFT_MODEL_TIMEOUT_SECONDS`
- `AGENT_MODEL_TIMEOUT_SECONDS`
- `EVENT_PUBLISH_TIMEOUT_MS`

### Live Research

- `LIVE_SEARCH_PROVIDER`
- `LIVE_SEARCH_MAX_RESULTS`
- `TAVILY_API_KEY`

### Data Services

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

### Email

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `DEMO_EMAIL_OVERRIDE`

## Local Run

Create `.env` from the example and fill in the provider keys:

```bash
cp .env.example .env
```

Start the full stack:

```bash
docker compose up -d --build
```

Open:

- app: `http://localhost:3000`
- health: `http://localhost:3000/api/health`
- docs: `http://localhost:3000/api/docs`

Stop:

```bash
docker compose down
```

## Cloud Deployment

The deployment model is intentionally simple:

```bash
docker compose up -d --build
```

Recommended public settings:

```bash
APP_PORT=80
APP_PUBLIC_ORIGIN=https://your-domain
NEXT_PUBLIC_API_BASE_URL=/api
API_BASE_URL=http://api:8000
```

Keep internal services on Docker hostnames:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/blostem
CLICKHOUSE_URL=http://clickhouse:8123
QDRANT_URL=http://qdrant:6333
REDPANDA_BROKERS=redpanda:9092
OBJECT_STORAGE_ENDPOINT=http://minio:9000
TEMPORAL_SERVER_URL=temporal:7233
```

Only the reverse proxy should be publicly reachable.

## Testing

Backend:

```bash
python -m pytest apps/api/tests -q
```

Frontend lint:

```bash
npm run lint --workspace web
```

Frontend production build:

```bash
npm run build --workspace web
```

Docker config:

```bash
docker compose config --quiet
```

## What Is Real vs Pilot-Limited

Working now:

- Product contexts
- Prompt-based discovery
- Scheduled discovery jobs
- Candidate inbox
- Candidate import to queue
- Account queue and detail
- Async AI copilot sidebar
- Live account research
- Opportunity scoring
- Committee mapping
- CTO/CFO/Legal drafts
- Compliance receipts
- Draft edit / approve / reject
- SMTP-backed reachout when configured
- Nurture sequence state
- Closed-won handoff
- Telemetry-triggered activation nudges
- Full Docker stack

Pilot limitations:

- Discovery is structured public search/news ingestion, not a fully autonomous unrestricted internet crawler
- Most workflow execution still runs in the API service rather than full Temporal workers
- ClickHouse, Qdrant, and MinIO are provisioned but not yet fully exploited
- External CRM sync is deferred; Postgres Shadow CRM is the v1 system of record
- Deep model quality depends on valid provider keys and external provider availability

## Suggested Demo Flow

1. Start the stack with `docker compose up -d --build`.
2. Create a Product Context for one Blostem product.
3. Run discovery for interested Indian BFSI targets.
4. Add one candidate into the queue.
5. Open that account.
6. Ask the copilot for deep research.
7. Refresh the opportunity.
8. Review the CTO/CFO/Legal drafts.
9. Check the compliance receipt.
10. Approve one draft.
11. Create a handoff.
12. Ingest telemetry like `setup_started`.
13. Review the activation nudge draft.
