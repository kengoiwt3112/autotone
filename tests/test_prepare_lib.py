from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autotone.prepare_lib import infer_topic_with_llm
from autotone.settings import Settings


class EmptyLLM:
    def chat(self, **kwargs) -> str:
        return ""


class PrepareLibTests(unittest.TestCase):
    def make_settings(self) -> Settings:
        root = Path(tempfile.mkdtemp(prefix="autotone-test-"))
        return Settings(
            project_root=root,
            llm_provider="openai",
            openai_base_url="https://api.example.com/v1",
            openai_api_key="test-key",
            anthropic_api_key="",
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

    def test_infer_topic_with_llm_falls_back_on_empty_response(self) -> None:
        topic = infer_topic_with_llm(
            EmptyLLM(),
            "prep-model",
            "新機能のリリース準備を進めていて、QA の詰めが残っている。",
        )

        self.assertTrue(topic)
        self.assertNotEqual(topic, "")


if __name__ == "__main__":
    unittest.main()
