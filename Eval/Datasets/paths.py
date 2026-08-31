"""Canonical Eval dataset locations and legacy-path projection helpers."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BEHAVIOR_ROOT = ROOT / "Eval" / "Datasets" / "Behavior"
GOLDEN_ROOT = ROOT / "Eval" / "Datasets" / "Golden"

LEGACY_PREFIXES = {
    "Tests/BehaviorEval": "Eval/Datasets/Behavior",
    "Tests/GoldenTasks": "Eval/Datasets/Golden",
}


def canonicalize_repo_path(value: str) -> str:
    text = str(value or "").replace("\\", "/")
    for legacy, canonical in LEGACY_PREFIXES.items():
        if text == legacy or text.startswith(legacy + "/"):
            return canonical + text[len(legacy):]
    return text


def canonicalize_document(value: Any) -> Any:
    """Return a deep canonical-path projection without mutating the source dataset."""
    if isinstance(value, dict):
        return {key: canonicalize_document(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonicalize_document(item) for item in value]
    if isinstance(value, str):
        return canonicalize_repo_path(value)
    return deepcopy(value)


def legacy_fixture_shadow(value: str) -> str:
    """Map canonical fixture path to the legacy compatibility copy for old validators only."""
    text = str(value or "").replace("\\", "/")
    reverse = {canonical: legacy for legacy, canonical in LEGACY_PREFIXES.items()}
    for canonical, legacy in reverse.items():
        if text == canonical or text.startswith(canonical + "/"):
            return legacy + text[len(canonical):]
    return text
