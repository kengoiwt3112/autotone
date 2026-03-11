from __future__ import annotations

from pathlib import Path

from openai import BadRequestError, OpenAI

from .settings import Settings
from .utils import ensure_dir, short_hash


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: OpenAI | None = None
        if not settings.mock_llm:
            self._client = OpenAI(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
                timeout=settings.request_timeout_s,
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
        except BadRequestError:
            # temperatureが拒否された場合はデフォルトで再試行
            kwargs.pop("temperature", None)
            response = self._client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or ""
        if cache_path is not None:
            ensure_dir(cache_path.parent)
            cache_path.write_text(text, encoding="utf-8")
        return text

    def _cache_path(self, payload: dict) -> Path | None:
        if self.settings.disable_llm_cache:
            return None
        key = short_hash(payload)
        return self.settings.cache_dir / f"{key}.txt"
