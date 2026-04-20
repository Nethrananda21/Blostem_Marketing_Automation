from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from apps.api.app.config import Settings
from apps.api.app.schemas import Citation, ModelRouteDecision


PROVIDER_HEALTH: dict[str, dict[str, str | None]] = {
    "nvidia": {"status": "unknown", "detail": None, "checked_at": None},
    "openrouter": {"status": "unknown", "detail": None, "checked_at": None},
}


class ModelGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(180.0, connect=30.0)

    async def generate_draft(
        self,
        *,
        route: ModelRouteDecision,
        account_name: str,
        persona: str,
        product_name: str,
        recommended_action: str,
        citations: list[Citation],
    ) -> dict[str, Any]:
        prompt = (
            f"Write a concise enterprise outreach email for the {persona} at {account_name}. "
            f"Focus on {product_name}. Recommended action: {recommended_action}. "
            "Use only grounded claims from the supplied citations and avoid unsupported ROI, compliance, or security assertions."
        )
        try:
            if route.provider == "openrouter" and self.settings.openrouter_api_key:
                response = await self._call_openrouter(route, prompt, citations)
                if response:
                    return response
            if route.provider == "nvidia" and self.settings.nvidia_api_key:
                response = await self._call_nvidia_with_model_fallbacks(route, prompt, citations)
                if response:
                    return response
        except (httpx.HTTPError, RuntimeError) as exc:
            try:
                fallback = await self._fallback_to_kimi_for_draft(route=route, prompt=prompt, citations=citations, exc=exc)
            except (httpx.HTTPError, RuntimeError) as fallback_exc:
                raise RuntimeError(
                    f"Live draft generation failed for both {route.provider}:{route.model} and NVIDIA Kimi fallback. "
                    "Check provider reachability, credentials, and network latency.",
                ) from fallback_exc
            if fallback is not None:
                return fallback
            raise RuntimeError(
                f"Live draft generation failed while calling {route.provider}:{route.model}. "
                "Check provider reachability, credentials, and network access.",
            ) from exc
        raise RuntimeError(
            f"Live draft generation is unavailable for route {route.provider}:{route.model}. "
            "Check provider keys and upstream API availability.",
        )

    async def answer_agent_prompt(
        self,
        *,
        route: ModelRouteDecision,
        prompt: str,
        context_summary: str,
        citations: list[Citation],
    ) -> dict[str, Any]:
        instruction = (
            "You are an internal sales agent for a BFSI-safe outbound system. "
            "Use the account context and citations only. "
            "If context is missing, say that clearly and give only setup steps that are explicitly supported by the running Blostem workspace. "
            "Do not invent authentication, approval, or compliance workflows that are not present in the supplied context. "
            "Return exact sections:\n"
            "Summary: <one short paragraph>\n"
            "Actions:\n- <action>\n- <action>\n"
            "Notes:\n- <note>\n- <note>"
        )
        full_prompt = f"Operator request: {prompt}\n\nContext:\n{context_summary}"
        try:
            if route.provider == "nvidia" and self.settings.nvidia_api_key:
                content, actual_route = await self._call_nvidia_text_completion_with_model_fallbacks(
                    route=route,
                    system_prompt=instruction,
                    user_prompt=self._assistant_prompt_with_citations(full_prompt, citations),
                )
                if content:
                    parsed = self._parse_agent_response(content)
                    parsed["used_live_model"] = True
                    parsed["route"] = actual_route
                    return parsed
            if route.provider == "openrouter" and self.settings.openrouter_api_key:
                content = await self._call_text_completion(
                    base_url=self.settings.openrouter_base_url,
                    api_key=self.settings.openrouter_api_key,
                    model=route.model,
                    system_prompt=instruction,
                    user_prompt=self._assistant_prompt_with_citations(full_prompt, citations),
                    thinking=False,
                    provider="openrouter",
                )
                if content:
                    parsed = self._parse_agent_response(content)
                    parsed["used_live_model"] = True
                    parsed["route"] = route
                    return parsed
        except (httpx.HTTPError, RuntimeError) as exc:
            try:
                fallback = await self._fallback_to_kimi_for_agent(
                    route=route,
                    instruction=instruction,
                    full_prompt=full_prompt,
                    citations=citations,
                    exc=exc,
                )
            except (httpx.HTTPError, RuntimeError) as fallback_exc:
                raise RuntimeError(
                    f"Live agent prompting failed for both {route.provider}:{route.model} and NVIDIA Kimi fallback. "
                    "Check provider reachability, credentials, and network latency.",
                ) from fallback_exc
            if fallback is not None:
                return fallback
            raise RuntimeError(
                f"Live agent prompting failed while calling {route.provider}:{route.model}. "
                "Check provider reachability, credentials, and network access.",
            ) from exc
        raise RuntimeError(
            f"Live agent prompting is unavailable for route {route.provider}:{route.model}. "
            "Check provider keys and upstream API availability.",
        )

    async def _call_openrouter(
        self,
        route: ModelRouteDecision,
        prompt: str,
        citations: list[Citation],
    ) -> dict[str, Any] | None:
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.app_public_origin,
            "X-Title": "Blostem",
        }
        body = {
            "model": route.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You draft concise BFSI-safe outreach. Never invent facts. Never mention hidden reasoning.",
                },
                {
                    "role": "user",
                    "content": self._draft_prompt_with_citations(prompt, citations),
                },
            ],
            "temperature": 0.3,
        }
        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            response = await client.post(
                f"{self.settings.openrouter_base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            if response.is_success:
                try:
                    content = self._extract_chat_content(response.json())
                except RuntimeError as exc:
                    self._record_provider_health("openrouter", "error", str(exc))
                    raise
                self._record_provider_health("openrouter", "available", f"{response.status_code} OK")
                payload = self._extract_subject_body(content)
                payload["route"] = route
                return payload
            self._record_provider_health("openrouter", "error", self._summarize_http_error(response))
            response.raise_for_status()
        return None

    async def _call_nvidia(
        self,
        route: ModelRouteDecision,
        prompt: str,
        citations: list[Citation],
    ) -> dict[str, Any] | None:
        headers = {
            "Authorization": f"Bearer {self.settings.nvidia_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body: dict[str, Any] = {
            "model": route.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You reason over grounded BFSI sales evidence. Return concise JSON-ready answers only.",
                },
                {
                    "role": "user",
                    "content": self._draft_prompt_with_citations(prompt, citations),
                },
            ],
            "temperature": 0.6 if route.thinking else 0.3,
            "max_tokens": 900,
        }
        if not route.thinking:
            body["thinking"] = {"type": "disabled"}
        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            response = await client.post(
                f"{self.settings.nvidia_base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            if response.is_success:
                try:
                    content = self._extract_chat_content(response.json())
                except RuntimeError as exc:
                    self._record_provider_health("nvidia", "error", str(exc))
                    raise
                self._record_provider_health("nvidia", "available", f"{response.status_code} OK")
                payload = self._extract_subject_body(content)
                payload["route"] = route
                return payload
            self._record_provider_health("nvidia", "error", self._summarize_http_error(response))
            response.raise_for_status()
        return None

    async def _call_text_completion(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        thinking: bool,
        provider: str,
    ) -> str | None:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if provider == "nvidia":
            headers["Accept"] = "application/json"
        if provider == "openrouter":
            headers["HTTP-Referer"] = self.settings.app_public_origin
            headers["X-Title"] = "Blostem"
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 900,
        }
        if provider == "nvidia" and not thinking:
            body["thinking"] = {"type": "disabled"}
        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            response = await client.post(f"{base_url}/chat/completions", headers=headers, json=body)
            if response.is_success:
                try:
                    content = self._extract_chat_content(response.json())
                except RuntimeError as exc:
                    self._record_provider_health(provider, "error", str(exc))
                    raise
                self._record_provider_health(provider, "available", f"{response.status_code} OK")
                return content
            self._record_provider_health(provider, "error", self._summarize_http_error(response))
            response.raise_for_status()
        return None

    def provider_health_snapshot(self) -> dict[str, dict[str, str | None]]:
        return {name: values.copy() for name, values in PROVIDER_HEALTH.items()}

    async def _fallback_to_kimi_for_agent(
        self,
        *,
        route: ModelRouteDecision,
        instruction: str,
        full_prompt: str,
        citations: list[Citation],
        exc: Exception,
    ) -> dict[str, Any] | None:
        if route.provider != "openrouter" or not self.settings.nvidia_api_key:
            return None
        fallback_route = self._fallback_route(route, self._summarize_exception(exc))
        content, actual_route = await self._call_nvidia_text_completion_with_model_fallbacks(
            route=fallback_route,
            system_prompt=instruction,
            user_prompt=self._assistant_prompt_with_citations(full_prompt, citations),
        )
        if not content:
            return None
        parsed = self._parse_agent_response(content)
        parsed["used_live_model"] = True
        parsed["route"] = actual_route
        parsed["notes"] = [
            f"Fell back to {actual_route.provider}:{actual_route.model} because {route.provider}:{route.model} was unavailable."
        ] + parsed["notes"]
        return parsed

    async def _fallback_to_kimi_for_draft(
        self,
        *,
        route: ModelRouteDecision,
        prompt: str,
        citations: list[Citation],
        exc: Exception,
    ) -> dict[str, Any] | None:
        if route.provider != "openrouter" or not self.settings.nvidia_api_key:
            return None
        fallback_route = self._fallback_route(route, self._summarize_exception(exc))
        payload = await self._call_nvidia_with_model_fallbacks(fallback_route, prompt, citations)
        if payload is not None:
            payload["fallback_note"] = (
                f"Fallback used {payload['route'].provider}:{payload['route'].model} because {route.provider}:{route.model} was unavailable."
            )
        return payload

    async def _call_nvidia_text_completion_with_model_fallbacks(
        self,
        *,
        route: ModelRouteDecision,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str | None, ModelRouteDecision]:
        last_error: Exception | None = None
        for model in self._nvidia_model_candidates(route.model):
            candidate_route = self._nvidia_candidate_route(route, model, last_error)
            try:
                content = await self._call_text_completion(
                    base_url=self.settings.nvidia_base_url,
                    api_key=self.settings.nvidia_api_key or "",
                    model=candidate_route.model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    thinking=candidate_route.thinking,
                    provider="nvidia",
                )
            except (httpx.HTTPError, RuntimeError) as exc:
                last_error = exc
                continue
            if content:
                return content, candidate_route
        if last_error:
            raise RuntimeError(
                f"All configured NVIDIA Kimi models failed. Last error: {self._summarize_exception(last_error)}"
            ) from last_error
        return None, route

    async def _call_nvidia_with_model_fallbacks(
        self,
        route: ModelRouteDecision,
        prompt: str,
        citations: list[Citation],
    ) -> dict[str, Any] | None:
        last_error: Exception | None = None
        for model in self._nvidia_model_candidates(route.model):
            candidate_route = self._nvidia_candidate_route(route, model, last_error)
            try:
                payload = await self._call_nvidia(candidate_route, prompt, citations)
            except (httpx.HTTPError, RuntimeError) as exc:
                last_error = exc
                continue
            if payload is not None:
                return payload
        if last_error:
            raise RuntimeError(
                f"All configured NVIDIA Kimi models failed. Last error: {self._summarize_exception(last_error)}"
            ) from last_error
        return None

    def _nvidia_model_candidates(self, primary_model: str) -> list[str]:
        configured_models = [
            model.strip()
            for model in self.settings.nvidia_kimi_fallback_models.split(",")
            if model.strip()
        ]
        return list(dict.fromkeys([primary_model, *configured_models]))

    def _nvidia_candidate_route(
        self,
        route: ModelRouteDecision,
        model: str,
        previous_error: Exception | None,
    ) -> ModelRouteDecision:
        if model == route.model:
            return route
        previous = self._summarize_exception(previous_error) if previous_error else "primary model unavailable"
        return ModelRouteDecision(
            workflow=route.workflow,
            target_profile=route.target_profile,
            provider="nvidia",
            model=model,
            reason=f"NVIDIA Kimi fallback model used because {route.model} failed or was unavailable ({previous}).",
            thinking=route.thinking,
            requires_manual_review_on_failure=route.requires_manual_review_on_failure,
        )

    def _fallback_route(self, route: ModelRouteDecision, cause: str) -> ModelRouteDecision:
        return ModelRouteDecision(
            workflow=route.workflow,
            target_profile=route.target_profile,
            provider="nvidia",
            model=self.settings.nvidia_model_kimi,
            reason=f"Fallback to Kimi because {route.provider}:{route.model} is unavailable ({cause}).",
            thinking=route.workflow in {"signal-triage", "committee-mapping", "compliance-review"} or route.thinking,
            requires_manual_review_on_failure=True,
        )

    def _draft_prompt_with_citations(self, prompt: str, citations: list[Citation]) -> str:
        facts = "\n".join(f"- {citation.claim} ({citation.source_url})" for citation in citations[:6])
        return f"{prompt}\n\nGrounded evidence:\n{facts}\n\nReturn:\nSubject: ...\nBody: ..."

    def _assistant_prompt_with_citations(self, prompt: str, citations: list[Citation]) -> str:
        facts = "\n".join(f"- {citation.claim} ({citation.source_url})" for citation in citations[:6]) or "- No citations attached."
        return f"{prompt}\n\nGrounded evidence:\n{facts}"

    def _extract_chat_content(self, payload: dict[str, Any]) -> str:
        message = payload["choices"][0]["message"]
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        raise RuntimeError("Provider returned no assistant content.")

    def _extract_subject_body(self, content: str) -> dict[str, str]:
        subject = "Blostem follow-up"
        body = content.strip()
        if "Body:" in content:
            parts = content.split("Body:", maxsplit=1)
            subject_block = parts[0]
            body = parts[1].strip()
            if "Subject:" in subject_block:
                subject = subject_block.split("Subject:", maxsplit=1)[1].strip()
        return {"subject": subject, "body": body}

    def _parse_agent_response(self, content: str) -> dict[str, Any]:
        summary = content.strip()
        actions: list[str] = []
        notes: list[str] = []
        section = "summary"
        summary_lines: list[str] = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.lower()
            if lowered.startswith("summary:"):
                section = "summary"
                summary_lines.append(line.split(":", maxsplit=1)[1].strip())
                continue
            if lowered.startswith("actions:"):
                section = "actions"
                continue
            if lowered.startswith("notes:"):
                section = "notes"
                continue
            if line.startswith("-"):
                if section == "actions":
                    actions.append(line[1:].strip())
                elif section == "notes":
                    notes.append(line[1:].strip())
                else:
                    summary_lines.append(line[1:].strip())
                continue
            if section == "summary":
                summary_lines.append(line)
        if summary_lines:
            summary = " ".join(summary_lines)
        return {
            "summary": summary,
            "suggested_actions": actions or ["Review the current account evidence and choose the next approved move."],
            "notes": notes or ["Structured response parsed without model-side notes."],
        }

    def _record_provider_health(self, provider: str, status: str, detail: str | None) -> None:
        PROVIDER_HEALTH[provider] = {
            "status": status,
            "detail": detail,
            "checked_at": datetime.now(UTC).isoformat(),
        }

    def _summarize_http_error(self, response: httpx.Response) -> str:
        return f"HTTP {response.status_code}"

    def _summarize_exception(self, exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            return self._summarize_http_error(exc.response)
        return exc.__class__.__name__
