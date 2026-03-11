from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
from typing import Any

from .data import load_dataset
from .llm import LLMClient
from .metrics import local_style_bundle, topic_keyword_overlap
from .settings import load_settings
from .utils import (
    clamp,
    ensure_dir,
    extract_json_object,
    mean,
    read_json,
    read_text,
    safe_float,
    short_hash,
    write_json,
    write_text,
)

REQUIRED_PLACEHOLDERS = ["{{STYLE_BRIEF}}", "{{TOPIC}}", "{{TARGET_LENGTH}}"]


def _count_log_entries(log_path: Path) -> int:
    """experiments.jsonl の有効行数を返す。"""
    if not log_path.exists():
        return 0
    count = 0
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def _ensure_prompt(prompts_dir: Path, filename: str) -> Path:
    """working/best が無ければ default_prompt.md からコピーして返す。"""
    import shutil

    target = prompts_dir / filename
    if not target.exists():
        default = prompts_dir / "default_prompt.md"
        if not default.exists():
            raise SystemExit(f"Neither {target} nor {default} found.")
        shutil.copy2(default, target)
    return target


def _resolve_prompt_path(project_root: Path, prompt_path: Path | None) -> Path:
    prompts_dir = project_root / "prompts"
    if prompt_path is None:
        return _ensure_prompt(prompts_dir, "working_prompt.md")

    normalized = Path(*prompt_path.parts)
    if normalized in {Path("prompts/working_prompt.md"), Path("working_prompt.md")}:
        return _ensure_prompt(prompts_dir, "working_prompt.md")
    if normalized in {Path("prompts/best_prompt.md"), Path("best_prompt.md")}:
        return _ensure_prompt(prompts_dir, "best_prompt.md")
    return prompt_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a prompt against held-out examples.")
    parser.add_argument("--prompt", type=Path, default=None, help="Path to prompt template")
    parser.add_argument("--limit", type=int, default=None, help="Optional validation set limit")
    parser.add_argument("--split", type=str, default="validation", choices=["validation", "train"])
    parser.add_argument("--output", type=Path, default=None, help="Path to JSON output")
    parser.add_argument("--report", action="store_true", help="Generate latest_report.md (contains raw text, for human review)")
    args = parser.parse_args()

    settings = load_settings()
    project_root = settings.project_root

    # MAX_EVALUATIONS のハードキャップ（experiments.jsonl の行数で判定）
    if settings.max_evaluations is not None:
        experiment_log = project_root / "runs" / "experiments.jsonl"
        done = _count_log_entries(experiment_log)
        if done >= settings.max_evaluations:
            raise SystemExit(
                f"HARD STOP: {done} evaluations completed (cap: {settings.max_evaluations}). "
                f"Increase MAX_EVALUATIONS in .env or remove the cap to continue."
            )

    prompt_path = _resolve_prompt_path(project_root, args.prompt)
    output_path = args.output or (project_root / "artifacts" / "latest_eval.json")

    result = evaluate_prompt(
        prompt_path=prompt_path,
        split=args.split,
        limit=args.limit,
        settings=settings,
    )
    write_json(output_path, build_redacted_eval(result))

    # 人間向けレポート / raw JSON（生テキストを含むため --report 指定時のみ生成）
    report_path = output_path.with_name("latest_report.md")
    raw_output_path = output_path.with_name("latest_eval_raw.json")
    if args.report:
        write_json(raw_output_path, result)
        write_text(report_path, build_markdown_report(result))

    # エージェント向け構造化入力（生テキストを含まない安全な形式）
    agent_input_path = output_path.with_name("latest_agent_input.json")
    write_json(agent_input_path, build_agent_input(result))

    # 実験ログの追記
    experiment_log = project_root / "runs" / "experiments.jsonl"
    prompt_text = read_text(prompt_path)
    log_entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "prompt_hash": short_hash(prompt_text),
        "prompt_path": str(prompt_path),
        "split": result.get("split", "validation"),
        "example_count": result.get("example_count", 0),
        "overall_score": result.get("overall_score", 0.0),
        "aggregate_metrics": result.get("aggregate_metrics", {}),
    }
    ensure_dir(experiment_log.parent)
    with experiment_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    print(f"Score: {result['overall_score']:.2f}")
    print(f"Wrote: {output_path}")
    if args.report:
        print(f"Wrote: {raw_output_path}")
        print(f"Wrote: {report_path}")
    print(f"Wrote: {agent_input_path}")
    print(f"Wrote: {experiment_log}")


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
        f"Topic: {row['topic']}\n\n"
        f"Reference post:\n{row['reference_text']}\n\n"
        f"Generated post:\n{generated_text}\n\n"
        "Return JSON with keys:\n"
        "{"
        '"style_similarity": 0-10, '
        '"same_author_likelihood": 0-10, '
        '"copy_risk": 0-10, '
        '"topic_fidelity": 0-10, '
        '"comment": "short comment"'
        "}\n"
        "High copy_risk means the generated text feels too close to the reference.\n"
        "topic_fidelity measures how well the generated text addresses the given topic."
    )
    raw = llm.chat(model=model, system=system, user=user, temperature=0.0, max_tokens=2500, json_mode=True)
    data = extract_json_object(raw)
    return normalize_judge(data)


