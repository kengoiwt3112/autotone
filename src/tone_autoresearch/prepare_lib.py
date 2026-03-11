from __future__ import annotations

import argparse
import textwrap
from pathlib import Path
from typing import Any

from .data import default_input_path, load_raw_posts, random_split, save_dataset
from .llm import LLMClient
from .metrics import build_style_profile, detect_language
from .settings import load_settings
from .utils import human_preview, write_json, write_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare dataset and style artifacts.")
    parser.add_argument("--input", type=Path, default=None, help="Path to raw_posts.jsonl")
    parser.add_argument("--output-dir", type=Path, default=None, help="Artifacts directory")
    args = parser.parse_args()

    settings = load_settings()
    project_root = settings.project_root
    input_path = args.input or default_input_path(project_root)
    output_dir = args.output_dir or (project_root / "artifacts")
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_raw_posts(input_path)
    if len(rows) < 4:
        raise SystemExit("Need at least 4 posts to create a train/validation split.")

    llm = LLMClient(settings)
    normalized = []
    for row in rows:
        topic = row.get("topic")
        if not topic:
            if settings.prep_model and not settings.mock_llm:
                topic = infer_topic_with_llm(llm, settings.prep_model, row["text"])
            else:
                topic = infer_topic_heuristic(row["text"])
        normalized.append(
            {
                "id": row["id"],
                "reference_text": row["text"],
                "topic": topic,
                "language": row.get("language") or detect_language(row["text"]),
                "target_length": len(row["text"]),
            }
        )

    train, validation = random_split(normalized, settings.train_ratio, settings.random_seed)
    save_dataset(output_dir / "dataset.json", train, validation)

    profile = build_style_profile(train)
    write_json(output_dir / "style_profile.json", profile)

    if settings.prep_model and not settings.mock_llm:
        style_brief = summarize_style_with_llm(llm, settings.prep_model, train)
    else:
        style_brief = summarize_style_heuristic(train)
    write_text(output_dir / "style_brief.md", style_brief)

    print(f"Input: {input_path}")
    print(f"Train examples: {len(train)}")
    print(f"Validation examples: {len(validation)}")
    print(f"Wrote: {output_dir / 'dataset.json'}")
    print(f"Wrote: {output_dir / 'style_profile.json'}")
    print(f"Wrote: {output_dir / 'style_brief.md'}")


def infer_topic_heuristic(text: str) -> str:
    clean = text.replace("\n", " ")
    clean = " ".join(clean.split())
    clean = clean.replace("http://", "").replace("https://", "")
    parts = clean.split("。")
    first = parts[0] if parts else clean
    first = first[:120].strip(" -–—:;,.!?！？")
    if len(first) < 10:
        return human_preview(clean, 90)
    return first


def infer_topic_with_llm(llm: LLMClient, model: str, text: str) -> str:
    system = (
        "You convert a personal post into a neutral topic hint for evaluation. "
        "Do not preserve the author's phrasing. Return only one short line."
    )
    user = (
        "Task: describe the main topic of this post in a neutral way.\n"
        "Keep it concise and reusable as a writing prompt.\n\n"
        f"POST:\n{text}"
    )
    topic = llm.chat(model=model, system=system, user=user, temperature=0.0, max_tokens=2000).strip()
    return topic.splitlines()[0].strip() or infer_topic_heuristic(text)


def summarize_style_with_llm(llm: LLMClient, model: str, train: list[dict[str, Any]]) -> str:
    example_block = []
    for row in train[:20]:
        example_block.append(human_preview(row['reference_text'], 220))
    system = (
        "You write a concise style brief for another model. "
        "Focus on tone, rhythm, structure, punctuation, confidence, and compression. "
        "Do not copy signature phrases. Use bullet points."
    )
    user = "Author posts:\n" + "\n".join(f"- {line}" for line in example_block)
    text = llm.chat(model=model, system=system, user=user, temperature=0.0, max_tokens=2500).strip()
    return text


def summarize_style_heuristic(train: list[dict[str, Any]]) -> str:
    texts = [r["reference_text"] for r in train]
    avg_len = int(sum(len(t) for t in texts) / max(1, len(texts)))
    joined = "\n".join(texts)

    traits = []
    if "?" in joined or "？" in joined:
        traits.append("sometimes uses rhetorical questions")
    if "—" in joined or "(" in joined or "（" in joined:
        traits.append("likes parenthetical / aside-like phrasing")
    if any("\n" in t for t in texts):
        traits.append("occasionally uses short line breaks")
    if joined.count("!") + joined.count("！") == 0:
        traits.append("rarely relies on exclamation marks")
    if not traits:
        traits.append("prefers direct statements over ornament")

    lines = [
        "- Overall voice: direct, compressed, and slightly skeptical rather than hype-driven.",
        "- Preference: concrete claims over generic inspiration.",
        "- Anti-pattern: avoid sounding like a generic assistant or marketing copy.",
        f"- Average post length: around {avg_len} characters.",
        f"- Traits: {'; '.join(traits)}.",
        "- Preserve the author's level of confidence: decisive, but not absolute unless the source style strongly suggests it.",
        "- Do not reuse distinctive phrases from the corpus verbatim.",
    ]
    return "\n".join(lines)
