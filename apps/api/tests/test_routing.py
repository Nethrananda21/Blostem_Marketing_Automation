from apps.api.app.config import Settings
from apps.api.app.services.routing import ModelRouter


def test_complex_tasks_route_to_kimi() -> None:
    router = ModelRouter(Settings())
    decision = router.decide("signal-triage", evidence_count=8, tool_count=2, high_risk=True)
    assert decision.provider == "nvidia"
    assert decision.model == "moonshotai/kimi-k2.5"
    assert decision.thinking is True
    assert decision.requires_manual_review_on_failure is True


def test_grounded_draft_routes_to_gemma() -> None:
    router = ModelRouter(Settings())
    decision = router.decide("draft-generation", evidence_count=3, tool_count=1)
    assert decision.provider == "openrouter"
    assert decision.model == "google/gemma-4-31b-it"
    assert decision.target_profile == "draft_executor"

