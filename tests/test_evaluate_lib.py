from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autotone.evaluate_lib import build_redacted_eval, _resolve_prompt_path


class EvaluateLibTests(unittest.TestCase):
    def test_resolve_prompt_path_bootstraps_missing_working_prompt(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="autotone-eval-test-"))
        prompts_dir = root / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        default_prompt = prompts_dir / "default_prompt.md"
        default_prompt.write_text("default prompt body", encoding="utf-8")

        resolved = _resolve_prompt_path(root, Path("prompts/working_prompt.md"))

        self.assertEqual(resolved, prompts_dir / "working_prompt.md")
        self.assertTrue(resolved.exists())
        self.assertEqual(resolved.read_text(encoding="utf-8"), "default prompt body")

    def test_build_redacted_eval_strips_raw_text_and_comments(self) -> None:
        result = {
            "prompt_path": "prompts/working_prompt.md",
            "split": "validation",
            "example_count": 1,
            "overall_score": 71.2,
            "aggregate_metrics": {"copy_penalty": 0.1},
            "examples": [
                {
                    "id": "post_001",
                    "topic": "shipping / launch",
                    "target_length": 120,
                    "reference_text": "private reference text",
                    "generated_text": "private generated text",
                    "local_metrics": {"profile_similarity": 0.8},
                    "judge": {
                        "style_similarity": 7.0,
                        "same_author_likelihood": 6.5,
                        "copy_risk": 1.0,
                        "topic_fidelity": 8.0,
                        "comment": "too close to the reference",
                    },
                    "sample_score": 0.712,
                }
            ],
        }

        redacted = build_redacted_eval(result)

        self.assertEqual(redacted["overall_score"], 71.2)
        self.assertNotIn("reference_text", redacted["examples"][0])
        self.assertNotIn("generated_text", redacted["examples"][0])
        self.assertNotIn("comment", redacted["examples"][0]["judge"])
        self.assertEqual(redacted["examples"][0]["generated_length"], len("private generated text"))


if __name__ == "__main__":
    unittest.main()
