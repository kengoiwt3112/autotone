from __future__ import annotations

import difflib
import math
import re
from collections import Counter
from typing import Any

from .utils import clamp, exp_similarity, mean


FEATURE_KEYS = [
    "char_count",
    "line_count",
    "avg_line_chars",
    "sentence_count",
    "avg_sentence_chars",
    "question_count",
    "exclaim_count",
    "ellipsis_count",
    "colon_count",
    "semicolon_count",
    "comma_count",
    "dash_count",
    "paren_count",
    "quote_count",
    "hashtag_count",
    "mention_count",
    "url_count",
    "emoji_count",
    "ascii_ratio",
    "hiragana_ratio",
    "katakana_ratio",
    "kanji_ratio",
    "newline_ratio",
]


def detect_language(text: str) -> str:
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    jp_chars = sum(1 for ch in text if _is_hiragana(ch) or _is_katakana(ch) or _is_kanji(ch))
    if jp_chars > ascii_chars * 1.2:
        return "ja"
    if ascii_chars > jp_chars * 1.2:
        return "en"
    return "mixed"


def extract_features(text: str) -> dict[str, float]:
    if not text:
        return {key: 0.0 for key in FEATURE_KEYS}

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        lines = [text]
    sentences = [s for s in re.split(r"[.!?。！？\n]+", text) if s.strip()]

    char_count = float(len(text))
    line_count = float(len(lines))
    sentence_count = float(max(1, len(sentences)))

    counts = Counter(text)

    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    hira = sum(1 for ch in text if _is_hiragana(ch))
    kata = sum(1 for ch in text if _is_katakana(ch))
    kanji = sum(1 for ch in text if _is_kanji(ch))
    emojis = sum(1 for ch in text if _is_emoji(ch))

    return {
        "char_count": char_count,
        "line_count": line_count,
        "avg_line_chars": char_count / max(1.0, line_count),
        "sentence_count": sentence_count,
        "avg_sentence_chars": char_count / sentence_count,
        "question_count": float(counts["?"] + counts["？"]),
        "exclaim_count": float(counts["!"] + counts["！"]),
        "ellipsis_count": float(text.count("...") + text.count("…")),
        "colon_count": float(counts[":"] + counts["："]),
        "semicolon_count": float(counts[";"] + counts["；"]),
        "comma_count": float(counts[","] + counts["、"] + counts["，"]),
        "dash_count": float(text.count("-") + text.count("—") + text.count("–")),
        "paren_count": float(text.count("(") + text.count(")") + text.count("（") + text.count("）")),
        "quote_count": float(text.count('"') + text.count("“") + text.count("”") + text.count("「") + text.count("」")),
        "hashtag_count": float(text.count("#")),
        "mention_count": float(text.count("@")),
        "url_count": float(text.count("http://") + text.count("https://")),
        "emoji_count": float(emojis),
        "ascii_ratio": ascii_chars / char_count,
        "hiragana_ratio": hira / char_count,
        "katakana_ratio": kata / char_count,
        "kanji_ratio": kanji / char_count,
        "newline_ratio": text.count("\n") / char_count,
    }


def build_style_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_platform: dict[str, list[dict[str, float]]] = {}
    for platform in {"x", "slack"}:
        texts = [row["reference_text"] for row in rows if row["platform"] == platform]
        if texts:
            by_platform[platform] = [extract_features(text) for text in texts]

    global_texts = [row["reference_text"] for row in rows]
    global_features = [extract_features(text) for text in global_texts]

    return {
        "global": _aggregate(global_features),
        "platforms": {platform: _aggregate(features) for platform, features in by_platform.items()},
    }


def profile_similarity(text: str, profile: dict[str, Any], platform: str) -> float:
    target = profile["platforms"].get(platform) or profile["global"]
    features = extract_features(text)

    scores: list[float] = []
    for key in FEATURE_KEYS:
        mean_value = float(target["mean"].get(key, 0.0))
        std_value = max(float(target["std"].get(key, 1.0)), _std_floor(key))
        z = abs(features[key] - mean_value) / std_value
        scores.append(math.exp(-0.45 * min(z, 8.0)))
    return clamp(mean(scores), 0.0, 1.0)


