import os
import time
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient


test_db = Path("apps/api/test.db")
if test_db.exists():
    try:
        test_db.unlink()
    except PermissionError:
        pass

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./apps/api/test.db"
os.environ.pop("NVIDIA_API_KEY", None)
os.environ.pop("OPENROUTER_API_KEY", None)

from apps.api.app.main import app  # noqa: E402
from apps.api.app.database import Base, engine  # noqa: E402
from apps.api.app.schemas import AgentResult, ModelRouteDecision  # noqa: E402
from apps.api.app.services.agent import AgentService  # noqa: E402
from apps.api.app.services.live_search import LiveCompanyResearchFinding, LiveCompanyResearchTool  # noqa: E402


async def _reset_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


asyncio.run(_reset_database())


def test_empty_runtime_and_manual_data_creation() -> None:
    with TestClient(app) as client:
        queue_response = client.get("/accounts")
        assert queue_response.status_code == 200
        assert queue_response.json()["items"] == []

        status_response = client.get("/system/status")
        assert status_response.status_code == 200
        assert status_response.json()["crm_mode"] == "shadow_crm_empty"

        product_context_response = client.post(
            "/product-contexts",
            json={
                "key": "security-posture",
                "name": "Security Posture",
                "version": "1.0.0",
                "overview": "Maps security triggers to outreach.",
                "icp_segments": ["bank"],
                "trigger_patterns": ["security", "fraud"],
                "buyer_personas": [{"persona": "CTO"}],
            },
        )
        assert product_context_response.status_code == 200

        account_response = client.post(
            "/accounts",
            json={
                "name": "Live Test Bank",
                "segment": "bank",
                "territory": "India",
                "summary": "Real runtime test account.",
                "metadata": {"tier": "pilot"},
            },
        )
        assert account_response.status_code == 200
        account_id = account_response.json()["id"]

        contact_response = client.post(
            f"/accounts/{account_id}/contacts",
            json={
                "name": "Asha Nair",
                "role": "CTO",
                "persona": "CTO",
                "email": "asha.nair@example.org",
            },
        )
        assert contact_response.status_code == 200

        queue_after_create = client.get("/accounts")
        assert queue_after_create.status_code == 200
        assert len(queue_after_create.json()["items"]) == 1

        brief_response = client.get(f"/accounts/{account_id}/brief")
        assert brief_response.status_code == 200
        assert brief_response.json()["account"]["name"] == "Live Test Bank"


def test_sidebar_deep_research_saves_live_search_signal(monkeypatch) -> None:
    async def fake_live_company_research(self, *, company_name, prompt, limit=None):  # noqa: ANN001
        assert company_name == "Research Test Bank"
        assert "deep research" in prompt.lower()
        return [
            LiveCompanyResearchFinding(
                title="Research Test Bank appoints new technology leader",
                summary="Research Test Bank appointed a technology leader while reviewing compliance controls.",
                source_url="https://example.com/research-test-bank-tech",
                provider="duckduckgo",
                query=f'"{company_name}" {prompt}',
                published_at=datetime.now(UTC),
            )
        ]

    monkeypatch.setattr(LiveCompanyResearchTool, "live_company_research", fake_live_company_research)

    with TestClient(app) as client:
        account_response = client.post(
            "/accounts",
            json={
                "name": "Research Test Bank",
                "segment": "bank",
                "territory": "India",
                "summary": "Account used to verify live sidebar research.",
                "metadata": {"tier": "pilot"},
            },
        )
        assert account_response.status_code == 200
        account_id = account_response.json()["id"]

        agent_response = client.post(
            "/agent/run",
            json={
                "account_id": account_id,
                "prompt": "Do deep research on recent executive hires and compliance issues in 2026.",
            },
        )
        assert agent_response.status_code == 200
        agent_payload = agent_response.json()
        assert agent_payload["entities"]["live_research_saved_signal_count"] == 1
        assert any(citation["source_url"] == "https://example.com/research-test-bank-tech" for citation in agent_payload["citations"])
        assert any("live_company_research" in note for note in agent_payload["notes"])

        brief_response = client.get(f"/accounts/{account_id}/brief")
        assert brief_response.status_code == 200
        brief_payload = brief_response.json()
        assert any(signal["source_type"] == "live_company_research" for signal in brief_payload["signals"])


def test_agent_jobs_complete_via_polling(monkeypatch) -> None:
    async def fake_run(self, request):  # noqa: ANN001
        return AgentResult(
            prompt=request.prompt or "",
            automation=request.automation,
            summary="Async agent job completed.",
            suggested_actions=["Open the queue."],
            route=ModelRouteDecision(
                workflow="agent-assistant",
                target_profile="complex_reasoner",
                provider="local",
                model="test",
                reason="Test route.",
                thinking=False,
                requires_manual_review_on_failure=False,
            ),
            citations=[],
            notes=["Completed in test."],
            entities={"account_id": None, "draft_id": None},
            automation_status="completed",
            used_live_model=False,
        )

    monkeypatch.setattr(AgentService, "run", fake_run)

    with TestClient(app) as client:
        create_response = client.post(
            "/agent/jobs",
            json={"prompt": "Summarize the queue."},
        )
        assert create_response.status_code == 200
        job_id = create_response.json()["id"]

        final_payload = None
        for _ in range(20):
            poll_response = client.get(f"/agent/jobs/{job_id}")
            assert poll_response.status_code == 200
            final_payload = poll_response.json()
            if final_payload["status"] == "completed":
                break
            time.sleep(0.05)

        assert final_payload is not None
        assert final_payload["status"] == "completed"
        assert final_payload["result"]["summary"] == "Async agent job completed."
