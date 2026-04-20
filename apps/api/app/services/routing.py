from apps.api.app.config import Settings
from apps.api.app.schemas import ModelRouteDecision


class ModelRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def decide(
        self,
        workflow: str,
        *,
        evidence_count: int,
        tool_count: int = 0,
        ambiguous: bool = False,
        high_risk: bool = False,
    ) -> ModelRouteDecision:
        kimi_workflows = {"signal-triage", "committee-mapping", "compliance-review"}
        should_use_kimi = (
            workflow in kimi_workflows
            or evidence_count > 6
            or tool_count > 1
            or ambiguous
            or high_risk
        )
        if should_use_kimi:
            return ModelRouteDecision(
                workflow=workflow,
                target_profile="complex_reasoner",
                provider="nvidia",
                model=self.settings.nvidia_model_kimi,
                reason="Complex or high-risk task requires Kimi 2.5 thinking mode.",
                thinking=True,
                requires_manual_review_on_failure=True,
            )
        return ModelRouteDecision(
            workflow=workflow,
            target_profile="draft_executor",
            provider="openrouter",
            model=self.settings.openrouter_model_gemma,
            reason="Grounded drafting task can run on Gemma 4 31B.",
            thinking=False,
            requires_manual_review_on_failure=False,
        )

