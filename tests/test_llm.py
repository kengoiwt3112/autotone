from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from openai import BadRequestError

from autotone.llm import LLMClient
from autotone.settings import Settings


class FakeAnthropicClient:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.responses.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class LLMClientTests(unittest.TestCase):
    def make_settings(self) -> Settings:
        root = Path(tempfile.mkdtemp(prefix="autotone-test-"))
        return Settings(
            project_root=root,
            llm_provider="anthropic",
            openai_base_url="https://api.example.com/v1",
            openai_api_key="test-key",
            anthropic_api_key="test-key",
            generator_model="gen",
            judge_model="judge",
            prep_model="prep",
            request_timeout_s=30,
            random_seed=42,
            train_ratio=0.7,
            disable_llm_cache=True,
            mock_llm=False,
            max_evaluations=None,
        )

    def test_anthropic_json_mode_repairs_non_json_response(self) -> None:
        client = LLMClient(self.make_settings())
        fake = FakeAnthropicClient([
            "Score was 7 out of 10.",
            "{\"score\": 7}",
        ])
        client._anthropic_client = fake

        text = client.chat(
            model="judge",
            system="Return JSON only.",
            user="Evaluate this.",
            json_mode=True,
        )

        self.assertEqual(json.loads(text), {"score": 7})
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("Return only a valid JSON object", fake.calls[0]["system"])

    def test_cache_key_changes_with_provider_config(self) -> None:
        settings = self.make_settings()
        settings.disable_llm_cache = False
        client = LLMClient(settings)
        payload = {
            "llm_provider": "openai",
            "base_url": "https://api.one/v1",
            "model": "same-model",
            "system": "s",
            "user": "u",
            "temperature": 0.2,
            "max_tokens": 10,
            "json_mode": False,
        }
        other_payload = {
            **payload,
            "base_url": "https://api.two/v1",
        }

        self.assertNotEqual(client._cache_path(payload), client._cache_path(other_payload))

    def test_openai_bad_request_is_only_retried_for_temperature_errors(self) -> None:
        client = LLMClient(self.make_settings())

        class FakeOpenAI:
            def __init__(self):
                self.chat = self
                self.completions = self
                self.calls = 0

            def create(self, **kwargs):
                self.calls += 1
                raise BadRequestError(
                    message="unsupported response_format",
                    response=SimpleNamespace(request=None, status_code=400, headers={}),
                    body={"error": {"message": "unsupported response_format"}},
                )

        client.settings.llm_provider = "openai"
        client._client = FakeOpenAI()

        with self.assertRaises(BadRequestError):
            client.chat(model="gpt", system="s", user="u", json_mode=True)
        self.assertEqual(client._client.calls, 1)


if __name__ == "__main__":
    unittest.main()
