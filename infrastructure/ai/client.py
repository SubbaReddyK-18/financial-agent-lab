"""
infrastructure/ai/client.py

Lightweight, vendor-agnostic HTTP and Mock clients for AI decision inference.

ARCHITECTURAL PRINCIPLES (Block 4, Part 2 & Part 23):
1. Protocol-based LLMClient interface.
2. MockLLMClient for 100% deterministic, offline test execution without live API dependencies.
3. GeminiRESTClient for calling Google Gemini REST API (gemini-2.5-flash) using httpx.
4. HttpOpenAIClient for calling OpenAI-compatible JSON endpoints.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Optional, Protocol

import httpx

from apps.api.settings import Settings, get_settings


@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


class LLMClient(Protocol):
    """Abstract protocol for language model inference clients."""

    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        ...


class MockLLMClient:
    """
    Deterministic mock LLM client for testing and offline simulation.
    """

    def __init__(
        self,
        canned_response: Optional[str] = None,
        should_fail: bool = False,
        failure_error: Optional[Exception] = None,
        latency_ms: float = 12.5,
    ):
        self.canned_response = canned_response
        self.should_fail = should_fail
        self.failure_error = failure_error or RuntimeError("Mock AI provider error")
        self.latency_ms = latency_ms

    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        if self.should_fail:
            raise self.failure_error

        if self.canned_response is not None:
            return LLMResponse(
                content=self.canned_response,
                input_tokens=180,
                output_tokens=75,
                latency_ms=self.latency_ms,
            )

        # Dynamic heuristic mock: parse user prompt JSON to produce a realistic AI response
        try:
            # Extract JSON block from user prompt
            json_str = user_prompt.split("Evaluate this failed payment context and propose the optimal recovery action:\n\n")[-1]
            data = json.loads(json_str)
            code = data.get("payment", {}).get("failure_code", "").upper()
            attempts = data.get("payment", {}).get("attempt_count", 1)
            is_cooldown = data.get("temporal_context", {}).get("is_cooldown_active", False)
            segment = data.get("customer_profile", {}).get("customer_segment", "RETURNING")

            if is_cooldown or attempts > 2:
                action = "WAIT"
                conf = 0.85
                reason_codes = ["COOLDOWN_ACTIVE" if is_cooldown else "MAX_ATTEMPTS_EXCEEDED"]
                discount = 0
            elif "TIMEOUT" in code or "NETWORK" in code or "GATEWAY" in code or "ISSUER" in code:
                action = "RETRY"
                conf = 0.80
                reason_codes = ["TRANSIENT_TECHNICAL_ERROR", "LOW_ATTEMPT_COUNT"]
                discount = 0
            elif "OTP" in code or "AUTH" in code or "MPIN" in code or "USER" in code:
                action = "PAYMENT_LINK"
                conf = 0.75
                reason_codes = ["CUSTOMER_ACTIONABLE_DROP", "PAYMENT_LINK_SUITABLE"]
                discount = 5 if segment == "VIP" else 0
            else:
                action = "WAIT"
                conf = 0.65
                reason_codes = ["UNCERTAIN_FAILURE_REGIME"]
                discount = 0

            resp_dict = {
                "recommended_action": action,
                "confidence": conf,
                "estimated_action_success_probability": 0.65 if action != "WAIT" else 0.20,
                "estimated_natural_recovery_probability": 0.20,
                "reasoning_codes": reason_codes,
                "uncertainty": "LOW" if conf > 0.75 else "MEDIUM",
                "requires_human_review": False,
                "concise_rationale": f"Mock AI chose {action} based on observed {code}.",
                "recommended_discount_percent": discount,
            }
            content = json.dumps(resp_dict)
        except Exception:
            content = json.dumps({
                "recommended_action": "WAIT",
                "confidence": 0.50,
                "reasoning_codes": ["FALLBACK_MOCK"],
                "uncertainty": "HIGH",
                "requires_human_review": False,
                "concise_rationale": "Fallback mock response.",
                "recommended_discount_percent": 0,
            })

        return LLMResponse(
            content=content,
            input_tokens=180,
            output_tokens=75,
            latency_ms=self.latency_ms,
        )


class GeminiRESTClient:
    """
    Direct HTTP client for Google Gemini API (gemini-flash-latest) using structured JSON output.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-flash-latest",
        timeout_seconds: float = 15.0,
    ):
        self.api_key = api_key or ""
        self.model = model or "gemini-flash-latest"
        self.timeout_seconds = timeout_seconds

    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        if not self.api_key:
            raise ValueError("AI_API_KEY must be configured for Gemini provider.")

        # If model is deprecated gemini-2.5-flash, map to gemini-flash-latest
        target_model = self.model
        if target_model in ("gemini-2.5-flash", "gemini-2.5"):
            target_model = "gemini-flash-latest"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        }

        max_retries = 4
        start_time = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for attempt in range(max_retries):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code == 429 and attempt < max_retries - 1:
                        await asyncio.sleep(4.5 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < max_retries - 1:
                        await asyncio.sleep(4.5 * (attempt + 1))
                        continue
                    raise

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        res_json = response.json()

        # Extract text content from candidates
        candidates = res_json.get("candidates", [])
        if not candidates:
            raise ValueError(f"Gemini API returned no candidates: {res_json}")

        choice = candidates[0]["content"]["parts"][0]["text"]
        usage = res_json.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)

        return LLMResponse(
            content=choice,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )


class HttpOpenAIClient:
    """
    Standard HTTP client calling any OpenAI-compatible API endpoint (OpenAI, Ollama, etc.).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 10.0,
    ):
        self.api_key = api_key or ""
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        if not self.api_key and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            raise ValueError("AI_API_KEY must be configured for remote LLM providers.")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        start_time = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        res_json = response.json()
        choice = res_json["choices"][0]["message"]["content"]
        usage = res_json.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=choice,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )


def create_llm_client(settings: Optional[Settings] = None) -> LLMClient:
    """Factory creating configured LLMClient instance based on application settings."""
    if settings is None:
        settings = get_settings()

    provider = settings.ai_provider.lower().strip()
    if provider == "mock":
        return MockLLMClient()

    if provider in ("gemini", "google"):
        return GeminiRESTClient(
            api_key=settings.ai_api_key,
            model=settings.ai_model or "gemini-flash-latest",
            timeout_seconds=settings.ai_timeout_seconds,
        )

    return HttpOpenAIClient(
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        base_url=settings.ai_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
    )