def normalize_judge(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "style_similarity": clamp(safe_float(data.get("style_similarity"), 0.0), 0.0, 10.0),
        "same_author_likelihood": clamp(safe_float(data.get("same_author_likelihood"), 0.0), 0.0, 10.0),
        "copy_risk": clamp(safe_float(data.get("copy_risk"), 0.0), 0.0, 10.0),
        "topic_fidelity": clamp(safe_float(data.get("topic_fidelity"), 5.0), 0.0, 10.0),
        "comment": str(data.get("comment", "")).strip(),
    }


def heuristic_judge(row: dict[str, Any], generated_text: str, local: dict[str, float]) -> dict[str, Any]:
    style = 10.0 * (0.55 * local["profile_similarity"] + 0.45 * local["reference_similarity"])
    same_author = 10.0 * (0.65 * local["profile_similarity"] + 0.35 * (1.0 - local["copy_penalty"]))
    copy_risk = 10.0 * local["copy_penalty"]
    topic_fid = 10.0 * topic_keyword_overlap(generated_text, row["topic"])
    return {
        "style_similarity": round(style, 2),
        "same_author_likelihood": round(same_author, 2),
        "copy_risk": round(copy_risk, 2),
        "topic_fidelity": round(topic_fid, 2),
        "comment": "Heuristic fallback judge",
    }


def combine_scores(local: dict[str, float], judge: dict[str, Any]) -> float:
    judge_style = judge["style_similarity"] / 10.0
    judge_author = judge["same_author_likelihood"] / 10.0
    judge_copy = judge["copy_risk"] / 10.0
    judge_topic = judge.get("topic_fidelity", 5.0) / 10.0

    score = (
        0.35 * judge_style
        + 0.15 * judge_author
        + 0.10 * judge_topic
        + 0.20 * local["profile_similarity"]
        + 0.10 * local["reference_similarity"]
        + 0.10 * local["length_score"]
    )
    penalty = 0.25 * max(local["copy_penalty"], judge_copy)
    return clamp(score - penalty, 0.0, 1.0)


def aggregate_metrics(examples: list[dict[str, Any]]) -> dict[str, float]:
    if not examples:
        return {}
    profile_scores = [ex["local_metrics"]["profile_similarity"] for ex in examples]
    ref_scores = [ex["local_metrics"]["reference_similarity"] for ex in examples]
    copy_penalties = [ex["local_metrics"]["copy_penalty"] for ex in examples]
    judge_style = [ex["judge"]["style_similarity"] / 10.0 for ex in examples]
    judge_author = [ex["judge"]["same_author_likelihood"] / 10.0 for ex in examples]
    judge_topic = [ex["judge"].get("topic_fidelity", 5.0) / 10.0 for ex in examples]
    return {
        "profile_similarity": round(mean(profile_scores), 4),
        "reference_similarity": round(mean(ref_scores), 4),
        "copy_penalty": round(mean(copy_penalties), 4),
        "judge_style_similarity": round(mean(judge_style), 4),
        "judge_same_author": round(mean(judge_author), 4),
        "judge_topic_fidelity": round(mean(judge_topic), 4),
    }


