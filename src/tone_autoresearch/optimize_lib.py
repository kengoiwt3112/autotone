from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path
from typing import Any

from .evaluate_lib import evaluate_prompt
from .llm import LLMClient
from .settings import load_settings
from .utils import human_preview, read_text, write_json, write_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize the working prompt with a keep/revert loop.")
    parser.add_argument("--rounds", type=int, default=None, help="Max rounds per experiment (default: unlimited)")
    parser.add_argument("--budget", type=int, default=300, help="Time budget per experiment in seconds (default 300 = 5 min)")
    parser.add_argument("--experiments", type=int, default=None, help="Number of experiments to run (default: unlimited = run forever)")
    parser.add_argument("--limit", type=int, default=None, help="Optional validation set limit")
    args = parser.parse_args()

    settings = load_settings()
    project_root = settings.project_root
    prompt_path = project_root / "prompts" / "working_prompt.md"
    best_prompt_path = project_root / "prompts" / "best_prompt.md"
    program_path = project_root / "program.md"
    runs_dir = project_root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    if best_prompt_path.exists():
        shutil.copy2(best_prompt_path, prompt_path)

    best_eval = evaluate_prompt(
        prompt_path=prompt_path,
        split="validation",
        limit=args.limit,
        settings=settings,
    )
    best_score = float(best_eval["overall_score"])
    write_json(project_root / "artifacts" / "best_eval.json", best_eval)
    shutil.copy2(prompt_path, best_prompt_path)

    llm = LLMClient(settings)
    global_round = 0
    experiment = 0

    print(f"Baseline score: {best_score:.2f}")
    print(f"Budget: {args.budget}s per experiment | Running continuously (Ctrl-C to stop)")

    while True:
        experiment += 1
        if args.experiments is not None and experiment > args.experiments:
            break

        t_start = time.time()
        round_in_exp = 0
        print(f"\n=== Experiment {experiment} started ===")

        while True:
            round_in_exp += 1
            global_round += 1
            elapsed = time.time() - t_start
            if elapsed >= args.budget:
                print(f"--- Experiment {experiment} done ({elapsed:.0f}s, {round_in_exp - 1} rounds) ---")
                break
            if args.rounds is not None and round_in_exp > args.rounds:
                print(f"--- Experiment {experiment} done ({round_in_exp - 1} rounds) ---")
                break

            current_prompt = read_text(prompt_path)
            program_md = read_text(program_path)
            candidate_prompt = propose_candidate_prompt(
                llm=llm,
                settings=settings,
                current_prompt=current_prompt,
                best_eval=best_eval,
                program_md=program_md,
                round_idx=global_round,
            )

            round_dir = runs_dir / f"round_{global_round:03d}"
            round_dir.mkdir(parents=True, exist_ok=True)
            write_text(round_dir / "candidate_prompt.md", candidate_prompt)

            write_text(prompt_path, candidate_prompt)
            candidate_eval = evaluate_prompt(
                prompt_path=prompt_path,
                split="validation",
                limit=args.limit,
                settings=settings,
            )
            write_json(round_dir / "eval.json", candidate_eval)

            score = float(candidate_eval["overall_score"])
            if score > best_score:
                best_score = score
                best_eval = candidate_eval
                shutil.copy2(prompt_path, best_prompt_path)
                write_json(project_root / "artifacts" / "best_eval.json", best_eval)
                status = "ACCEPT"
            else:
                shutil.copy2(best_prompt_path, prompt_path)
                status = "REJECT"

            elapsed = time.time() - t_start
            print(f"  [exp {experiment} round {round_in_exp:02d}] {status} {score:.2f} (best {best_score:.2f}) [{elapsed:.0f}s]")

    print(f"\nBest prompt: {best_prompt_path}")
    print(f"Best score: {best_score:.2f}")


