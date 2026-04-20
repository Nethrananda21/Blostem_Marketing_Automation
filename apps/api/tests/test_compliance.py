from datetime import UTC, datetime

from apps.api.app.schemas import Citation, ModelRouteDecision
from apps.api.app.services.compliance import ComplianceService


def _route() -> ModelRouteDecision:
    return ModelRouteDecision(
        workflow="compliance-review",
        target_profile="complex_reasoner",
        provider="nvidia",
        model="moonshotai/kimi-k2.5",
        reason="test",
        thinking=True,
        requires_manual_review_on_failure=True,
    )


def test_uncited_numeric_claim_fails() -> None:
    receipt = ComplianceService().review(
        draft_text="A target bank opened 5 new security roles this month.",
        citations=[],
        route=_route(),
    )
    assert receipt.passed is False
    assert receipt.issues


def test_connective_prose_passes_without_citation() -> None:
    receipt = ComplianceService().review(
        draft_text="I am reaching out because this seemed relevant to your team.",
        citations=[],
        route=_route(),
    )
    assert receipt.passed is True
    assert receipt.claim_checks[0].sentence_type == "boilerplate"


def test_supported_security_claim_passes() -> None:
    citation = Citation(
        label="careers",
        source_url="https://news.example.org/security-hiring",
        claim="A target bank posted five InfoSec roles.",
        excerpt="five InfoSec roles",
        published_at=datetime.now(UTC),
    )
    receipt = ComplianceService().review(
        draft_text="A target bank posted five InfoSec roles.",
        citations=[citation],
        route=_route(),
    )
    assert receipt.passed is True
    assert receipt.claim_checks[0].supported is True
