#!/usr/bin/env python3
"""Fail closed unless active UnityAgent surfaces are fully cut over to canonical ownership."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()

LEGACY_ROOT = "." + "ai"
LEGACY_MARKER = LEGACY_ROOT + "/"
COMPATIBILITY_URI = "compatibility" + "://"
EXTERNAL_GRAPH_REPOSITORY = "DarumaPPAP/" + "Unity-Graph-Engineering"

FORBIDDEN_PATHS = (
    LEGACY_ROOT,
    "Context/Compatibility",
    "Eval/Compatibility",
    "Persistence/Compatibility",
    "Tools/BehaviorEval",
    "Tools/GoldenEval",
    "Tools/LoopIntegration",
    "Tests/BehaviorEval",
    "Tests/GoldenTasks",
    "Tests/LoopIntegration",
)

ACTIVE_SCAN_ROOTS = (
    "AGENTS.md",
    ".agents",
    "Policy",
    "Context",
    "Orchestration",
    "Runtime",
    "Persistence",
    "Operations",
    "Eval",
    ".github/workflows",
    "Tools/validate_all.py",
)

REFERENCE_ONLY_PREFIXES = (
    "Eval/Datasets/",
    "Eval/Replay/",
)

TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".md", ".json"}
COMPAT_IMPORT_RE = re.compile(r"(?m)^\s*(?:from|import)\s+(?:Context|Eval|Persistence)\.Compatibility\b")


def iter_active_files():
    for item in ACTIVE_SCAN_ROOTS:
        path = ROOT / item
        if path.is_file():
            yield path
            continue
        if not path.is_dir():
            continue
        for candidate in path.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in TEXT_SUFFIXES:
                yield candidate


def main() -> int:
    errors: list[str] = []

    for relative in FORBIDDEN_PATHS:
        if (ROOT / relative).exists():
            errors.append(f"forbidden post-cutover path still exists: {relative}")

    for path in iter_active_files():
        if path.resolve() == SELF:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(REFERENCE_ONLY_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8")

        if LEGACY_MARKER in text:
            errors.append(f"active legacy path reference: {relative}")
        if COMPATIBILITY_URI in text:
            errors.append(f"active compatibility URI reference: {relative}")
        if COMPAT_IMPORT_RE.search(text):
            errors.append(f"active compatibility import: {relative}")

        if relative.startswith(".github/workflows/") and EXTERNAL_GRAPH_REPOSITORY in text:
            errors.append(f"workflow still depends on Unity-Graph-Engineering: {relative}")

        for obsolete in ("Tools/BehaviorEval/", "Tools/GoldenEval/", "Tools/LoopIntegration/"):
            if obsolete in text:
                errors.append(f"active obsolete tool reference {obsolete}: {relative}")

    if errors:
        print("Phase 8 single-repo cutover validation failed:")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1

    print("Phase 8 single-repo cutover validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