def build_redacted_eval(result: dict[str, Any]) -> dict[str, Any]:
    redacted_examples = []
    for ex in result.get("examples", []):
        redacted_examples.append(
            {
                "id": ex["id"],
                "topic": ex["topic"],
                "target_length": ex["target_length"],
                "generated_length": len(ex.get("generated_text", "")),
                "local_metrics": ex["local_metrics"],
                "judge": {k: v for k, v in ex["judge"].items() if k != "comment"},
                "sample_score": ex["sample_score"],
            }
        )

    redacted = {
        "prompt_path": result.get("prompt_path", ""),
        "split": result.get("split", "validation"),
        "example_count": result.get("example_count", 0),
        "overall_score": result.get("overall_score", 0.0),
        "aggregate_metrics": result.get("aggregate_metrics", {}),
        "examples": redacted_examples,
    }
    if "error" in result:
        redacted["error"] = result["error"]
    return redacted


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


def build_agent_input(result: dict[str, Any]) -> dict[str, Any]:
    """エージェントが読み取る構造化データ。生テキストは含まない。"""
    examples_summary = []
    for ex in result.get("examples", []):
        # judge の自由テキスト (comment) は間接プロンプトインジェクション防止のため除外
        # エージェントには構造化された hints のみを提供する
        judge_scores = {k: v for k, v in ex["judge"].items() if k != "comment"}
        examples_summary.append({
            "id": ex["id"],
            "topic": ex["topic"],
            "target_length": ex["target_length"],
            "generated_length": len(ex.get("generated_text", "")),
            "sample_score": ex["sample_score"],
            "local_metrics": ex["local_metrics"],
            "judge": judge_scores,
        })

    return {
        "prompt_path": result.get("prompt_path", ""),
        "split": result.get("split", "validation"),
        "example_count": result.get("example_count", 0),
        "overall_score": result.get("overall_score", 0.0),
        "aggregate_metrics": result.get("aggregate_metrics", {}),
        "examples": examples_summary,
        "hints": _generate_hints(result),
    }


def _generate_hints(result: dict[str, Any]) -> list[str]:
    """スコアに基づいて改善ヒントを最大5つ生成する。"""
    hints: list[str] = []
    agg = result.get("aggregate_metrics", {})

    if agg.get("copy_penalty", 0) > 0.15:
        hints.append("copy_penalty が高い。アンチコピー指示を強化すべき。")
    if agg.get("profile_similarity", 1) < 0.6:
        hints.append("profile_similarity が低い。スタイルプロファイルとの一致を改善すべき。")
    if agg.get("judge_style_similarity", 1) < 0.6:
        hints.append("judge_style_similarity が低い。文体の一貫性を改善すべき。")
    if agg.get("judge_topic_fidelity", 1) < 0.6:
        hints.append("topic_fidelity が低い。トピックへの忠実度を改善すべき。")

    examples = sorted(result.get("examples", []), key=lambda x: x["sample_score"])
    if examples and examples[0]["sample_score"] < 0.4:
        worst = examples[0]
        hints.append(f"最低スコア例 (id={worst['id']}, topic='{worst['topic']}'): score={worst['sample_score']:.2f}")

    return hints[:5]


def mock_generate(rendered_prompt: str, row: dict[str, Any]) -> str:
    topic = row["topic"]
    lang = row.get("language", "en")
    if lang == "ja":
        return f"{topic}。派手さより、回るループの方が効く。"
    return f"{topic}. Small loops beat big rewrites."


def strip_outer_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
        return text[1:-1].strip()
    return text
