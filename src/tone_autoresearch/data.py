from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from .metrics import detect_language
from .utils import read_json, read_jsonl, write_json


def default_input_path(project_root: Path) -> Path:
    private_path = project_root / "data" / "private" / "raw_posts.jsonl"
    if private_path.exists():
        return private_path
    return project_root / "data" / "sample_raw_posts.jsonl"


def load_raw_posts(path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    cleaned: list[dict[str, Any]] = []
    seen = set()

    for i, row in enumerate(rows):
        text = str(row.get("text", "")).strip()
        if not text:
            continue
        platform = str(row.get("platform", "x")).strip().lower()
        if platform not in {"x", "slack"}:
            platform = "x"
        key = (platform, text)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(
            {
                "id": str(row.get("id", f"post_{i+1:03d}")),
                "platform": platform,
                "text": text,
                "topic": row.get("topic"),
                "language": row.get("language") or detect_language(text),
            }
        )
    return cleaned


def stratified_split(
    rows: list[dict[str, Any]], train_ratio: float, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["platform"]].append(row)

    train: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    rng = random.Random(seed)

    for group in grouped.values():
        group = list(group)
        rng.shuffle(group)
        cut = max(1, int(len(group) * train_ratio))
        cut = min(cut, max(1, len(group) - 1))
        train.extend(group[:cut])
        validation.extend(group[cut:])

    train.sort(key=lambda x: x["id"])
    validation.sort(key=lambda x: x["id"])
    return train, validation


def save_dataset(path: Path, train: list[dict[str, Any]], validation: list[dict[str, Any]]) -> None:
    write_json(path, {"train": train, "validation": validation})


def load_dataset(path: Path) -> dict[str, Any]:
    return read_json(path)
