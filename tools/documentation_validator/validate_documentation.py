#!/usr/bin/env python3
"""Validate active UnityAgent documentation against canonical repository paths/contracts."""
from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import re
import sys
import unicodedata
import yaml
from urllib.parse import unquote, urlsplit
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ACTIVE_DOC_PATHS = (
    Path("AGENTS.md"),
    Path("README.md"),
    Path("docs/README.md"),
    Path("docs/development"),
    Path("docs/getting-started"),
    Path("docs/guides"),
    Path("docs/concepts"),
    Path("docs/references"),
    Path("docs/architecture"),
    Path("docs/context-explorer.md"),
    Path("docs/local-project-development.md"),
    Path("docs/unity-environment-adaptation.md"),
    Path("docs/templates/DevelopmentRequest.md"),
    Path("docs/architecture/specifications"),
    Path("docs/standards"),
    Path("tools/context_explorer"),
    Path("tests/skill_routing/README.md"),
    Path("tests/context_explorer/README.md"),
)

README_GLOB = "README.md"
MIGRATION_DIR = ROOT / "docs/migration"
PHASE_NAMED_MIGRATION = re.compile(r"^phase\d+(?:[-_.]|$)", re.IGNORECASE)
PHASE_NAMED_MIGRATION_TITLE = re.compile(r"^#\s+phase\s*\d+\b", re.IGNORECASE)

# UPM内包のP9 Source Mirrorは実行Inputであり、アクティブなMarkdown文書ではない。
# Mirror内READMEの相対リンクはcanonical repositoryでのみ解決される。
EXCLUDED_PREFIXES = (
    Path("docs/migration"),
    Path("docs/development/plans"),
    Path("docs/development/unity-setup.md"),
    Path("src/unityagent/_resources"),
    Path("build"),
    Path("dist"),
    Path("Artifacts"),
    Path("artifacts"),
    Path("_site"),
    Path(".venv"),
    Path("venv"),
    Path(".git"),
    Path("Packages/com.darumappap.unity-agent/Editor/Verification~"),
)

LEGACY_PATH_MARKERS = (
    ".ai/",
    "eval/production_smoke",
    "eval/graders",
    "tools/BehaviorEval/",
    "tools/GoldenEval/",
    "tools/LoopIntegration/",
    "tools/ContextManifest/",
    "tools/ContextBudget/",
    "tools/ContextCatalog/",
    "tools/Phase10/",
    "tests/context_manifest/",
    "tests/context_catalog/",
    "docs/phase8-graph-observatory-spec.md",
    "src/unityagent/context/compatibility",
    "eval/compatibility",
    "src/unityagent/persistence/compatibility",
    "src/unityagent/context/selection/mcp-selection.yaml",
)

HISTORICAL_LINE_MARKERS = (
    "legacy", "historical", "migration", "deleted", "removed", "forbidden",
    "do not use", "not use", "regression", "old ", "旧", "削除", "廃止", "禁止",
    "復活", "戻さ", "当時", "過去", "ではありません", "使用しない", "×",
)

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
    Path("tools/validate_all.py"),
    Path("tools/run_regression_gate.py"),
    Path("tools/production_tool_runtime/validate_production_tool_runtime.py"),
)

USER_GUIDES = (
    Path("docs/getting-started/installation.md"),
    Path("docs/getting-started/first-task.md"),
    Path("docs/guides/subagents.md"),
    Path("docs/references/capability-status.md"),
)
STATUS_COLUMNS = ("機能ID／機能名", "利用条件", "実装状態", "検証状態", "制限", "根拠", "対象Revision")
CAPABILITY_SCHEMA = Path("src/unityagent/runtime/contracts/capability-request.schema.yaml")
REVISION_URL = re.compile(r"https://github\.com/DarumaPPAP/UnityAgent/commit/[0-9a-f]{40}")
REFERENCE_DEFINITION = re.compile(
    r'^ {0,3}\[([^]\n]+)\]:[ \t]*(<[^>\n]+>|[^\s]+)(?:[ \t]+.*)?$', re.MULTILINE
)


def _is_excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return (any(relative == prefix or prefix in relative.parents for prefix in EXCLUDED_PREFIXES)
            or "node_modules" in relative.parts or "__pycache__" in relative.parts)


def _iter_docs():
    seen: set[Path] = set()
    candidates: list[Path] = []
    for relative in ACTIVE_DOC_PATHS:
        path = ROOT / relative
        if path.is_file():
            candidates.append(path)
        elif path.is_dir():
            candidates.extend(sorted(path.rglob("*.md")))
    candidates.extend(sorted(ROOT.rglob(README_GLOB)))
    for candidate in candidates:
        if candidate in seen or _is_excluded(candidate):
            continue
        seen.add(candidate)
        yield candidate


