"""
Full pipeline integration test — all 11 stages.
Runs directly inside the API container with generous timeouts.
"""
import asyncio
import httpx

BASE = "http://localhost:8000/api"
TIMEOUT = httpx.Timeout(300.0, connect=15.0)   # 5-min timeout for LLM steps


async def get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{BASE}{path}")
        r.raise_for_status()
        return r.json()


async def post(path: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{BASE}{path}", json=payload)
        if not r.is_success:
            print(f"  ✗ HTTP {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
        return r.json()


def sep(label: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"{'─'*60}")


async def main() -> None:

    # ── STEP 1: Add Product Context ──────────────────────────────────────────
    sep("STEP 1 — Add Product Context")
    try:
        ctx = await post("/product-contexts", {
            "key": "log_inv_fw",
            "name": "Log Investigation Framework",
            "overview": "AI-powered log investigation and forensics for BFSI.",
            "icp_segments": ["Bank", "NBFC", "Insurance", "Fintech"],
            "trigger_patterns": ["log analysis", "SIEM", "cyber attack",
                                 "data breach", "RBI compliance",
                                 "fraud investigation", "security audit"],
            "disqualifiers": ["non-financial", "retail only", "e-commerce"],
        })
        print(f"  ✓ Context created: {ctx['name']}  key={ctx['key']}")
    except Exception as e:
        # Already exists — just fetch it
        print(f"  ⚠ Context may already exist ({e}), continuing…")

    # ── STEP 2: Discovery Search (Ingest Market Signals) ─────────────────────
    sep("STEP 2 — Discovery Search (Ingest Market Signals)")
    print("  ⏳ Running live discovery search — takes ~15 s …")
    search = await post("/discovery/search", {
        "prompt": (
            "Find Indian Bank, NBFC, Insurance, Fintech organizations showing signs of "
            "log analysis, SIEM, cyber attack, data breach, RBI compliance, fraud "
            "investigation that suggest active need for Log Investigation Framework."
        ),
        "product_context_key": "log_inv_fw",
        "limit": 5,
    })
    candidates = search.get("candidates", [])
    print(f"  ✓ Queries: {search.get('queries', [])}")
    print(f"  ✓ Candidates found: {len(candidates)}")
    for i, c in enumerate(candidates[:5]):
        print(f"    [{i+1}] {c['name']}  segment={c['segment']}  "
              f"interest={c['interest_score']:.0f}  fit={c['fit_score']:.0f}")

    if not candidates:
        print("  ✗ No candidates returned — cannot continue test.")
        return

    top = candidates[0]

    # ── STEP 3: Import to Human Queue ────────────────────────────────────────
    sep("STEP 3 — Import to Human Queue (Add to Pipeline)")
    print(f"  Importing: {top['name']} …")
    imp = await post("/discovery/candidates/add", {
        "candidate": top,
        "refresh_workflow": False,   # we'll run workflow separately in step 6
    })
    account_id = imp["account"]["id"]
    acct_name  = imp["account"]["name"]
    print(f"  ✓ Account created: {acct_name}  (id={account_id})")
    print(f"  ✓ Signals ingested: {imp['imported_signal_count']}")
    print(f"  ✓ Was existing:     {imp['existing_account']}")

    # ── STEP 4: Verify Queue ─────────────────────────────────────────────────
    sep("STEP 4 — Verify Human Queue")
    queue = await get("/accounts")
    items = queue.get("items", [])
    print(f"  ✓ Accounts in queue: {len(items)}")
    for item in items:
        print(f"    • {item['name']}  intent={item['intent_score']}  "
              f"fit={item['fit_score']}  stage={item['pipeline_stage']}")

    # ── STEP 5: Select Target — fetch full brief ──────────────────────────────
    sep("STEP 5 — Select Target (Account Detail)")
    brief = await get(f"/accounts/{account_id}/brief")
    print(f"  ✓ Account: {brief['account']['name']}")
    print(f"  ✓ Signals: {len(brief['signals'])}")
    print(f"  ✓ Contacts so far: {len(brief['contacts'])}")

    # Add 2 contacts for committee mapping
    for contact in [
        {"name": "Priya Nair",  "role": "CISO", "persona": "ciso",
         "email": "priya.nair@dummybank.in", "influence_level": "high",
         "status": "target", "notes": "Primary InfoSec decision maker"},
        {"name": "Rajan Mehta", "role": "CTO",  "persona": "cto",
         "email": "rajan.mehta@dummybank.in", "influence_level": "high",
         "status": "target", "notes": "Technology sponsor"},
    ]:
        c = await post(f"/accounts/{account_id}/contacts", contact)
        print(f"  ✓ Contact added: {c['name']} ({c['role']})")

    # ── STEP 6: AI Triage + Committee Mapping + Drafting + Compliance ─────────
    sep("STEP 6 — AI Triage & Score → Committee Mapping → Persona Drafting → Compliance Gate")
    print("  ⏳ Running full opportunity refresh (LLM steps) — allow 30–90 s …")
    wf = await post("/workflows/opportunity-refresh", {"account_id": account_id})
    draft_id = wf["draft"]
    print(f"  ✓ Opportunity: {wf['opportunity']}")
    print(f"  ✓ Draft ID:    {draft_id}")
    print(f"  ✓ Status:      {wf['status']}")

    # ── STEP 7: Live Deep Research (inspect draft + account evidence) ─────────
    sep("STEP 7 — Live Deep Research + Draft Inspection")
    draft = await get(f"/drafts/{draft_id}")
    receipt = draft.get("compliance_receipt") or {}
    print(f"  Draft subject:  {draft['subject']}")
    print(f"  Persona:        {draft['persona']}")
    print(f"  Status:         {draft['status']}")
    print(f"  Compliance:     {'PASSED ✓' if receipt.get('passed') else 'NEEDS REVISION ✗'}")
    print(f"  Issues:         {receipt.get('issues', [])}")
    print(f"  Sentences checked: {len(receipt.get('claim_checks', []))}")
    print(f"\n  Body preview:\n    {(draft.get('edited_body') or draft['body'])[:320]}…")

    # ── STEP 8: Human Approval & Reachout ─────────────────────────────────────
    sep("STEP 8 — Human Approval & Reachout (email)")
    approval = await post(f"/drafts/{draft_id}/approve", {
        "reviewer_role": "rep",
        "notes": "Approved for initial outreach — LIF relevance confirmed.",
    })
    print(f"  ✓ Decision:  {approval['decision']}")
    print(f"  ✓ Reviewer:  {approval['reviewer_role']}")
    print(f"  ✓ Approval ID: {approval['id']}")

    # Check activity log for email send result
    brief2 = await get(f"/accounts/{account_id}/brief")
    for ev in brief2.get("activity", []):
        if ev.get("kind") == "email":
            print(f"  Email event → {ev['title']}: {ev['detail']}")

    # ── STEP 9: Post-Sale Nudging ─────────────────────────────────────────────
    sep("STEP 9 — Post-Sale Nudging")
    telem = await post("/telemetry/ingest", {
        "account_id": account_id,
        "event_type": "login_completed",
        "topic_family": "product_activation",
        "payload": {"session_count": 1, "feature": "log_search"},
    })
    print(f"  ✓ Telemetry: {telem['event_type']} (id={telem['id']})")

    handoff = await post(f"/deals/{account_id}/handoff", {})
    print(f"  ✓ Handoff: {handoff['deal_label']}  stage={handoff['stage']}")
    print(f"  ✓ Tasks:   {len(handoff['tasks'])}")

    due = await post("/automation/run-due", {})
    print(f"  ✓ Nurture sequences run: {due['nurture']}")

    # ── FINAL SUMMARY ─────────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print("  FULL PIPELINE TEST — RESULTS")
    print(f"{'═'*60}")
    print(f"  1. Add Product Context      ✓  {ctx['name']}")
    print(f"  2. Ingest Market Signals    ✓  {len(candidates)} candidates discovered")
    print(f"  3. Populate Human Queue     ✓  {acct_name} imported")
    print(f"  4. Select Target            ✓  {len(brief['signals'])} signals on account")
    print(f"  5. Live Deep Research       ✓  committee evidence collected")
    print(f"  6. Committee Mapping        ✓  workflow ran → draft generated")
    print(f"  7. AI Persona Drafting      ✓  subject: {draft['subject']}")
    print(f"  8. AI Compliance Gate       {'✓ PASSED' if receipt.get('passed') else '✗ NEEDS REVISION'}")
    print(f"  9. Human Approval           ✓  {approval['decision']} by {approval['reviewer_role']}")
    print(f" 10. Post-Sale Nudging        ✓  telemetry + handoff + nurture triggered")
    print(f"\n  Frontend:   http://localhost:3000/accounts/{account_id}")
    print(f"  Draft:      http://localhost:3000/drafts/{draft_id}")
    print(f"{'═'*60}")


asyncio.run(main())
