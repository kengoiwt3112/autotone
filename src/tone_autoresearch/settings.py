from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Settings:
    project_root: Path
    openai_base_url: str
    openai_api_key: str
    generator_model: str | None
    judge_model: str | None
    prep_model: str | None
    request_timeout_s: int
    random_seed: int
    train_ratio: float
    disable_llm_cache: bool
    mock_llm: bool

    @property
    def cache_dir(self) -> Path:
        return self.project_root / ".cache" / "llm"


def load_settings(project_root: Path | None = None) -> Settings:
    if project_root is None:
        project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")

    return Settings(
        project_root=project_root,
        openai_base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        openai_api_key=os.getenv("OPENAI_API_KEY", "ollama"),
        generator_model=_empty_to_none(os.getenv("GENERATOR_MODEL")),
        judge_model=_empty_to_none(os.getenv("JUDGE_MODEL")),
        prep_model=_empty_to_none(os.getenv("PREP_MODEL")),
        request_timeout_s=int(os.getenv("REQUEST_TIMEOUT_S", "120")),
        random_seed=int(os.getenv("RANDOM_SEED", "42")),
        train_ratio=float(os.getenv("TRAIN_RATIO", "0.7")),
        disable_llm_cache=os.getenv("DISABLE_LLM_CACHE", "0") == "1",
        mock_llm=os.getenv("MOCK_LLM", "0") == "1",
    )


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