def _without_code_blocks(text: str) -> str:
    # 行数を維持し、説明用コードをリンクや見出しとして解釈しない。
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if re.match(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$", line):
                fence = None
            lines.append("")
        elif match:
            fence = match.group(1)
            lines.append("")
        else:
            lines.append(line)
    return re.sub(r"<!--.*?-->", "", "\n".join(lines), flags=re.DOTALL)


def _reference_key(label: str) -> str:
    return " ".join(label.split()).casefold()


def _references(text: str) -> dict[str, str]:
    return {_reference_key(m[1]): m[2].strip("<>") for m in REFERENCE_DEFINITION.finditer(text)}


class _HTMLReferences(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.anchors: set[str] = set()
        self.code_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"pre", "code"}:
            self.code_depth += 1
        if self.code_depth:
            return
        for key, value in attrs:
            if value is not None and key in {"href", "src"}:
                self.links.append(value)
            if value is not None and (key == "id" or (tag == "a" and key == "name")):
                self.anchors.add(value)

    def handle_endtag(self, tag):
        if tag in {"pre", "code"} and self.code_depth:
            self.code_depth -= 1


def _inline_destination(text: str, start: int) -> str | None:
    rest = text[start:].lstrip()
    if rest.startswith("<"):
        end = rest.find(">")
        return rest[1:end] if end >= 0 else None
    depth = 0
    chars = []
    escaped = False
    for char in rest:
        if escaped:
            chars.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if (char == ")" and depth == 0) or (char.isspace() and depth == 0):
            break
        depth += (char == "(") - (char == ")")
        chars.append(char)
    return "".join(chars) or None


def _links(text: str, references: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    text = _without_code_blocks(text)
    # HTMLの属性内にあるバッククォートを壊さないようタグは先に取得する。
    html = _HTMLReferences()
    html.feed(re.sub(r"(`+).*?\1", "", text, flags=re.DOTALL))
    refs = {**(references or {}), **_references(text)}
    text = REFERENCE_DEFINITION.sub("", text)
    text = re.sub(r"(`+).*?\1", "", text, flags=re.DOTALL)
    targets = list(html.links)
    missing = []
    # 画像を包むリンクの外側も検査するため、ラベルの角括弧を対応付ける。
    brackets: list[int] = []
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == "[":
            brackets.append(index)
        elif char == "]" and brackets:
            brackets.pop()
            if text[index + 1:index + 2] == "(":
                destination = _inline_destination(text, index + 2)
                if destination:
                    targets.append(unescape(destination))
    for match in re.finditer(r"!?\[([^]\n]*)\]\[([^]\n]*)\]", text):
        key = _reference_key(match[2] or match[1])
        if key in refs:
            targets.append(refs[key])
        else:
            missing.append(key)
    for match in re.finditer(r"\[([^]\n]+)\](?![([])", text):
        key = _reference_key(match[1])
        if key in refs:
            targets.append(refs[key])
    return targets, missing


def _anchors(text: str) -> set[str]:
    text = _without_code_blocks(text)
    html = _HTMLReferences()
    html.feed(text)
    anchors = set(html.anchors)
    generated: set[str] = set()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            heading = match[1]
        elif (line.strip() and index + 1 < len(lines)
              and re.fullmatch(r" {0,3}(?:=+|-+)\s*", lines[index + 1])):
            heading = line.strip()
        else:
            continue
        heading = re.sub(r"!?\[([^]]+)\]\([^)]*\)", r"\1", heading)
        heading = re.sub(r"<[^>]*>", "", heading)
        heading = re.sub(r"(`+)(.*?)\1", r"\2", heading)
        heading = re.sub(r"(?<!\w)([*_~]+)(.+?)\1(?!\w)", r"\2", heading)
        heading = unescape(heading).lower()
        base = "".join(c for c in heading if c in "-_ " or unicodedata.category(c)[0] in "LMN").replace(" ", "-")
        slug = base
        suffix = 0
        while slug in generated:
            suffix += 1
            slug = f"{base}-{suffix}"
        generated.add(slug)
        anchors.add(slug)
    return anchors


def _resolve_link(source: Path, target: str) -> Path | None:
    parsed = urlsplit(target.strip())
    if parsed.scheme or parsed.netloc:
        return None
    file_part = unquote(parsed.path)
    if not file_part:
        return source.resolve()
    if file_part.startswith("/"):
        return (ROOT / file_part.lstrip("/")).resolve()
    return (source.parent / file_part).resolve()


def _validate_links(path: Path, text: str, errors: list[str]) -> None:
    relative = path.relative_to(ROOT).as_posix()
    targets, missing = _links(text)
    for label in missing:
        errors.append(f"undefined markdown reference: {relative} -> {label}")
    for target in targets:
        try:
            resolved = _resolve_link(path, target)
            if resolved is None:
                continue
            resolved.relative_to(ROOT)
        except ValueError:
            errors.append(f"local reference escapes repository or has invalid URL: {relative} -> {target}")
            continue
        if not resolved.exists():
            errors.append(f"broken local reference: {relative} -> {target}")
            continue
        fragment = unquote(urlsplit(target).fragment)
        if fragment and resolved.is_file() and resolved.suffix.lower() == ".md":
            if fragment not in _anchors(resolved.read_text(encoding="utf-8")):
                errors.append(f"broken markdown anchor: {relative} -> {target}")


def _validate_navigation(errors: list[str]) -> None:
    # 提案段階のファイルを必須化せず、追加された案内だけを到達性の対象にする。
    pending = [ROOT / "README.md"]
    reached: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in reached or not path.is_file():
            continue
        reached.add(path)
        targets, _ = _links(path.read_text(encoding="utf-8"))
        for target in targets:
            try:
                resolved = _resolve_link(path, target)
                if resolved is None:
                    continue
                resolved.relative_to(ROOT)
            except ValueError:
                continue
            if resolved.suffix.lower() == ".md" and resolved not in reached and not _is_excluded(resolved):
                pending.append(resolved)
    for relative in USER_GUIDES:
        if (ROOT / relative).is_file() and (ROOT / relative).resolve() not in reached:
            errors.append(f"user guide not reachable from README: {relative.as_posix()}")


def _validate_capability_status(errors: list[str]) -> None:
    relative = Path("docs/references/capability-status.md")
    path = ROOT / relative
    if not path.is_file():
        return
    text = _without_code_blocks(path.read_text(encoding="utf-8"))
    references = _references(text)
    found = False
    rows = 0
    active = False
    tool_section = False
    tool_capabilities: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            tool_section = line.strip() == "## Tool Capability"
        if not line.strip().startswith("|"):
            if active and rows == 0:
                errors.append(f"empty status table: {relative}:{number}")
            active = False
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if cells[0] == STATUS_COLUMNS[0]:
            found = True
            active = True
            rows = 0
            if tuple(cells) != STATUS_COLUMNS:
                errors.append(f"required status columns are missing or reordered: {relative}:{number}")
            continue
        if not active or all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        rows += 1
        if len(cells) != len(STATUS_COLUMNS) or any(cell in {"", "-"} for cell in cells):
            errors.append(f"empty status field or malformed row: {relative}:{number}")
            continue
        if not _links(cells[5], references)[0]:
            errors.append(f"status evidence must contain a link: {relative}:{number}")
        if not any(REVISION_URL.fullmatch(link) for link in _links(cells[6], references)[0]):
            errors.append(f"status revision must link to a 40-character UnityAgent commit: {relative}:{number}")
        if tool_section:
            match = re.fullmatch(r"`([a-z][a-z0-9_.-]+)`", cells[0])
            if match is None:
                errors.append(f"invalid tool capability ID: {relative}:{number}")
            else:
                tool_capabilities.append(match[1])
    if active and rows == 0:
        errors.append(f"empty status table: {relative}")
    if not found:
        errors.append(f"required status columns are missing: {relative}")

    schema_path = ROOT / CAPABILITY_SCHEMA
    if schema_path.is_file():
        try:
            declared = yaml.safe_load(schema_path.read_text(encoding="utf-8"))["properties"]["capability"]["enum"]
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
            errors.append(f"invalid canonical capability schema: {CAPABILITY_SCHEMA}: {exc}")
            return
        if len(tool_capabilities) != len(set(tool_capabilities)):
            errors.append(f"duplicate tool capability in status matrix: {relative}")
        missing = sorted(set(declared) - set(tool_capabilities))
        extra = sorted(set(tool_capabilities) - set(declared))
        if missing or extra:
            errors.append(f"tool capability matrix differs from schema: missing={missing}, extra={extra}")


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
    _validate_navigation(errors)
    _validate_capability_status(errors)

    for path in docs:
        relative = path.relative_to(ROOT).as_posix()
        if not path.resolve().is_relative_to(ROOT):
            errors.append(f"documentation source escapes repository: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        _validate_production_runtime_terms(path, text, errors)

        for line_number, line in enumerate(text.splitlines(), start=1):
            for marker in LEGACY_PATH_MARKERS:
                if marker in line and not _legacy_reference_is_historical(line):
                    errors.append(f"active legacy path reference {marker}: {relative}:{line_number}")

        _validate_links(path, text, errors)

    if errors:
        print("Active documentation validation failed:")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1

    print(f"Active documentation validation passed: {len(docs)} Markdown files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
