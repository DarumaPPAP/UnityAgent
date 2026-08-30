#!/usr/bin/env python3
"""Validate active UnityAgent documentation against post-cutover repository paths."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ACTIVE_DOC_PATHS = (
    Path("README.md"),
    Path("docs/architecture"),
    Path("docs/phase8-graph-observatory-spec.md"),
    Path("Specs"),
    Path("SkillReferences"),
    Path("Tools/GraphObservatory"),
    Path("Tests/SkillRouting/README.md"),
    Path("Tests/GraphObservatory/README.md"),
)

# Historical migration documents intentionally retain legacy provenance and are
# therefore not part of this active-document authority scan.
EXCLUDED_PREFIXES = (Path("docs/migration"),)

LEGACY_PATH_MARKERS = (
    ".ai/",
    "Eval/ProductionSmoke",
    "Eval/Graders",
    "Tools/BehaviorEval/",
    "Tools/GoldenEval/",
    "Tools/LoopIntegration/",
    "Context/Compatibility",
    "Eval/Compatibility",
    "Persistence/Compatibility",
)

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _is_excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return any(relative == prefix or prefix in relative.parents for prefix in EXCLUDED_PREFIXES)


def _iter_docs():
    seen: set[Path] = set()
    for relative in ACTIVE_DOC_PATHS:
        path = ROOT / relative
        if path.is_file():
            candidates = (path,)
        elif path.is_dir():
            candidates = tuple(sorted(path.rglob("*.md")))
        else:
            continue
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


def main() -> int:
    errors: list[str] = []
    docs = list(_iter_docs())
    if not docs:
        errors.append("no active documentation files discovered")

    for path in docs:
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")

        for marker in LEGACY_PATH_MARKERS:
            if marker in text:
                errors.append(f"active legacy path reference {marker}: {relative}")

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
