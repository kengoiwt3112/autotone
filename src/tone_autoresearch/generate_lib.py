from __future__ import annotations

import argparse
from pathlib import Path

from .evaluate_lib import generate_post, render_prompt
from .llm import LLMClient
from .settings import load_settings
from .utils import read_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one new post with the best prompt.")
    parser.add_argument("--topic", required=True, help="Topic hint")
    parser.add_argument("--platform", default="x", choices=["x", "slack"])
    parser.add_argument("--prompt", type=Path, default=None, help="Optional prompt path")
    parser.add_argument("--target-length", type=int, default=None)
    args = parser.parse_args()

    settings = load_settings()
    project_root = settings.project_root
    prompt_path = args.prompt or (project_root / "prompts" / "best_prompt.md")
    prompt_template = read_text(prompt_path)
    style_brief = read_text(project_root / "artifacts" / "style_brief.md")

    row = {
        "platform": args.platform,
        "topic": args.topic,
        "target_length": args.target_length or (140 if args.platform == "x" else 220),
    }
    rendered = render_prompt(prompt_template, style_brief, row)

    if settings.mock_llm:
        from .evaluate_lib import mock_generate

        print(mock_generate(rendered, row))
        return

    if not settings.generator_model:
        raise SystemExit("GENERATOR_MODEL is required unless MOCK_LLM=1.")

    llm = LLMClient(settings)
    text = generate_post(llm, settings.generator_model, rendered, row["target_length"])
    print(text)