def reference_similarity(text: str, reference_text: str) -> float:
    a = extract_features(text)
    b = extract_features(reference_text)
    scores: list[float] = []

    for key in FEATURE_KEYS:
        baseline = max(abs(b[key]) * 0.35, _std_floor(key))
        scores.append(exp_similarity(a[key] - b[key], baseline))
    return clamp(mean(scores), 0.0, 1.0)


def copy_penalty(text: str, references: list[str]) -> float:
    if not text or not references:
        return 0.0
    ratios = [difflib.SequenceMatcher(a=text, b=ref).ratio() for ref in references]
    return clamp(max(ratios), 0.0, 1.0)


def topic_overlap_score(topic: str, text: str) -> float:
    topic_tokens = _coarse_tokens(topic)
    text_tokens = set(_coarse_tokens(text))
    if not topic_tokens:
        return 0.5
    hit = sum(1 for token in topic_tokens if token in text_tokens)
    return clamp(hit / max(1, len(topic_tokens)), 0.0, 1.0)


def platform_fit_score(platform: str, text: str, target_length: int) -> float:
    length_score = exp_similarity(len(text) - target_length, max(20, target_length * 0.45))
    line_score = 1.0
    if platform == "x":
        line_score = 1.0 if text.count("\n") <= 2 else 0.7
    elif platform == "slack":
        line_score = 1.0 if text.count("\n") <= 4 else 0.7
    return clamp(0.8 * length_score + 0.2 * line_score, 0.0, 1.0)


def local_style_bundle(
    generated_text: str,
    reference_text: str,
    all_references: list[str],
    profile: dict[str, Any],
    platform: str,
    topic: str,
    target_length: int,
) -> dict[str, float]:
    prof = profile_similarity(generated_text, profile, platform)
    ref = reference_similarity(generated_text, reference_text)
    copy = copy_penalty(generated_text, all_references)
    topic_score = topic_overlap_score(topic, generated_text)
    platform_score = platform_fit_score(platform, generated_text, target_length)
    length_score = exp_similarity(len(generated_text) - target_length, max(20, target_length * 0.45))

    return {
        "profile_similarity": prof,
        "reference_similarity": ref,
        "copy_penalty": copy,
        "topic_overlap": topic_score,
        "platform_fit": platform_score,
        "length_score": clamp(length_score, 0.0, 1.0),
    }


def _aggregate(feature_dicts: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    if not feature_dicts:
        return {
            "mean": {key: 0.0 for key in FEATURE_KEYS},
            "std": {key: _std_floor(key) for key in FEATURE_KEYS},
        }

    mean_map: dict[str, float] = {}
    std_map: dict[str, float] = {}
    for key in FEATURE_KEYS:
        values = [f[key] for f in feature_dicts]
        m = mean(values)
        mean_map[key] = m
        variance = mean([(v - m) ** 2 for v in values])
        std_map[key] = max(math.sqrt(variance), _std_floor(key))
    return {"mean": mean_map, "std": std_map}


def _std_floor(key: str) -> float:
    if key.endswith("_ratio"):
        return 0.03
    if key in {"char_count", "avg_line_chars", "avg_sentence_chars"}:
        return 8.0
    return 1.0


def _coarse_tokens(text: str) -> list[str]:
    text = text.lower()
    pieces = re.findall(r"[a-z0-9_]{2,}|[\u3040-\u30ff\u3400-\u9fff]{2,}", text)
    seen = []
    used = set()
    for p in pieces:
        if p not in used:
            used.add(p)
            seen.append(p)
    return seen


def _is_hiragana(ch: str) -> bool:
    code = ord(ch)
    return 0x3040 <= code <= 0x309F


def _is_katakana(ch: str) -> bool:
    code = ord(ch)
    return 0x30A0 <= code <= 0x30FF


def _is_kanji(ch: str) -> bool:
    code = ord(ch)
    return (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF)


def _is_emoji(ch: str) -> bool:
    code = ord(ch)
    return (
        0x1F300 <= code <= 0x1FAFF
        or 0x2600 <= code <= 0x27BF
        or 0xFE00 <= code <= 0xFE0F
    )