def propose_candidate_prompt(
    *,
    llm: LLMClient,
    settings,
    current_prompt: str,
    best_eval: dict[str, Any],
    program_md: str,
    round_idx: int,
) -> str:
    if settings.optimizer_model and not settings.mock_llm:
        return propose_with_llm(
            llm=llm,
            model=settings.optimizer_model,
            current_prompt=current_prompt,
            best_eval=best_eval,
            program_md=program_md,
            round_idx=round_idx,
        )
    return propose_heuristic(current_prompt, best_eval, round_idx)


def propose_with_llm(
    *,
    llm: LLMClient,
    model: str,
    current_prompt: str,
    best_eval: dict[str, Any],
    program_md: str,
    round_idx: int,
) -> str:
    worst_examples = sorted(best_eval.get("examples", []), key=lambda x: x["sample_score"])[:3]
    summary_lines = []
    for ex in worst_examples:
        summary_lines.append(
            f"- {ex['id']} ({ex['platform']}) score={ex['sample_score']*100:.1f} "
            f"topic={human_preview(ex['topic'], 70)} "
            f"judge_comment={human_preview(ex['judge'].get('comment',''), 80)}"
        )
    system = (
        "You are rewriting a prompt template for an autoresearch loop. "
        "Return the full revised prompt template only. "
        "Preserve all placeholders exactly: {{STYLE_BRIEF}}, {{PLATFORM}}, {{TOPIC}}, {{TARGET_LENGTH}}."
    )
    user = (
        f"Round: {round_idx}\n\n"
        f"Research brief:\n{program_md}\n\n"
        f"Current prompt:\n{current_prompt}\n\n"
        f"Current best overall score: {best_eval.get('overall_score', 0.0)}\n"
        f"Aggregate metrics: {best_eval.get('aggregate_metrics', {})}\n"
        f"Worst examples:\n" + "\n".join(summary_lines) + "\n\n"
        "Rewrite the prompt template to improve tone matching on held-out examples. "
        "Keep it short and practical."
    )
    proposal = llm.chat(model=model, system=system, user=user, temperature=0.7, max_tokens=4000).strip()
    return sanitize_candidate_prompt(proposal, current_prompt)


def propose_heuristic(current_prompt: str, best_eval: dict[str, Any], round_idx: int) -> str:
    agg = best_eval.get("aggregate_metrics", {})
    prompt = current_prompt

    additions = []
    if agg.get("copy_penalty", 0.0) > 0.35:
        additions.append("- Never reuse distinctive phrasing from the corpus; transfer style, not wording.")
    if agg.get("platform_fit", 1.0) < 0.75:
        additions.append("- Make X outputs feel tighter; make Slack outputs slightly more contextual and operational.")
    if agg.get("topic_overlap", 1.0) < 0.6:
        additions.append("- Stay anchored to the topic instead of drifting into generic commentary.")
    if agg.get("profile_similarity", 1.0) < 0.7:
        additions.append("- Match the author's cadence and punctuation habits more closely, but keep the writing natural.")
    if agg.get("reference_similarity", 1.0) < 0.65:
        additions.append("- Keep sentence length and structure closer to the author's usual range.")

    if not additions:
        additions.append("- Keep the writing sharp, natural, and slightly compressed.")

    marker = "Rules:\n"
    if marker in prompt:
        idx = prompt.index(marker) + len(marker)
        insertion = "\n".join(additions) + "\n"
        prompt = prompt[:idx] + insertion + prompt[idx:]
    else:
        prompt += "\n\n" + "\n".join(additions) + "\n"
    return sanitize_candidate_prompt(prompt, current_prompt)


def sanitize_candidate_prompt(candidate: str, fallback: str) -> str:
    candidate = candidate.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("```", 1)[-1]
        if "```" in candidate:
            candidate = candidate.rsplit("```", 1)[0]
        candidate = candidate.strip()
    required = ["{{STYLE_BRIEF}}", "{{PLATFORM}}", "{{TOPIC}}", "{{TARGET_LENGTH}}"]
    if any(token not in candidate for token in required):
        return fallback
    return candidate
