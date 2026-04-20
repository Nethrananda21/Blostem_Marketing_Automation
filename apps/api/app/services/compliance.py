from __future__ import annotations

import re
from datetime import UTC, datetime

from apps.api.app.schemas import Citation, ClaimCheck, ComplianceReceipt, ModelRouteDecision


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_DATE_PATTERN = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|\d{1,2}/\d{1,2}/\d{2,4}|20\d{2})\b",
    re.IGNORECASE,
)
_COMPARATIVE_PATTERN = re.compile(
    r"\b(increase|decrease|faster|slower|more|less|improved|reduced|better|higher|lower|compared|versus|vs)\b",
    re.IGNORECASE,
)
_RISK_PATTERN = re.compile(
    r"\b(soc 2|iso|compliant|compliance|gdpr|regulatory|rbi|security|secure|uptime|customer|client|roi)\b",
    re.IGNORECASE,
)
_GENERIC_PATTERN = re.compile(
    r"\b(thanks for your time|reaching out|wanted to share|thought this might be relevant|happy to discuss)\b",
    re.IGNORECASE,
)


def split_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in _SENTENCE_SPLIT.split(text.strip()) if sentence.strip()]


def _needs_citation(sentence: str) -> bool:
    return bool(
        any(
            (
                any(char.isdigit() for char in sentence),
                _DATE_PATTERN.search(sentence),
                _COMPARATIVE_PATTERN.search(sentence),
                _RISK_PATTERN.search(sentence),
            ),
        ),
    )


def _is_supported(sentence: str, citations: list[Citation]) -> bool:
    normalized_sentence = sentence.lower()
    for citation in citations:
        claim = citation.claim.lower()
        excerpt = (citation.excerpt or "").lower()
        if claim and claim in normalized_sentence:
            return True
        if excerpt and excerpt[:40] and excerpt[:40] in normalized_sentence:
            return True
        claim_tokens = [token for token in claim.split() if len(token) > 3]
        if claim_tokens and sum(token in normalized_sentence for token in claim_tokens) >= max(1, len(claim_tokens) // 2):
            return True
    return False


class ComplianceService:
    def review(
        self,
        *,
        draft_text: str,
        citations: list[Citation],
        route: ModelRouteDecision,
    ) -> ComplianceReceipt:
        issues: list[str] = []
        checks: list[ClaimCheck] = []
        for sentence in split_sentences(draft_text):
            needs_citation = _needs_citation(sentence)
            if not needs_citation and _GENERIC_PATTERN.search(sentence):
                checks.append(
                    ClaimCheck(
                        sentence=sentence,
                        sentence_type="boilerplate",
                        needs_citation=False,
                        supported=True,
                        reason="Standard connective or introductory phrasing.",
                    ),
                )
                continue
            if not needs_citation:
                checks.append(
                    ClaimCheck(
                        sentence=sentence,
                        sentence_type="boilerplate",
                        needs_citation=False,
                        supported=True,
                        reason="No regulated or factual assertion detected.",
                    ),
                )
                continue
            supported = _is_supported(sentence, citations)
            if not supported:
                issues.append(f"Uncited factual claim detected: {sentence}")
            checks.append(
                ClaimCheck(
                    sentence=sentence,
                    sentence_type="factual_claim",
                    needs_citation=True,
                    supported=supported,
                    reason="Contains numeric, dated, comparative, regulatory, customer, or security language.",
                ),
            )
        return ComplianceReceipt(
            passed=not issues,
            issues=issues,
            claim_checks=checks,
            route=route,
            reviewed_at=datetime.now(UTC),
        )
