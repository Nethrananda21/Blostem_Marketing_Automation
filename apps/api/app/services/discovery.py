from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus
from uuid import uuid4

import httpx

from apps.api.app import models
from apps.api.app.config import Settings
from apps.api.app.repositories import Repository
from apps.api.app.schemas import (
    Citation,
    DiscoveryCandidate,
    DiscoveryImportRequest,
    DiscoveryImportResult,
    DiscoverySearchRequest,
    DiscoverySearchResponse,
    DiscoverySignal,
)
from apps.api.app.services.routing import ModelRouter
from apps.api.app.services.serializers import account_summary_from_model
from apps.api.app.services.workflow_engine import WorkflowRunner


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9&.'/-]{2,}")
STOPWORDS = {
    "about",
    "after",
    "agency",
    "against",
    "around",
    "built",
    "company",
    "companies",
    "detail",
    "find",
    "for",
    "from",
    "have",
    "into",
    "need",
    "ones",
    "orgs",
    "product",
    "prompt",
    "provide",
    "recent",
    "relevant",
    "should",
    "that",
    "their",
    "them",
    "they",
    "this",
    "those",
    "want",
    "with",
}
ORG_SUFFIXES = (
    "Bank",
    "Finance",
    "Finserv",
    "Fintech",
    "Payments",
    "Pay",
    "Insurance",
    "Capital",
    "Securities",
    "Credit",
    "Authority",
    "Agency",
    "Corporation",
    "Exchange",
)
MULTIWORD_SUFFIXES = (
    "Small Finance Bank",
    "Cooperative Bank",
    "Co-operative Bank",
)
PUBLISHER_BLOCKLIST = {
    "Google News",
    "Reuters",
    "Business Standard",
    "Moneycontrol",
    "The Economic Times",
    "Mint",
    "The Hindu",
    "Times of India",
}
GENERIC_ORG_PHRASES = {
    "biggest bank",
    "largest bank",
    "leading bank",
    "top bank",
    "public sector bank",
    "private sector bank",
}
GENERIC_ORG_PREFIXES = (
    "in ",
    "rs ",
    "lakh ",
    "penalty ",
    "penalises ",
    "imposes ",
    "fraud ",
    "case ",
    "files ",
    "filed ",
    "charges ",
    "chargesheet ",
    "appoints ",
    "rbi ",
    "ed ",
)
GENERIC_ORG_TOKENS = {
    "crore",
    "lakh",
    "penalty",
    "fraud",
    "recruitment",
    "notification",
    "fintech",
    "digital",
    "payments",
    "laws",
    "rules",
    "growth",
    "legal",
    "service",
}
SIGNAL_WEIGHTS = {
    "security_event": 34.0,
    "regulatory_event": 32.0,
    "digital_initiative": 22.0,
    "leadership_change": 18.0,
    "market_update": 12.0,
}


def strip_html(value: str) -> str:
    return SPACE_RE.sub(" ", TAG_RE.sub(" ", html.unescape(value or ""))).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def canonicalize_org_name(value: str) -> str:
    normalized = SPACE_RE.sub(" ", value.replace("&amp;", "&")).strip(" .,-")
    normalized = re.sub(r"\s+-\s+.*$", "", normalized)
    normalized = re.sub(r"\b(Ltd|Limited|Pvt|Private|Inc|Corp|Corporation)\.?$", "", normalized, flags=re.I)
    normalized = SPACE_RE.sub(" ", normalized).strip(" .,-")
    return normalized.lower()


