import httpx
import pytest

from apps.api.app.config import Settings
from apps.api.app.schemas import Citation, ModelRouteDecision
from apps.api.app.services.model_gateway import ModelGateway


def _settings() -> Settings:
    return Settings(
        env="test",
        nvidia_api_key="nvidia-test-key",
        openrouter_api_key="openrouter-test-key",
        api_base_url="http://127.0.0.1:8000",
    )


def _openrouter_route(workflow: str, *, thinking: bool = False) -> ModelRouteDecision:
    return ModelRouteDecision(
        workflow=workflow,
        target_profile="draft_executor",
        provider="openrouter",
        model="google/gemma-4-31b-it",
        reason="Preferred Gemma route.",
        thinking=thinking,
        requires_manual_review_on_failure=False,
    )


def _http_402() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(402, request=request)
    return httpx.HTTPStatusError("402 Payment Required", request=request, response=response)


def _http_503() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    response = httpx.Response(503, request=request)
    return httpx.HTTPStatusError("503 Service Unavailable", request=request, response=response)


@pytest.mark.asyncio
async def test_agent_prompt_falls_back_to_kimi_when_openrouter_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = ModelGateway(_settings())
    seen_providers: list[str] = []

    async def fake_call_text_completion(*, provider: str, **_: object) -> str:
        seen_providers.append(provider)
        if provider == "openrouter":
            raise _http_402()
        return "Summary: Start by loading one account with cited signals.\nActions:\n- Create a product context.\n- Add one account.\nNotes:\n- Fallback path used."

    monkeypatch.setattr(gateway, "_call_text_completion", fake_call_text_completion)

    result = await gateway.answer_agent_prompt(
        route=_openrouter_route("agent-assistant"),
        prompt="How do I get started?",
        context_summary="No account context is open.",
        citations=[],
    )

    assert seen_providers == ["openrouter", "nvidia"]
    assert result["route"].provider == "nvidia"
    assert result["route"].model == "moonshotai/kimi-k2.5"
    assert result["summary"].startswith("Start by loading one account")
    assert any("Fell back to nvidia:moonshotai/kimi-k2.5" in note for note in result["notes"])


@pytest.mark.asyncio
async def test_draft_generation_falls_back_to_kimi_when_openrouter_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = ModelGateway(_settings())

    async def fake_call_openrouter(*_: object, **__: object) -> dict[str, object] | None:
        raise _http_402()

    async def fake_call_nvidia(route: ModelRouteDecision, *_: object, **__: object) -> dict[str, object] | None:
        return {
            "subject": "Security posture signal",
            "body": "Body from Kimi fallback.",
            "route": route,
        }

    monkeypatch.setattr(gateway, "_call_openrouter", fake_call_openrouter)
    monkeypatch.setattr(gateway, "_call_nvidia", fake_call_nvidia)

    result = await gateway.generate_draft(
        route=_openrouter_route("draft-generation"),
        account_name="Test Bank",
        persona="CTO",
        product_name="Security Posture",
        recommended_action="Call today",
        citations=[],
    )

    assert result["route"].provider == "nvidia"
    assert result["route"].model == "moonshotai/kimi-k2.5"
    assert result["subject"] == "Security posture signal"
    assert "fallback" in result["fallback_note"].lower()


def test_assistant_prompt_builder_does_not_request_subject_and_body() -> None:
    gateway = ModelGateway(_settings())
    prompt = gateway._assistant_prompt_with_citations(
        "Summarize this account.",
        [
            Citation(
                label="news",
                source_url="https://example.org/news",
                claim="The bank hired security engineers.",
                excerpt=None,
                published_at=None,
            )
        ],
    )

    assert "Subject:" not in prompt
    assert "Body:" not in prompt
    assert "Grounded evidence:" in prompt


@pytest.mark.asyncio
async def test_nvidia_agent_prompt_tries_kimi_fallback_models(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = ModelGateway(_settings())
    seen_models: list[str] = []
    route = ModelRouteDecision(
        workflow="agent-live-research",
        target_profile="complex_reasoner",
        provider="nvidia",
        model="moonshotai/kimi-k2.5",
        reason="Primary Kimi route.",
        thinking=True,
        requires_manual_review_on_failure=True,
    )

    async def fake_call_text_completion(*, model: str, **_: object) -> str:
        seen_models.append(model)
        if model == "moonshotai/kimi-k2.5":
            raise _http_503()
        return "Summary: Fallback model answered.\nActions:\n- Review citations.\nNotes:\n- Kimi fallback used."

    monkeypatch.setattr(gateway, "_call_text_completion", fake_call_text_completion)

    result = await gateway.answer_agent_prompt(
        route=route,
        prompt="Do deep research.",
        context_summary="Account: Test Bank.",
        citations=[],
    )

    assert seen_models[:2] == ["moonshotai/kimi-k2.5", "moonshotai/kimi-k2-thinking"]
    assert result["route"].provider == "nvidia"
    assert result["route"].model == "moonshotai/kimi-k2-thinking"
    assert result["summary"] == "Fallback model answered."
