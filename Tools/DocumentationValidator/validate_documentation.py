#!/usr/bin/env python3
"""Validate active UnityAgent documentation against canonical repository paths."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ACTIVE_DOC_PATHS = (
    Path("README.md"),
    Path("docs/architecture"),
    Path("docs/graph-observatory-spec.md"),
    Path("Specs"),
    Path("SkillReferences"),
    Path("Tools/GraphObservatory"),
    Path("Tests/SkillRouting/README.md"),
    Path("Tests/GraphObservatory/README.md"),
)

README_GLOB = "README.md"

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
)

HISTORICAL_LINE_MARKERS = (
    "legacy", "historical", "migration", "deleted", "removed", "forbidden",
    "do not use", "not use", "旧", "削除", "廃止", "禁止", "復活させ",
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


def main() -> int:
    errors: list[str] = []
    docs = list(_iter_docs())
    if not docs:
        errors.append("no active documentation files discovered")

    _validate_readme_stability(errors)

    for path in docs:
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")

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