def parse_google_news_rss(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = strip_html(item.findtext("description") or "")
        source_text = (item.findtext("source") or "").strip()
        published_raw = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        published_at = None
        if published_raw:
            published_at = parsedate_to_datetime(published_raw).astimezone(UTC)
        items.append(
            {
                "title": title,
                "link": link,
                "description": description,
                "source": source_text or "Google News",
                "published_at": published_at,
            },
        )
    return items


def classify_signal(text: str) -> str:
    normalized = text.lower()
    if any(token in normalized for token in ["breach", "cyber", "phishing", "security", "attack", "ciso", "fraud"]):
        return "security_event"
    if any(token in normalized for token in ["rbi", "fine", "penalty", "regulatory", "compliance", "audit", "sebi"]):
        return "regulatory_event"
    if any(token in normalized for token in ["hire", "hiring", "appoint", "joins", "leadership", "chief executive", "cfo"]):
        return "leadership_change"
    if any(token in normalized for token in ["partnership", "partner", "launch", "digital", "onboarding", "api", "platform"]):
        return "digital_initiative"
    return "market_update"


def infer_segment(name: str, text_blob: str) -> str:
    normalized = f"{name} {text_blob}".lower()
    if "small finance bank" in normalized:
        return "Small Finance Bank"
    if "bank" in normalized:
        return "Bank"
    if any(token in normalized for token in ["fintech", "payments", "upi", "wallet"]):
        return "Fintech"
    if any(token in normalized for token in ["nbfc", "finance", "lending", "loan"]):
        return "NBFC"
    if any(token in normalized for token in ["insurance", "insurer"]):
        return "Insurance"
    if any(token in normalized for token in ["authority", "agency", "government"]):
        return "Agency"
    return "BFSI"


def extract_keywords(prompt: str) -> list[str]:
    keywords: list[str] = []
    for match in WORD_RE.findall(prompt.lower()):
        if match in STOPWORDS or match in keywords:
            continue
        keywords.append(match)
    return keywords[:8]


def extract_org_names(title: str, description: str, source: str) -> list[str]:
    candidates: set[str] = set()
    title_head = re.split(r"\s[-|]\s", title, maxsplit=1)[0].strip()
    search_spaces = [title_head, title, description]

    for text in search_spaces:
        cleaned = re.sub(r"[,:;()]", " ", text)
        tokens = cleaned.split()
        for index in range(len(tokens)):
            for width in range(1, 7):
                phrase = " ".join(tokens[index : index + width]).strip(" -")
                if not phrase:
                    continue
                if any(phrase.endswith(suffix) for suffix in ORG_SUFFIXES + MULTIWORD_SUFFIXES):
                    if _looks_like_org_phrase(phrase):
                        candidates.add(phrase)

    if not candidates and _looks_like_org_phrase(title_head):
        words = title_head.split()
        if 1 <= len(words) <= 5:
            candidates.add(title_head)

    filtered = []
    for candidate in candidates:
        compact = SPACE_RE.sub(" ", candidate).strip(" -")
        if not compact or compact in PUBLISHER_BLOCKLIST:
            continue
        if compact.lower() == source.lower():
            continue
        if len(compact) < 3:
            continue
        if _is_generic_org_phrase(compact):
            continue
        filtered.append(compact)
    filtered.sort(key=len, reverse=True)
    pruned: list[str] = []
    for candidate in filtered:
        if any(existing.endswith(candidate) for existing in pruned):
            continue
        pruned.append(candidate)
    return pruned


def _looks_like_org_phrase(phrase: str) -> bool:
    words = [word.strip(" .") for word in phrase.split() if word.strip(" .")]
    if not words:
        return False
    first_word = words[0]
    if not (first_word.isupper() or first_word[:1].isupper()):
        return False
    valid_words = 0
    for word in words:
        if word.isupper() or word[:1].isupper() or any(char.isdigit() for char in word):
            valid_words += 1
    return valid_words >= max(1, len(words) - 1)


def _is_generic_org_phrase(phrase: str) -> bool:
    normalized = phrase.lower().replace("’", "'")
    if any(token in normalized for token in GENERIC_ORG_PHRASES):
        return True
    generic_prefixes = ("india's ", "indias ", "indian ", "largest ", "leading ", "top ", *GENERIC_ORG_PREFIXES)
    if normalized.startswith(generic_prefixes):
        return True
    if normalized.startswith("bank ") or " bank bank " in normalized or normalized.count(" bank") >= 2:
        return True
    tokens = {token for token in re.findall(r"[a-z0-9']+", normalized) if token}
    if tokens and tokens.issubset(GENERIC_ORG_TOKENS | {"bank", "finance", "insurance", "agency"}):
        return True
    return bool(tokens & GENERIC_ORG_TOKENS and len(tokens & GENERIC_ORG_TOKENS) >= max(1, len(tokens) - 1))


class MarketDiscoveryService:
    def __init__(
        self,
        *,
        repository: Repository,
        runner: WorkflowRunner,
        router: ModelRouter,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.runner = runner
        self.router = router
        self.settings = settings

    async def search(self, request: DiscoverySearchRequest) -> DiscoverySearchResponse:
        product_contexts = list(await self.repository.list_product_contexts())
        if not product_contexts:
            raise ValueError("Create a product context before running external discovery.")
        context = self._select_product_context(request, product_contexts)
        queries = self._build_queries(context, request.prompt)
        route = self.router.decide(
            "signal-triage",
            evidence_count=max(len(context.trigger_patterns), 1),
            tool_count=min(3, len(queries)),
            ambiguous=True,
            high_risk=True,
        )

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 BlostemDiscovery/1.0"},
        ) as client:
            batches = await self._fetch_batches(client, queries)
            candidates = await self._build_candidates(
                client=client,
                context=context,
                prompt=request.prompt,
                batches=batches,
                route=route,
                limit=max(1, min(request.limit, 12)),
            )

        return DiscoverySearchResponse(
            prompt=request.prompt,
            product_context_key=context.key,
            product_context_name=context.name,
            queries=queries,
            candidates=candidates,
            route=route,
            notes=[
                "Discovery currently searches public web/news signals through query-driven RSS ingestion, then groups and ranks net-new organizations.",
                "Candidates are not added to the interested queue until you explicitly import them.",
            ],
        )

    async def run_discovery_job(self, job: models.DiscoveryJob) -> int:
        response = await self.search(
            DiscoverySearchRequest(
                prompt=job.prompt,
                product_context_key=job.product_context_key,
                limit=job.limit,
            ),
        )
        stored_count = 0
        for candidate in response.candidates:
            source_urls = {citation.source_url for citation in candidate.citations}
            confidence_score = self._confidence_score(candidate, len(source_urls))
            record = await self.repository.upsert_discovery_candidate_record(
                job_id=job.id,
                canonical_name=canonicalize_org_name(candidate.name),
                payload={
                    "name": candidate.name,
                    "segment": candidate.segment,
                    "territory": candidate.territory,
                    "summary": candidate.summary,
                    "product_context_key": candidate.product_context_key,
                    "interest_score": candidate.interest_score,
                    "fit_score": candidate.fit_score,
                    "freshness_score": candidate.freshness_score,
                    "confidence_score": confidence_score,
                    "source_count": len(source_urls),
                    "top_signal": candidate.top_signal,
                    "reason": candidate.reason,
                    "reasons": candidate.reasons,
                    "citations": [citation.model_dump(mode="json") for citation in candidate.citations],
                    "signals": [signal.model_dump(mode="json") for signal in candidate.signals],
                    "source_prompt": response.prompt,
                    "source_queries": response.queries,
                    "status": "new",
                },
            )
            stored_count += 1
            if job.auto_import_threshold and candidate.interest_score >= job.auto_import_threshold:
                await self.import_candidate(
                    DiscoveryImportRequest(
                        candidate=candidate,
                        candidate_record_id=record.id,
                        refresh_workflow=True,
                    ),
                )

        now = datetime.now(UTC)
        await self.repository.update_discovery_job(
            job,
            last_run_at=now,
            next_run_at=now + timedelta(minutes=job.cadence_minutes),
            last_result_count=stored_count,
        )
        return stored_count

    async def run_due_jobs(self) -> dict[str, int]:
        due_jobs = list(await self.repository.list_due_discovery_jobs(datetime.now(UTC)))
        results: dict[str, int] = {}
        for job in due_jobs:
            results[job.id] = await self.run_discovery_job(job)
        return results

    async def import_candidate(self, request: DiscoveryImportRequest) -> DiscoveryImportResult:
        candidate = request.candidate
        account = await self.repository.get_account_by_name(candidate.name)
        existing_account = account is not None

        if account is None:
            account = await self.repository.create_account(
                {
                    "name": candidate.name,
                    "segment": candidate.segment,
                    "territory": candidate.territory,
                    "pipeline_stage": "Research",
                    "summary": candidate.summary,
                    "owner_role": "rep",
                    "metadata": {
                        "discovery_origin": "external_public_search",
                        "product_context_key": candidate.product_context_key,
                        "interest_score": f"{candidate.interest_score:.0f}",
                    },
                },
            )

        existing_signals = {(signal.title, signal.source_url) for signal in await self.repository.list_signals(account.id)}
        imported_signal_count = 0
        for signal in candidate.signals:
            dedupe_key = (signal.title, signal.source_url)
            if dedupe_key in existing_signals:
                continue
            await self.repository.create_signal(
                {
                    "account_id": account.id,
                    "topic_family": signal.topic_family,
                    "signal_type": signal.signal_type,
                    "source_type": signal.source_type,
                    "title": signal.title,
                    "summary": signal.summary,
                    "source_url": signal.source_url,
                    "detected_at": signal.detected_at,
                    "facts": signal.facts,
                    "citations": [citation.model_dump(mode="json") for citation in signal.citations],
                    "raw_payload": signal.raw_payload,
                },
            )
            imported_signal_count += 1

        await self.repository.log_activity(
            account.id,
            "discovery",
            "Imported from external discovery",
            f"Added {candidate.name} from the public discovery pipeline with {imported_signal_count} new signals.",
        )

        if request.candidate_record_id:
            record = await self.repository.get_discovery_candidate_record(request.candidate_record_id)
            if record is not None:
                await self.repository.update_discovery_candidate_record(record, status="imported")

        opportunity_id: str | None = None
        draft_id: str | None = None
        if request.refresh_workflow:
            opportunity, draft = await self.runner.refresh_opportunity(account.id)
            opportunity_id = opportunity.id
            draft_id = draft.id

        refreshed_account = await self.repository.get_account(account.id)
        if refreshed_account is None:
            raise RuntimeError("Imported account could not be reloaded.")

        return DiscoveryImportResult(
            account=account_summary_from_model(refreshed_account),
            existing_account=existing_account,
            imported_signal_count=imported_signal_count,
            opportunity_id=opportunity_id,
            draft_id=draft_id,
        )

    def _select_product_context(
        self,
        request: DiscoverySearchRequest,
        contexts: list[models.ProductContext],
    ) -> models.ProductContext:
        if request.product_context_key:
            for context in contexts:
                if context.key == request.product_context_key:
                    return context
            raise ValueError("Selected product context was not found.")

        if len(contexts) == 1:
            return contexts[0]

        prompt_terms = extract_keywords(request.prompt)
        best_context = contexts[0]
        best_score = -1
        for context in contexts:
            blob = " ".join(
                [context.name, context.overview, *context.icp_segments, *context.trigger_patterns],
            ).lower()
            score = sum(1 for term in prompt_terms if term in blob)
            if score > best_score:
                best_context = context
                best_score = score
        return best_context

    def _build_queries(self, context: models.ProductContext, prompt: str) -> list[str]:
        keywords = extract_keywords(prompt)
        geography = "India"
        if any(token in prompt.lower() for token in ["global", "worldwide", "international"]):
            geography = ""

        sector_terms = self._sector_terms(context)
        trigger_terms = self._trigger_terms(context, keywords)

        queries: list[str] = []
        if prompt.strip():
            queries.append(f"{prompt.strip()} when:30d")
        for sector in sector_terms[:3]:
            for trigger in trigger_terms[:3]:
                parts = [geography, sector, trigger, "when:30d"]
                query = " ".join(part for part in parts if part)
                if query not in queries:
                    queries.append(query)
        return queries[:6]

    def _sector_terms(self, context: models.ProductContext) -> list[str]:
        terms: list[str] = []
        for segment in context.icp_segments:
            normalized = segment.lower()
            if "bank" in normalized:
                terms.extend(["bank", "private bank"])
            elif "fintech" in normalized:
                terms.extend(["fintech", "payments"])
            elif "nbfc" in normalized or "finance" in normalized:
                terms.extend(["nbfc", "finance company"])
            elif "insurance" in normalized:
                terms.extend(["insurance", "insurer"])
            else:
                terms.append(segment)
        if not terms:
            terms = ["bank", "fintech"]
        return list(dict.fromkeys(terms))

    def _trigger_terms(self, context: models.ProductContext, prompt_keywords: list[str]) -> list[str]:
        matched = [pattern for pattern in context.trigger_patterns if any(word in pattern.lower() for word in prompt_keywords)]
        triggers = matched or context.trigger_patterns[:4]
        if not triggers:
            triggers = ["security", "compliance", "digital transformation"]
        return list(dict.fromkeys(triggers))

    async def _fetch_batches(self, client: httpx.AsyncClient, queries: list[str]) -> list[dict[str, Any]]:
        async def _fetch_one(query: str) -> list[dict[str, Any]]:
            url = f"{GOOGLE_NEWS_RSS}?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"
            try:
                response = await client.get(url)
                response.raise_for_status()
                items = parse_google_news_rss(response.text)
                return [{**item, "query": query} for item in items]
            except (httpx.HTTPError, ET.ParseError):
                return []

        import asyncio as _asyncio
        results = await _asyncio.gather(*[_fetch_one(q) for q in queries], return_exceptions=True)
        seen_titles: set[str] = set()
        batches: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, BaseException):
                continue
            for item in result:
                title_key = item["title"].lower()
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                batches.append(item)
        return batches

    async def _build_candidates(
        self,
        *,
        client: httpx.AsyncClient,
        context: models.ProductContext,
        prompt: str,
        batches: list[dict[str, Any]],
        route,
        limit: int,
    ) -> list[DiscoveryCandidate]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        display_names: dict[str, str] = {}
        for item in batches:
            org_names = extract_org_names(item["title"], item["description"], item["source"])
            for org_name in org_names[:2]:
                if self._is_disqualified(org_name, item, context):
                    continue
                canonical_name = canonicalize_org_name(org_name)
                if not canonical_name or len(canonical_name) < 3:
                    continue
                grouped.setdefault(canonical_name, []).append({**item, "matched_org": org_name})
                current_display = display_names.get(canonical_name, "")
                if len(org_name) > len(current_display):
                    display_names[canonical_name] = org_name

        candidates: list[DiscoveryCandidate] = []
        for canonical_name, items in grouped.items():
            name = display_names.get(canonical_name, canonical_name.title())
            signals = await self._candidate_signals(client, name, items)
            if not signals:
                continue
            segment = infer_segment(name, " ".join(f"{signal.title} {signal.summary}" for signal in signals))
            fit_score = self._fit_score(segment, context, prompt, signals)
            freshness_score = self._freshness_score(signals)
            severity_score = self._severity_score(context, prompt, signals)
            interest_score = min(99.0, round(severity_score * 0.55 + fit_score * 0.3 + freshness_score * 0.15, 1))
            sorted_signals = sorted(signals, key=lambda signal: signal.detected_at, reverse=True)
            top_signal = sorted_signals[0].title
            reasons = self._reasons_for_candidate(name, segment, context, prompt, sorted_signals, fit_score, freshness_score)
            citations = [citation for signal in sorted_signals[:3] for citation in signal.citations[:1]]
            candidates.append(
                DiscoveryCandidate(
                    id=f"disc_{uuid4().hex[:12]}",
                    name=name,
                    segment=segment,
                    territory="India",
                    summary=(
                        f"{name} surfaced in {len(sorted_signals)} recent public signals that overlap with "
                        f"{context.name.lower()} trigger patterns."
                    ),
                    product_context_key=context.key,
                    interest_score=interest_score,
                    fit_score=fit_score,
                    freshness_score=freshness_score,
                    top_signal=top_signal,
                    reason=reasons[0],
                    reasons=reasons,
                    citations=citations,
                    signals=sorted_signals,
                    route=route,
                ),
            )

        candidates.sort(
            key=lambda item: (item.interest_score, item.fit_score, item.freshness_score, len(item.signals)),
            reverse=True,
        )
        return candidates[:limit]

    def _confidence_score(self, candidate: DiscoveryCandidate, source_count: int) -> float:
        score = 35.0
        score += min(25.0, source_count * 8.0)
        score += min(20.0, len(candidate.signals) * 5.0)
        score += max(0.0, candidate.interest_score - 60.0) * 0.25
        if candidate.segment.lower() in {"bank", "private bank", "small finance bank", "fintech", "nbfc"}:
            score += 8.0
        return min(99.0, round(score, 1))

    async def _candidate_signals(
        self,
        client: httpx.AsyncClient,
        name: str,
        items: list[dict[str, Any]],
    ) -> list[DiscoverySignal]:
        import asyncio as _asyncio

        async def _resolve_item(item: dict[str, Any]) -> DiscoverySignal:
            source_url = await self._resolve_article_url(client, item["link"])
            summary = (item["description"] or item["title"])[:320]
            detected_at = item["published_at"] or datetime.now(UTC)
            citation = Citation(
                label=item["source"],
                source_url=source_url,
                claim=item["title"],
                excerpt=summary,
                published_at=detected_at,
            )
            return DiscoverySignal(
                signal_type=classify_signal(f"{item['title']} {summary}"),
                source_type="google_news_rss",
                title=item["title"],
                summary=summary,
                source_url=source_url,
                detected_at=detected_at,
                facts={
                    "publisher": item["source"],
                    "query": item["query"],
                    "matched_org": name,
                },
                citations=[citation],
                raw_payload={
                    "original_link": item["link"],
                    "query": item["query"],
                    "publisher": item["source"],
                },
            )

        resolved = await _asyncio.gather(
            *[_resolve_item(item) for item in items[:5]], return_exceptions=True
        )
        deduped: dict[tuple[str, str], DiscoverySignal] = {}
        for result in resolved:
            if isinstance(result, BaseException):
                continue
            deduped[(result.title, result.source_url)] = result
        return list(deduped.values())

    async def _resolve_article_url(self, client: httpx.AsyncClient, url: str) -> str:
        if len(url) <= 500 and "news.google.com" not in url:
            return url
        try:
            response = await client.get(url)
            final_url = str(response.url)
            if final_url and len(final_url) <= 500:
                return final_url
        except httpx.HTTPError:
            return url[:500]
        return url[:500]

    def _is_disqualified(self, name: str, item: dict[str, Any], context: models.ProductContext) -> bool:
        blob = f"{name} {item['title']} {item['description']}".lower()
        return any(disqualifier.lower() in blob for disqualifier in context.disqualifiers)

    def _fit_score(
        self,
        segment: str,
        context: models.ProductContext,
        prompt: str,
        signals: list[DiscoverySignal],
    ) -> float:
        fit = 70.0
        if any(segment.lower() in icp.lower() or icp.lower() in segment.lower() for icp in context.icp_segments):
            fit += 18.0
        prompt_blob = prompt.lower()
        if any(term.lower() in prompt_blob for term in [segment, context.name, *context.icp_segments]):
            fit += 6.0
        trigger_hits = sum(
            1
            for signal in signals
            for pattern in context.trigger_patterns[:6]
            if pattern.lower() in f"{signal.title} {signal.summary}".lower()
        )
        fit += min(5.0, trigger_hits)
        return min(98.0, round(fit, 1))

    def _freshness_score(self, signals: list[DiscoverySignal]) -> float:
        latest = max(signal.detected_at for signal in signals)
        age_days = max((datetime.now(UTC) - latest).days, 0)
        return max(42.0, round(96.0 - min(age_days * 6.5, 54.0), 1))

    def _severity_score(
        self,
        context: models.ProductContext,
        prompt: str,
        signals: list[DiscoverySignal],
    ) -> float:
        total = 30.0
        prompt_keywords = extract_keywords(prompt)
        for signal in signals:
            total += SIGNAL_WEIGHTS.get(signal.signal_type, 10.0)
            text_blob = f"{signal.title} {signal.summary}".lower()
            total += sum(3.0 for pattern in context.trigger_patterns if pattern.lower() in text_blob)
            total += sum(1.5 for keyword in prompt_keywords if keyword in text_blob)
        return min(98.0, round(total / max(len(signals), 1), 1))

    def _reasons_for_candidate(
        self,
        name: str,
        segment: str,
        context: models.ProductContext,
        prompt: str,
        signals: list[DiscoverySignal],
        fit_score: float,
        freshness_score: float,
    ) -> list[str]:
        latest = signals[0]
        matched_patterns = [
            pattern
            for pattern in context.trigger_patterns
            if pattern.lower() in f"{latest.title} {latest.summary}".lower()
        ]
        reasons = [
            f"{name} aligns to the {segment} segment with a fit score of {fit_score:.0f}.",
            f"Latest public trigger: {latest.title}",
            f"Freshness is {freshness_score:.0f} based on recent public coverage.",
        ]
        if matched_patterns:
            reasons.insert(1, f"Matched trigger patterns: {', '.join(matched_patterns[:3])}.")
        if prompt.strip():
            reasons.append(f"Discovery prompt used: {prompt.strip()}")
        return reasons
