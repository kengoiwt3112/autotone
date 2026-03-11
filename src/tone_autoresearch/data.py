from __future__ import annotations

import random
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
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(
            {
                "id": str(row.get("id", f"post_{i+1:03d}")),
                "text": text,
                "language": row.get("language") or detect_language(text),
            }
        )
    return cleaned


def random_split(
    rows: list[dict[str, Any]], train_ratio: float, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    shuffled = list(rows)
    rng.shuffle(shuffled)
    cut = max(1, int(len(shuffled) * train_ratio))
    cut = min(cut, max(1, len(shuffled) - 1))
    train = sorted(shuffled[:cut], key=lambda x: x["id"])
    validation = sorted(shuffled[cut:], key=lambda x: x["id"])
    return train, validation


def save_dataset(path: Path, train: list[dict[str, Any]], validation: list[dict[str, Any]]) -> None:
    write_json(path, {"train": train, "validation": validation})


def load_dataset(path: Path) -> dict[str, Any]:
    return read_json(path)
