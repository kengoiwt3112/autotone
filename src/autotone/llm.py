from __future__ import annotations

import json
from pathlib import Path

from anthropic import Anthropic
from openai import BadRequestError, OpenAI

from .settings import Settings
from .utils import ensure_dir, extract_json_object, short_hash


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: OpenAI | None = None
        self._anthropic_client: Anthropic | None = None
        if not settings.mock_llm:
            if settings.llm_provider == "anthropic":
                if not settings.anthropic_api_key:
                    raise SystemExit(
                        "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic. "
                        "Set it in .env or export ANTHROPIC_API_KEY=..."
                    )
                self._anthropic_client = Anthropic(
                    api_key=settings.anthropic_api_key,
                    timeout=settings.request_timeout_s,
                )
            elif settings.llm_provider == "openai":
                self._client = OpenAI(
                    base_url=settings.openai_base_url,
                    api_key=settings.openai_api_key,
                    timeout=settings.request_timeout_s,
                )
            else:
                raise SystemExit(
                    f"Unknown LLM_PROVIDER: {settings.llm_provider!r}. "
                    "Valid values: 'openai', 'anthropic'."
                )

    def chat(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        json_mode: bool = False,
    ) -> str:
        if self.settings.mock_llm:
            raise RuntimeError("chat() should not be called in MOCK_LLM mode.")

        payload = {
            "llm_provider": self.settings.llm_provider,
            "base_url": self.settings.openai_base_url if self.settings.llm_provider == "openai" else "anthropic",
            "model": model,
            "system": system,
            "user": user,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "json_mode": json_mode,
        }
        cache_path = self._cache_path(payload)
        if cache_path is not None and cache_path.exists():
            return cache_path.read_text(encoding="utf-8")

        if self.settings.llm_provider == "anthropic":
            text = self._chat_anthropic(
                model=model, system=system, user=user,
                temperature=temperature, max_tokens=max_tokens,
                json_mode=json_mode,
            )
        else:
            text = self._chat_openai(
                model=model, system=system, user=user,
                temperature=temperature, max_tokens=max_tokens,
                json_mode=json_mode,
            )

        if cache_path is not None:
            ensure_dir(cache_path.parent)
            cache_path.write_text(text, encoding="utf-8")
        return text

    def _chat_openai(
        self, *, model: str, system: str, user: str,
        temperature: float, max_tokens: int, json_mode: bool,
    ) -> str:
        assert self._client is not None
        # GPT-5系はtemperatureのカスタム値を未サポートのため、デフォルト(1.0)以外を指定する場合のみ渡す
        kwargs: dict = {
            "model": model,
            "max_completion_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if temperature != 1.0:
            # temperatureをサポートしないモデルではエラーになるため、try/fallback
            kwargs["temperature"] = temperature
        try:
            response = self._client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            # temperature が拒否された場合のみデフォルトで再試行する
            if "temperature" not in _stringify_bad_request(exc).lower():
                raise
            kwargs.pop("temperature", None)
            response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def _chat_anthropic(
        self, *, model: str, system: str, user: str,
        temperature: float, max_tokens: int, json_mode: bool,
    ) -> str:
        assert self._anthropic_client is not None
        if json_mode:
            system = (
                system
                + "\n\nReturn only a valid JSON object. "
                + "Do not add markdown fences or explanatory text."
            )
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if temperature != 1.0:
            kwargs["temperature"] = temperature
        response = self._anthropic_client.messages.create(**kwargs)
        text = self._extract_anthropic_text(response)
        if not json_mode:
            return text

        parsed = self._try_extract_json_text(text)
        if parsed is not None:
            return parsed

        repair_response = self._anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system="Convert the input into a valid JSON object. Return only JSON.",
            messages=[{
                "role": "user",
                "content": (
                    "Rewrite this as strict JSON with no markdown fences or extra prose.\n\n"
                    f"{text}"
                ),
            }],
        )
        repaired_text = self._extract_anthropic_text(repair_response)
        parsed = self._try_extract_json_text(repaired_text)
        if parsed is not None:
            return parsed
        return repaired_text

    @staticmethod
    def _extract_anthropic_text(response) -> str:
        if not response.content:
            return ""
        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", "")
            if text:
                parts.append(text)
        return "".join(parts)

    @staticmethod
    def _try_extract_json_text(text: str) -> str | None:
        try:
            data = extract_json_object(text)
        except Exception:
            return None
        return json.dumps(data, ensure_ascii=False)

    def _cache_path(self, payload: dict) -> Path | None:
        if self.settings.disable_llm_cache:
            return None
        key = short_hash(payload)
        return self.settings.cache_dir / f"{key}.txt"


def _stringify_bad_request(exc: BadRequestError) -> str:
    body = getattr(exc, "body", None)
    if body is not None:
        return str(body)
    message = getattr(exc, "message", None)
    if message is not None:
        return str(message)
    return str(exc)
