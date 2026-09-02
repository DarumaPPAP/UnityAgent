#!/usr/bin/env python3
"""Validate active UnityAgent documentation against canonical repository paths/contracts."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ACTIVE_DOC_PATHS = (
    Path("AGENTS.md"),
    Path("README.md"),
    Path("docs/architecture"),
    Path("docs/graph-observatory-spec.md"),
    Path("docs/local-project-development.md"),
    Path("docs/unity-environment-adaptation.md"),
    Path("Templates/DevelopmentRequest.md"),
    Path("Specs"),
    Path("SkillReferences"),
    Path("Tools/GraphObservatory"),
    Path("Tests/SkillRouting/README.md"),
    Path("Tests/GraphObservatory/README.md"),
)

README_GLOB = "README.md"
MIGRATION_DIR = ROOT / "docs/migration"
PHASE_NAMED_MIGRATION = re.compile(r"^phase\d+(?:[-_.]|$)", re.IGNORECASE)
PHASE_NAMED_MIGRATION_TITLE = re.compile(r"^#\s+phase\s*\d+\b", re.IGNORECASE)

EXCLUDED_PREFIXES = (Path("docs/migration"),)

LEGACY_PATH_MARKERS = (
    ".ai/",
    "Eval/ProductionSmoke",
    "Eval/Graders",
    "Tools/BehaviorEval/",
    "Tools/GoldenEval/",
    "Tools/LoopIntegration/",
    "Tools/ContextManifest/",
    "Tools/ContextBudget/",
    "Tools/ContextCatalog/",
    "Tools/Phase10/",
    "Tests/ContextManifest/",
    "Tests/ContextCatalog/",
    "docs/phase8-graph-observatory-spec.md",
    "Context/Compatibility",
    "Eval/Compatibility",
    "Persistence/Compatibility",
    "Context/Selection/mcp-selection.yaml",
)

HISTORICAL_LINE_MARKERS = (
    "legacy", "historical", "migration", "deleted", "removed", "forbidden",
    "do not use", "not use", "regression", "old ", "旧", "削除", "廃止", "禁止",
    "復活", "戻さ", "当時", "過去", "ではありません", "使用しない", "×",
)

# These names existed in pre-cutover human-facing material but are not members of
# the canonical 15 CapabilityRequest vocabulary. A fenced migration table may
# mention them only when the immediately preceding prose explicitly states that
# those names are non-canonical.
STALE_CAPABILITY_NAMES = (
    "source.inspect",
    "project.compile",
    "editor.observe",
    "editor.capture",
    "performance.capture",
    "player.control",
)

STALE_RUNTIME_POSITION_PATTERNS = (
    re.compile(r"Capability-driven[^\n]*Target Architecture", re.IGNORECASE),
    re.compile(r"Unity Tool Runtime[^\n]*Target Architecture", re.IGNORECASE),
    re.compile(r"Tool Broker[^\n]*Production実装へ昇格する前", re.IGNORECASE),
)

README_DYNAMIC_STATE_PATTERNS = (
    (re.compile(r"\bphase\s*\d+\b", re.IGNORECASE), "development phase number"),
    (re.compile(r"フェーズ\s*\d+"), "development phase number"),
    (re.compile(r"現在地点"), "current development status"),
    (re.compile(r"品質基盤\s*v\d+", re.IGNORECASE), "versioned completion status"),
    (re.compile(r"\bphase\d+-baseline[-\w.]*", re.IGNORECASE), "specific baseline id"),
    (re.compile(r"\bgpt-\d[\w.-]*", re.IGNORECASE), "specific model version"),
)

REQUIRED_USER_ENTRYPOINTS = (
    Path("Tools/validate_all.py"),
    Path("Tools/run_regression_gate.py"),
    Path("Tools/ProductionToolRuntime/validate_production_tool_runtime.py"),
)

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _is_excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return any(relative == prefix or prefix in relative.parents for prefix in EXCLUDED_PREFIXES)


def _iter_docs():
    seen: set[Path] = set()
    explicit_candidates: list[Path] = []
    for relative in ACTIVE_DOC_PATHS:
        path = ROOT / relative
        if path.is_file():
            explicit_candidates.append(path)
        elif path.is_dir():
            explicit_candidates.extend(sorted(path.rglob("*.md")))

    candidates = [*explicit_candidates, *sorted(ROOT.rglob(README_GLOB))]
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen or _is_excluded(candidate):
            continue
        seen.add(candidate)
        yield candidate


def _resolve_link(source: Path, target: str) -> Path | None:
    raw = target.strip()
    if not raw or raw.startswith(("#", "http://", "https://", "mailto:")):
        return None
    file_part = raw.split("#", 1)[0].strip()
    if not file_part or "<" in file_part or ">" in file_part:
        return None
    if file_part.startswith("/"):
        return (ROOT / file_part.lstrip("/")).resolve()
    return (source.parent / file_part).resolve()


def _legacy_reference_is_historical(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in HISTORICAL_LINE_MARKERS)


def _validate_readme_stability(errors: list[str]) -> None:
    readme = ROOT / "README.md"
    if not readme.is_file():
        errors.append("README.md is missing")
        return

    text = readme.read_text(encoding="utf-8")
    for pattern, description in README_DYNAMIC_STATE_PATTERNS:
        match = pattern.search(text)
        if match:
            errors.append(f"README must not hard-code {description}: {match.group(0)!r}")

    for entrypoint in REQUIRED_USER_ENTRYPOINTS:
        if not (ROOT / entrypoint).is_file():
            errors.append(f"README user entry point is missing: {entrypoint.as_posix()}")


def _validate_migration_naming(errors: list[str]) -> None:
    if not MIGRATION_DIR.is_dir():
        return

    for path in sorted(MIGRATION_DIR.rglob("*")):
        if not path.is_file():
            continue

        relative = path.relative_to(ROOT).as_posix()
        if PHASE_NAMED_MIGRATION.match(path.name):
            errors.append(
                f"migration document must use a semantic filename instead of a development phase number: {relative}"
            )

        if path.suffix.lower() == ".md":
            lines = path.read_text(encoding="utf-8").splitlines()
            first_nonempty = next((line.strip() for line in lines if line.strip()), "")
            if PHASE_NAMED_MIGRATION_TITLE.match(first_nonempty):
                errors.append(
                    f"migration document must use a semantic H1 title instead of a development phase number: {relative}"
                )


def _validate_production_runtime_terms(path: Path, text: str, errors: list[str]) -> None:
    relative = path.relative_to(ROOT).as_posix()
    allow_next_migration_fence = False
    migration_fence = False
    in_fence = False

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        lowered = line.lower()

        if "canonical capabilityではありません" in lowered or "non-canonical capability" in lowered:
            allow_next_migration_fence = True

        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                migration_fence = allow_next_migration_fence
                allow_next_migration_fence = False
            else:
                in_fence = False
                migration_fence = False
            continue

        for name in STALE_CAPABILITY_NAMES:
            if name not in lowered:
                continue
            if _legacy_reference_is_historical(line):
                continue
            if migration_fence and "->" in line:
                continue
            errors.append(
                f"stale non-canonical Capability name {name}: {relative}:{line_number}"
            )

    for pattern in STALE_RUNTIME_POSITION_PATTERNS:
        match = pattern.search(text)
        if match:
            errors.append(
                f"active documentation still describes Production Tool Runtime as a future Target Architecture: "
                f"{relative}: {match.group(0)!r}"
            )


def main() -> int:
    errors: list[str] = []
    docs = list(_iter_docs())
    if not docs:
        errors.append("no active documentation files discovered")

    _validate_readme_stability(errors)
    _validate_migration_naming(errors)

    for path in docs:
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        _validate_production_runtime_terms(path, text, errors)

        for line_number, line in enumerate(text.splitlines(), start=1):
            for marker in LEGACY_PATH_MARKERS:
                if marker in line and not _legacy_reference_is_historical(line):
                    errors.append(f"active legacy path reference {marker}: {relative}:{line_number}")

        for target in MARKDOWN_LINK.findall(text):
            resolved = _resolve_link(path, target)
            if resolved is None:
                continue
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                errors.append(f"markdown link escapes repository: {relative} -> {target}")
                continue
            if not resolved.exists():
                errors.append(f"broken markdown link: {relative} -> {target}")

    if errors:
        print("Active documentation validation failed:")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1

    print(f"Active documentation validation passed: {len(docs)} Markdown files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
