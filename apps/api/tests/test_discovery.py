import os
from datetime import UTC, datetime

from fastapi.testclient import TestClient


os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./apps/api/test.db"
os.environ.pop("NVIDIA_API_KEY", None)
os.environ.pop("OPENROUTER_API_KEY", None)

from apps.api.app.main import app  # noqa: E402
from apps.api.app.services.discovery import MarketDiscoveryService, extract_org_names  # noqa: E402


def test_extract_org_names_prefers_bfsi_targets() -> None:
    names = extract_org_names(
        "Acme Bank hit by data breach as digital onboarding grows - Example News",
        "Acme Bank is reviewing the incident after the breach.",
        "Example News",
    )
    assert "Acme Bank" in names


def test_discovery_search_and_import(monkeypatch) -> None:
    async def fake_fetch_batches(self, client, queries):  # noqa: ANN001
        return [
            {
                "title": "Acme Bank hit by data breach as digital onboarding grows - Example News",
                "link": "https://example.com/acme-breach",
                "description": "Acme Bank is accelerating digital onboarding after a recent breach disclosure.",
                "source": "Example News",
                "published_at": datetime.now(UTC),
                "query": queries[0],
            },
            {
                "title": "Acme Bank hires new CIO to modernize security controls - Example News",
                "link": "https://example.com/acme-cio",
                "description": "The bank appointed a new CIO to improve security and compliance execution.",
                "source": "Example News",
                "published_at": datetime.now(UTC),
                "query": queries[0],
            },
        ]

    async def fake_resolve_article_url(self, client, url):  # noqa: ANN001
        return url

    monkeypatch.setattr(MarketDiscoveryService, "_fetch_batches", fake_fetch_batches)
    monkeypatch.setattr(MarketDiscoveryService, "_resolve_article_url", fake_resolve_article_url)

    with TestClient(app) as client:
        product_context_response = client.post(
            "/product-contexts",
            json={
                "key": "discovery-security",
                "name": "Discovery Security Engine",
                "version": "1.0.0",
                "overview": "Maps security and onboarding triggers to BFSI outreach.",
                "icp_segments": ["Bank", "Fintech"],
                "trigger_patterns": ["data breach", "security", "digital onboarding", "compliance"],
                "buyer_personas": [{"persona": "CTO"}],
            },
        )
        assert product_context_response.status_code in {200, 409}

        search_response = client.post(
            "/discovery/search",
            json={
                "product_context_key": "discovery-security",
                "prompt": "Find Indian banks with security or digital onboarding triggers.",
                "limit": 5,
            },
        )
        assert search_response.status_code == 200
        payload = search_response.json()
        assert payload["candidates"]
        candidate = payload["candidates"][0]
        assert candidate["name"] == "Acme Bank"

        import_response = client.post(
            "/discovery/candidates/add",
            json={"candidate": candidate, "refresh_workflow": True},
        )
        assert import_response.status_code == 200
        import_payload = import_response.json()
        assert import_payload["account"]["name"] == "Acme Bank"
        assert import_payload["imported_signal_count"] >= 0
        assert import_payload["opportunity_id"] is not None
        assert import_payload["draft_id"] is not None
        account_id = import_payload["account"]["id"]

        brief_response = client.get(f"/accounts/{account_id}/brief")
        assert brief_response.status_code == 200
        brief_payload = brief_response.json()
        draft_personas = {draft["persona"] for draft in brief_payload["drafts"]}
        assert {"CTO", "CFO", "Legal"}.issubset(draft_personas)
        assert any(sequence["kind"] == "prospect_outreach" for sequence in brief_payload["nurture_sequences"])
        assert len(brief_payload["nurture_touches"]) >= 3

        handoff_response = client.post(f"/deals/{account_id}/handoff")
        assert handoff_response.status_code == 200
        telemetry_response = client.post(
            "/telemetry/ingest",
            json={
                "account_id": account_id,
                "event_type": "setup_started",
                "detected_at": datetime.now(UTC).isoformat(),
                "payload": {"source": "test"},
            },
        )
        assert telemetry_response.status_code == 200
        post_sale_brief = client.get(f"/accounts/{account_id}/brief").json()
        assert any(sequence["kind"] == "post_sale_activation" for sequence in post_sale_brief["nurture_sequences"])
        assert any(touch["touch_kind"] == "activation_nudge" for touch in post_sale_brief["nurture_touches"])

        queue_response = client.get("/accounts")
        assert queue_response.status_code == 200
        assert any(item["name"] == "Acme Bank" for item in queue_response.json()["items"])


def test_scheduled_discovery_stores_reviewable_inbox(monkeypatch) -> None:
    async def fake_fetch_batches(self, client, queries):  # noqa: ANN001
        return [
            {
                "title": "Zenith Bank launches new digital onboarding controls - Example News",
                "link": "https://example.com/zenith-onboarding",
                "description": "Zenith Bank is investing in digital onboarding and fraud controls.",
                "source": "Example News",
                "published_at": datetime.now(UTC),
                "query": queries[0],
            },
        ]

    async def fake_resolve_article_url(self, client, url):  # noqa: ANN001
        return url

    monkeypatch.setattr(MarketDiscoveryService, "_fetch_batches", fake_fetch_batches)
    monkeypatch.setattr(MarketDiscoveryService, "_resolve_article_url", fake_resolve_article_url)

    with TestClient(app) as client:
        product_context_response = client.post(
            "/product-contexts",
            json={
                "key": "scheduled-discovery",
                "name": "Scheduled Discovery",
                "version": "1.0.0",
                "overview": "Finds BFSI onboarding triggers.",
                "icp_segments": ["Fintech", "Payments"],
                "trigger_patterns": ["digital onboarding", "fraud", "controls"],
                "buyer_personas": [{"persona": "CTO"}],
            },
        )
        assert product_context_response.status_code in {200, 409}

        job_response = client.post(
            "/discovery/jobs",
            json={
                "product_context_key": "scheduled-discovery",
                "prompt": "Find Indian fintechs with onboarding triggers.",
                "cadence_minutes": 60,
                "limit": 5,
            },
        )
        assert job_response.status_code == 200
        job_id = job_response.json()["id"]

        run_response = client.post(f"/discovery/jobs/{job_id}/run")
        assert run_response.status_code == 200
        assert run_response.json()["stored_count"] >= 1

        inbox_response = client.get("/discovery/inbox")
        assert inbox_response.status_code == 200
        records = inbox_response.json()
        zenith = next(record for record in records if record["candidate"]["name"] == "Zenith Bank")
        assert zenith["confidence_score"] > 0
        assert zenith["source_count"] >= 1

        import_response = client.post(
            "/discovery/candidates/add",
            json={
                "candidate": zenith["candidate"],
                "candidate_record_id": zenith["id"],
                "refresh_workflow": True,
            },
        )
        assert import_response.status_code == 200

        imported_records = client.get("/discovery/inbox?status=imported").json()
        assert any(record["id"] == zenith["id"] for record in imported_records)
