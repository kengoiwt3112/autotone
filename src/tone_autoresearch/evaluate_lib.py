from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .data import load_dataset
from .llm import LLMClient
from .metrics import local_style_bundle
from .settings import load_settings
from .utils import (
    clamp,
    extract_json_object,
    mean,
    read_json,
    read_text,
    safe_float,
    write_json,
    write_text,
)

REQUIRED_PLACEHOLDERS = ["{{STYLE_BRIEF}}", "{{PLATFORM}}", "{{TOPIC}}", "{{TARGET_LENGTH}}"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a prompt against held-out examples.")
    parser.add_argument("--prompt", type=Path, default=None, help="Path to prompt template")
    parser.add_argument("--limit", type=int, default=None, help="Optional validation set limit")
    parser.add_argument("--split", type=str, default="validation", choices=["validation", "train"])
    parser.add_argument("--output", type=Path, default=None, help="Path to JSON output")
    args = parser.parse_args()

    settings = load_settings()
    project_root = settings.project_root
    prompt_path = args.prompt or (project_root / "prompts" / "working_prompt.md")
    output_path = args.output or (project_root / "artifacts" / "latest_eval.json")

    result = evaluate_prompt(
        prompt_path=prompt_path,
        split=args.split,
        limit=args.limit,
        settings=settings,
    )
    write_json(output_path, result)
    report_path = output_path.with_name("latest_report.md")
    write_text(report_path, build_markdown_report(result))

    print(f"Score: {result['overall_score']:.2f}")
    print(f"Wrote: {output_path}")
    print(f"Wrote: {report_path}")


def evaluate_prompt(
    *,
    prompt_path: Path,
    split: str,
    limit: int | None,
    settings,
) -> dict[str, Any]:
    project_root = settings.project_root
    dataset = load_dataset(project_root / "artifacts" / "dataset.json")
    profile = read_json(project_root / "artifacts" / "style_profile.json")
    style_brief = read_text(project_root / "artifacts" / "style_brief.md")
    prompt_template = read_text(prompt_path)

    missing = [p for p in REQUIRED_PLACEHOLDERS if p not in prompt_template]
    if missing:
        return {
            "prompt_path": str(prompt_path),
            "error": f"Missing required placeholders: {missing}",
            "overall_score": 0.0,
            "examples": [],
        }

    rows = list(dataset[split])
    if limit is not None:
        rows = rows[:limit]
    llm = LLMClient(settings)
    all_references = [row["reference_text"] for row in dataset["train"]] + [row["reference_text"] for row in dataset["validation"]]

    examples = []
    for row in rows:
        rendered = render_prompt(prompt_template, style_brief, row)
        if settings.mock_llm:
            generated = mock_generate(rendered, row)
        else:
            if not settings.generator_model:
                raise SystemExit("GENERATOR_MODEL is required unless MOCK_LLM=1.")
            generated = generate_post(llm, settings.generator_model, rendered, row["target_length"])

        local = local_style_bundle(
            generated_text=generated,
            reference_text=row["reference_text"],
            all_references=all_references,
            profile=profile,
            platform=row["platform"],
            topic=row["topic"],
            target_length=row["target_length"],
        )

        if settings.mock_llm or not settings.judge_model:
            judge = heuristic_judge(row, generated, local)
        else:
            judge = judge_post(llm, settings.judge_model, row, generated)

        sample_score = combine_scores(local, judge)
        examples.append(
            {
                "id": row["id"],
                "platform": row["platform"],
                "topic": row["topic"],
                "target_length": row["target_length"],
                "reference_text": row["reference_text"],
                "generated_text": generated,
                "local_metrics": local,
                "judge": judge,
                "sample_score": round(sample_score, 4),
            }
        )

    overall = mean([ex["sample_score"] for ex in examples]) * 100.0
    aggregate = aggregate_metrics(examples)
    return {
        "prompt_path": str(prompt_path),
        "split": split,
        "example_count": len(examples),
        "overall_score": round(overall, 3),
        "aggregate_metrics": aggregate,
        "examples": examples,
    }


def render_prompt(prompt_template: str, style_brief: str, row: dict[str, Any]) -> str:
    return (
        prompt_template
        .replace("{{STYLE_BRIEF}}", style_brief)
        .replace("{{PLATFORM}}", row["platform"])
        .replace("{{TOPIC}}", row["topic"])
        .replace("{{TARGET_LENGTH}}", str(row["target_length"]))
    )


def generate_post(llm: LLMClient, model: str, rendered_prompt: str, target_length: int) -> str:
    system = (
        "You are a careful writing assistant. Follow the user's writing prompt exactly. "
        "Return only the final text, with no explanation."
    )
    user = rendered_prompt
    # reasoningモデル(GPT-5等)はmax_completion_tokensにreasoning分も含むため余裕を持たせる
    base_tokens = max(160, min(600, target_length * 3))
    max_tokens = base_tokens + 2000
    text = llm.chat(model=model, system=system, user=user, temperature=0.3, max_tokens=max_tokens).strip()
    return strip_outer_quotes(text)


def judge_post(llm: LLMClient, model: str, row: dict[str, Any], generated_text: str) -> dict[str, Any]:
    system = (
        "You evaluate whether a generated post matches the same author's style as a reference post "
        "without copying it. Return JSON only."
    )
    user = (
        f"Platform: {row['platform']}\n"
        f"Topic hint: {row['topic']}\n\n"
        f"Reference post:\n{row['reference_text']}\n\n"
        f"Generated post:\n{generated_text}\n\n"
        "Return JSON with keys:\n"
        "{"
        '"style_similarity": 0-10, '
        '"same_author_likelihood": 0-10, '
        '"topicality": 0-10, '
        '"platform_fit": 0-10, '
        '"copy_risk": 0-10, '
        '"comment": "short comment"'
        "}\n"
        "High copy_risk means the generated text feels too close to the reference."
    )
    raw = llm.chat(model=model, system=system, user=user, temperature=0.0, max_tokens=2500, json_mode=True)
    data = extract_json_object(raw)
    return normalize_judge(data)


def normalize_judge(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "style_similarity": clamp(safe_float(data.get("style_similarity"), 0.0), 0.0, 10.0),
        "same_author_likelihood": clamp(safe_float(data.get("same_author_likelihood"), 0.0), 0.0, 10.0),
        "topicality": clamp(safe_float(data.get("topicality"), 0.0), 0.0, 10.0),
        "platform_fit": clamp(safe_float(data.get("platform_fit"), 0.0), 0.0, 10.0),
        "copy_risk": clamp(safe_float(data.get("copy_risk"), 0.0), 0.0, 10.0),
        "comment": str(data.get("comment", "")).strip(),
    }


def heuristic_judge(row: dict[str, Any], generated_text: str, local: dict[str, float]) -> dict[str, Any]:
    style = 10.0 * (0.55 * local["profile_similarity"] + 0.45 * local["reference_similarity"])
    same_author = 10.0 * (0.65 * local["profile_similarity"] + 0.35 * (1.0 - local["copy_penalty"]))
    topicality = 10.0 * local["topic_overlap"]
    platform_fit = 10.0 * local["platform_fit"]
    copy_risk = 10.0 * local["copy_penalty"]
    return {
        "style_similarity": round(style, 2),
        "same_author_likelihood": round(same_author, 2),
        "topicality": round(topicality, 2),
        "platform_fit": round(platform_fit, 2),
        "copy_risk": round(copy_risk, 2),
        "comment": "Heuristic fallback judge",
    }


def combine_scores(local: dict[str, float], judge: dict[str, Any]) -> float:
    judge_style = judge["style_similarity"] / 10.0
    judge_author = judge["same_author_likelihood"] / 10.0
    judge_topic = judge["topicality"] / 10.0
    judge_platform = judge["platform_fit"] / 10.0
    judge_copy = judge["copy_risk"] / 10.0

    score = (
        0.33 * judge_style
        + 0.15 * judge_author
        + 0.10 * judge_topic
        + 0.10 * judge_platform
        + 0.15 * local["profile_similarity"]
        + 0.07 * local["reference_similarity"]
        + 0.05 * local["length_score"]
        + 0.05 * local["topic_overlap"]
    )
    penalty = 0.25 * max(local["copy_penalty"], judge_copy)
    return clamp(score - penalty, 0.0, 1.0)


def aggregate_metrics(examples: list[dict[str, Any]]) -> dict[str, float]:
    if not examples:
        return {}
    profile_scores = [ex["local_metrics"]["profile_similarity"] for ex in examples]
    ref_scores = [ex["local_metrics"]["reference_similarity"] for ex in examples]
    copy_penalties = [ex["local_metrics"]["copy_penalty"] for ex in examples]
    topic_scores = [ex["local_metrics"]["topic_overlap"] for ex in examples]
    platform_scores = [ex["local_metrics"]["platform_fit"] for ex in examples]
    judge_style = [ex["judge"]["style_similarity"] / 10.0 for ex in examples]
    judge_author = [ex["judge"]["same_author_likelihood"] / 10.0 for ex in examples]
    return {
        "profile_similarity": round(mean(profile_scores), 4),
        "reference_similarity": round(mean(ref_scores), 4),
        "copy_penalty": round(mean(copy_penalties), 4),
        "topic_overlap": round(mean(topic_scores), 4),
        "platform_fit": round(mean(platform_scores), 4),
        "judge_style_similarity": round(mean(judge_style), 4),
        "judge_same_author": round(mean(judge_author), 4),
    }


def build_markdown_report(result: dict[str, Any]) -> str:
    lines = []
    lines.append("# Evaluation report")
    lines.append("")
    lines.append(f"- Overall score: **{result.get('overall_score', 0.0):.2f}**")
    lines.append(f"- Split: `{result.get('split', 'validation')}`")
    lines.append(f"- Examples: `{result.get('example_count', 0)}`")
    lines.append("")

    agg = result.get("aggregate_metrics", {})
    if agg:
        lines.append("## Aggregate metrics")
        lines.append("")
        for key, value in agg.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    examples = sorted(result.get("examples", []), key=lambda x: x["sample_score"])
    if not examples:
        return "\n".join(lines)

    lines.append("## Lowest scoring examples")
    lines.append("")
    for ex in examples[:3]:
        lines.extend(format_example_block(ex))

    lines.append("## Highest scoring examples")
    lines.append("")
    for ex in examples[-3:]:
        lines.extend(format_example_block(ex))

    return "\n".join(lines)


def format_example_block(ex: dict[str, Any]) -> list[str]:
    return [
        f"### {ex['id']} — score {ex['sample_score']*100:.1f}",
        "",
        f"- platform: `{ex['platform']}`",
        f"- topic: {ex['topic']}",
        f"- judge comment: {ex['judge'].get('comment','')}",
        "",
        "**reference**",
        "",
        ex["reference_text"],
        "",
        "**generated**",
        "",
        ex["generated_text"],
        "",
    ]


def mock_generate(rendered_prompt: str, row: dict[str, Any]) -> str:
    topic = row["topic"]
    platform = row["platform"]
    if platform == "x":
        return f"{topic}。派手さより、回るループの方が効く。"
    return f"{topic}について共有です。結論だけ言うと、まずは小さく回してから広げるのが良さそうです。"


def strip_outer_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
        return text[1:-1].strip()
    return text
