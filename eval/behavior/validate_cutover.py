#!/usr/bin/env python3
"""Fail closed unless active UnityAgent surfaces use canonical repository ownership."""
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
    "src/unityagent/context/compatibility",
    "eval/compatibility",
    "src/unityagent/persistence/compatibility",
    "tools/BehaviorEval",
    "tools/GoldenEval",
    "tools/LoopIntegration",
    "tools/ContextManifest",
    "tools/ContextBudget",
    "tools/ContextCatalog",
    "tools/GraphContractValidator",
    "tools/TaskFingerprintValidator",
    "tools/Phase10",
    "tests/behavior_eval",
    "tests/golden_tasks",
    "tests/loop_integration",
    "tests/context_manifest",
    "tests/context_catalog",
    "tests/context_routing",
)

ACTIVE_SCAN_ROOTS = (
    "README.md",
    "AGENTS.md",
    ".agents",
    "src/unityagent/policy",
    "src/unityagent/context",
    "src/unityagent/orchestration",
    "src/unityagent/runtime",
    "src/unityagent/persistence",
    "src/unityagent/operations",
    "eval",
    ".github/workflows",
    "tools",
)

REFERENCE_ONLY_PREFIXES = (
    "eval/datasets/",
    "eval/replay/",
)
REFERENCE_DEFINITION_FILES = {
    "tools/documentation_validator/validate_documentation.py",
}
PHASE_PATH_EXEMPT_PREFIXES = (
    "eval/rebaseline/baselines/",
)

TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".md", ".json"}
COMPAT_IMPORT_RE = re.compile(r"(?m)^\s*(?:from|import)\s+(?:Context|Eval|src/unityagent/persistence)\.Compatibility\b")
PHASE_PATH_RE = re.compile(r"(?i)(?:^|/)[^/]*phase\d+[^/]*(?:/|$)")


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

        if not relative.startswith(PHASE_PATH_EXEMPT_PREFIXES) and PHASE_PATH_RE.search(relative):
            errors.append(f"active path must use responsibility-based naming instead of development phase: {relative}")

        if relative.startswith(REFERENCE_ONLY_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8")

        if relative not in REFERENCE_DEFINITION_FILES:
            if LEGACY_MARKER in text:
                errors.append(f"active legacy path reference: {relative}")
            if COMPATIBILITY_URI in text:
                errors.append(f"active compatibility URI reference: {relative}")
            if COMPAT_IMPORT_RE.search(text):
                errors.append(f"active compatibility import: {relative}")

            for obsolete in (
                "tools/BehaviorEval/",
                "tools/GoldenEval/",
                "tools/LoopIntegration/",
                "tools/ContextManifest/",
                "tools/ContextBudget/",
                "tools/ContextCatalog/",
                "tools/GraphContractValidator/",
                "tools/TaskFingerprintValidator/",
                "tools/Phase10/",
                "tests/context_routing/",
            ):
                if obsolete in text:
                    errors.append(f"active obsolete path reference {obsolete}: {relative}")

        if relative.startswith(".github/workflows/") and EXTERNAL_GRAPH_REPOSITORY in text:
            errors.append(f"workflow still depends on Unity-Graph-Engineering: {relative}")

    if errors:
        print("Canonical repository cutover validation failed:")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1

    print("Canonical repository cutover validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
