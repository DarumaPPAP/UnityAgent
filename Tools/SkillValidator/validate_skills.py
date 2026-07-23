#!/usr/bin/env python3
"""Validate UnityAgent SKILL.md structure without external dependencies.

Default mode treats structural problems as errors and authoring-quality gaps as
warnings so legacy skills can be improved incrementally. Use --strict to make
warnings fail the process.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
REQUIRED_QUALITY_SECTIONS = (
    "output contract",
    "checklist",
    "common mistakes",
)
MUTATING_TOOLS = {"Write", "Edit"}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class SkillDocument:
    path: Path
    folder_name: str
    name: str | None
    description: str | None
    allowed_tools: tuple[str, ...]
    body: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate .agents/skills/*/SKILL.md files."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat authoring-quality warnings as failures.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON.",
    )
    return parser.parse_args()


def discover_skill_files(root: Path) -> list[Path]:
    skills_root = root / ".agents" / "skills"
    if not skills_root.is_dir():
        return []
    return sorted(skills_root.glob("*/SKILL.md"))


def parse_frontmatter(lines: list[str]) -> tuple[dict[str, str], tuple[str, ...], int] | None:
    if not lines or lines[0].strip() != "---":
        return None

    try:
        end_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        return None

    scalars: dict[str, str] = {}
    allowed_tools: list[str] = []
    active_list: str | None = None

    for raw_line in lines[1:end_index]:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if not line.startswith((" ", "\t")) and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            active_list = key if value == "" else None
            if value:
                scalars[key] = value
            continue

        if active_list == "allowed-tools" and stripped.startswith("- "):
            allowed_tools.append(stripped[2:].strip().strip('"').strip("'"))

    return scalars, tuple(allowed_tools), end_index


def read_skill(path: Path) -> tuple[SkillDocument | None, list[Finding]]:
    findings: list[Finding] = []
    relative_path = path.as_posix()

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        findings.append(
            Finding("error", "SKILL001", relative_path, f"Cannot read UTF-8 text: {error}")
        )
        return None, findings

    lines = text.splitlines()
    parsed = parse_frontmatter(lines)
    if parsed is None:
        findings.append(
            Finding(
                "error",
                "SKILL002",
                relative_path,
                "Missing or unterminated YAML frontmatter.",
            )
        )
        return None, findings

    scalars, allowed_tools, frontmatter_end = parsed
    body = "\n".join(lines[frontmatter_end + 1 :]).strip()
    document = SkillDocument(
        path=path,
        folder_name=path.parent.name,
        name=scalars.get("name"),
        description=scalars.get("description"),
        allowed_tools=allowed_tools,
        body=body,
    )
    return document, findings


def validate_document(document: SkillDocument, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    relative_path = document.path.relative_to(root).as_posix()

    if not document.name:
        findings.append(
            Finding("error", "SKILL003", relative_path, "Frontmatter is missing 'name'.")
        )
    else:
        if document.name != document.folder_name:
            findings.append(
                Finding(
                    "error",
                    "SKILL004",
                    relative_path,
                    f"Skill name '{document.name}' does not match folder '{document.folder_name}'.",
                )
            )
        if not NAME_PATTERN.fullmatch(document.name):
            findings.append(
                Finding(
                    "error",
                    "SKILL005",
                    relative_path,
                    "Skill name must use kebab-case ASCII letters and digits.",
                )
            )

    if not document.description:
        findings.append(
            Finding(
                "error", "SKILL006", relative_path, "Frontmatter is missing 'description'."
            )
        )
    else:
        if not document.description.startswith("Use when "):
            findings.append(
                Finding(
                    "warning",
                    "SKILL101",
                    relative_path,
                    "Description should start with 'Use when ' and describe trigger conditions.",
                )
            )
        if len(document.description) < 80:
            findings.append(
                Finding(
                    "warning",
                    "SKILL102",
                    relative_path,
                    "Description is probably too short to distinguish adjacent Skills.",
                )
            )

    if not document.body:
        findings.append(
            Finding("error", "SKILL007", relative_path, "SKILL.md body is empty.")
        )
        return findings

    lowered_body = document.body.lower()
    for section in REQUIRED_QUALITY_SECTIONS:
        if section not in lowered_body:
            findings.append(
                Finding(
                    "warning",
                    "SKILL103",
                    relative_path,
                    f"Recommended section is missing: {section.title()}.",
                )
            )

    read_only_language = (
        "read-only" in lowered_body
        or "do not modify" in lowered_body
        or "without changing" in (document.description or "").lower()
        or "変更しない" in document.body
    )
    mutating_tools = sorted(MUTATING_TOOLS.intersection(document.allowed_tools))
    if read_only_language and mutating_tools:
        findings.append(
            Finding(
                "warning",
                "SKILL104",
                relative_path,
                f"Read-only language conflicts with mutating tools: {', '.join(mutating_tools)}.",
            )
        )

    findings.extend(validate_markdown_links(document, root))
    return findings


def validate_markdown_links(document: SkillDocument, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    relative_path = document.path.relative_to(root).as_posix()

    for raw_target in MARKDOWN_LINK_PATTERN.findall(document.body):
        target = raw_target.strip()
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue

        file_part = target.split("#", 1)[0]
        if not file_part:
            continue

        candidate = (document.path.parent / file_part).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            findings.append(
                Finding(
                    "error",
                    "SKILL008",
                    relative_path,
                    f"Markdown link escapes repository root: {target}",
                )
            )
            continue

        if not candidate.exists():
            findings.append(
                Finding(
                    "error",
                    "SKILL009",
                    relative_path,
                    f"Broken relative Markdown link: {target}",
                )
            )

    return findings


def validate_duplicates(documents: Iterable[SkillDocument], root: Path) -> list[Finding]:
    by_name: dict[str, list[SkillDocument]] = {}
    for document in documents:
        if document.name:
            by_name.setdefault(document.name, []).append(document)

    findings: list[Finding] = []
    for name, matches in by_name.items():
        if len(matches) < 2:
            continue
        locations = ", ".join(
            match.path.relative_to(root).as_posix() for match in matches
        )
        findings.append(
            Finding(
                "error",
                "SKILL010",
                locations,
                f"Duplicate Skill name '{name}'.",
            )
        )
    return findings


def render_text(findings: list[Finding], skill_count: int, strict: bool) -> None:
    for finding in findings:
        print(
            f"[{finding.severity.upper()}] {finding.code} "
            f"{finding.path}: {finding.message}"
        )

    errors = sum(finding.severity == "error" for finding in findings)
    warnings = sum(finding.severity == "warning" for finding in findings)
    mode = "strict" if strict else "advisory"
    print(
        f"Validated {skill_count} Skills: {errors} error(s), "
        f"{warnings} warning(s), mode={mode}."
    )


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    skill_files = discover_skill_files(root)

    findings: list[Finding] = []
    documents: list[SkillDocument] = []

    if not skill_files:
        findings.append(
            Finding(
                "error",
                "SKILL000",
                str(root),
                "No .agents/skills/*/SKILL.md files were found.",
            )
        )

    for skill_file in skill_files:
        document, read_findings = read_skill(skill_file)
        findings.extend(read_findings)
        if document is None:
            continue
        documents.append(document)
        findings.extend(validate_document(document, root))

    findings.extend(validate_duplicates(documents, root))
    findings.sort(key=lambda item: (item.severity != "error", item.path, item.code))

    errors = sum(finding.severity == "error" for finding in findings)
    warnings = sum(finding.severity == "warning" for finding in findings)

    if args.json_output:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "skill_count": len(documents),
                    "strict": args.strict,
                    "errors": errors,
                    "warnings": warnings,
                    "findings": [asdict(finding) for finding in findings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        render_text(findings, len(documents), args.strict)

    if errors > 0:
        return 1
    if args.strict and warnings > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
