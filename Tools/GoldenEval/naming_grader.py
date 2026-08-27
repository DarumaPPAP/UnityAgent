#!/usr/bin/env python3
"""Deterministic C# Type Naming grader for UnityAgent Golden Regression."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_ARTIFACT_ROOT = ROOT / "Artifacts" / "GoldenEval"

HARD_FINDING_CODES = {
    "NAME001_ROLE_SUFFIX_STACKING",
    "NAME002_VAGUE_TYPE_NAME",
    "NAME003_FORBIDDEN_IDENTIFIER",
    "NAME004_REQUIRED_IDENTIFIER_MISSING",
    "NAME005_UNEXPECTED_NEW_TYPE",
}

KNOWN_ABBREVIATIONS = {
    "UI",
    "GPU",
    "CPU",
    "LOD",
    "URP",
    "HDRP",
    "MCP",
    "RT",
    "API",
    "SDK",
}

ROLE_TOKENS = {
    "Analyzer",
    "Baker",
    "Binder",
    "Builder",
    "Collector",
    "Controller",
    "Debugger",
    "Driver",
    "Exporter",
    "Factory",
    "Guard",
    "History",
    "Importer",
    "Manager",
    "Pool",
    "Presenter",
    "Registry",
    "Renderer",
    "Resolver",
    "Router",
    "Scheduler",
    "Service",
    "Settings",
    "Snapshot",
    "State",
    "Store",
    "System",
    "Tracker",
    "Validator",
    "Watcher",
    "Window",
}

VAGUE_TOKENS = {
    "Helper",
    "Util",
    "Utility",
    "Common",
    "General",
    "Universal",
    "Advanced",
    "Flexible",
}

CONJUNCTION_TOKENS = {"And", "Or", "With", "Without", "From", "To"}

TYPE_DECLARATION_RE = re.compile(
    r"(?m)^\s*(?:(?:public|internal|private|protected|static|sealed|abstract|partial|readonly|ref|unsafe|new)\s+)*"
    r"(class|struct|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b"
)
BLOCK_NAMESPACE_RE = re.compile(r"\bnamespace\s+([A-Za-z_][A-Za-z0-9_.]*)\s*\{")
FILE_NAMESPACE_RE = re.compile(r"(?m)^\s*namespace\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;")
PASCAL_TOKEN_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+")


@dataclass(frozen=True)
class ArtifactEvidenceError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def _blank_preserving_newlines(text: str) -> str:
    return "".join("\n" if char == "\n" else " " for char in text)


def sanitize_csharp(source: str) -> str:
    """Remove comments and string/char literal contents while preserving line layout."""

    output: list[str] = []
    index = 0
    length = len(source)

    while index < length:
        char = source[index]
        next_char = source[index + 1] if index + 1 < length else ""

        if char == "/" and next_char == "/":
            end = source.find("\n", index + 2)
            if end == -1:
                output.append(_blank_preserving_newlines(source[index:]))
                break
            output.append(_blank_preserving_newlines(source[index:end]))
            index = end
            continue

        if char == "/" and next_char == "*":
            end = source.find("*/", index + 2)
            if end == -1:
                output.append(_blank_preserving_newlines(source[index:]))
                break
            end += 2
            output.append(_blank_preserving_newlines(source[index:end]))
            index = end
            continue

        prefix_length = 0
        verbatim = False
        if source.startswith("$@\"", index) or source.startswith("@$\"", index):
            prefix_length = 2
            verbatim = True
        elif source.startswith("@\"", index):
            prefix_length = 1
            verbatim = True
        elif source.startswith("$\"", index):
            prefix_length = 1

        quote_index = index + prefix_length
        if quote_index < length and source[quote_index] == '"':
            cursor = quote_index + 1
            while cursor < length:
                if verbatim and source[cursor] == '"':
                    if cursor + 1 < length and source[cursor + 1] == '"':
                        cursor += 2
                        continue
                    cursor += 1
                    break
                if not verbatim and source[cursor] == "\\":
                    cursor += 2
                    continue
                if not verbatim and source[cursor] == '"':
                    cursor += 1
                    break
                cursor += 1
            output.append(_blank_preserving_newlines(source[index:cursor]))
            index = cursor
            continue

        if char == "'":
            cursor = index + 1
            while cursor < length:
                if source[cursor] == "\\":
                    cursor += 2
                    continue
                if source[cursor] == "'":
                    cursor += 1
                    break
                cursor += 1
            output.append(_blank_preserving_newlines(source[index:cursor]))
            index = cursor
            continue

        output.append(char)
        index += 1

    return "".join(output)


def split_pascal_case(identifier: str) -> list[str]:
    return PASCAL_TOKEN_RE.findall(identifier)


def extract_csharp_identifiers(source: str, source_path: str = "") -> dict:
    sanitized = sanitize_csharp(source)
    namespaces = FILE_NAMESPACE_RE.findall(sanitized) + BLOCK_NAMESPACE_RE.findall(sanitized)
    namespaces = list(dict.fromkeys(namespaces))
    types = [
        {
            "kind": match.group(1),
            "name": match.group(2),
            "source_path": source_path,
            "namespaces": list(namespaces),
        }
        for match in TYPE_DECLARATION_RE.finditer(sanitized)
    ]
    return {"namespaces": namespaces, "types": types}


def merge_extracted(items: Iterable[dict]) -> dict:
    namespaces: list[str] = []
    types: list[dict] = []
    for item in items:
        namespaces.extend(item.get("namespaces", []) or [])
        types.extend(item.get("types", []) or [])
    return {"namespaces": list(dict.fromkeys(namespaces)), "types": types}


def _finding(code: str, identifier: str, message: str, severity: str) -> dict:
    return {
        "code": code,
        "identifier": identifier,
        "severity": severity,
        "message": message,
    }


def _generic_type_findings(type_decl: dict) -> list[dict]:
    name = str(type_decl.get("name", ""))
    tokens = split_pascal_case(name)
    findings: list[dict] = []

    trailing_roles = 0
    for token in reversed(tokens):
        if token in ROLE_TOKENS:
            trailing_roles += 1
        else:
            break
    if trailing_roles >= 2:
        findings.append(
            _finding(
                "NAME001_ROLE_SUFFIX_STACKING",
                name,
                "Multiple primary role suffixes are stacked on one Type.",
                "error",
            )
        )

    if name == "BaseManager" or name in VAGUE_TOKENS or (tokens and tokens[-1] in VAGUE_TOKENS):
        findings.append(
            _finding(
                "NAME002_VAGUE_TYPE_NAME",
                name,
                "Type name uses a vague responsibility term.",
                "error",
            )
        )

    if len(name) >= 33:
        level = "strong responsibility review" if len(name) > 40 else "naming review"
        findings.append(
            _finding(
                "NAME101_LENGTH_REVIEW",
                name,
                f"Type name length is {len(name)} characters and requires {level}.",
                "warning",
            )
        )

    if any(token in CONJUNCTION_TOKENS for token in tokens):
        findings.append(
            _finding(
                "NAME102_CONJUNCTION_REVIEW",
                name,
                "Conjunction in Type name requires responsibility review.",
                "warning",
            )
        )

    for namespace in type_decl.get("namespaces", []) or []:
        namespace_segment = str(namespace).split(".")[-1]
        if len(namespace_segment) >= 4 and name != namespace_segment and name.startswith(namespace_segment):
            findings.append(
                _finding(
                    "NAME103_NAMESPACE_REDUNDANCY",
                    name,
                    f"Type repeats namespace context '{namespace_segment}'.",
                    "warning",
                )
            )
            break

    suspect_tokens: list[str] = []
    for token in tokens:
        if token in KNOWN_ABBREVIATIONS:
            continue
        if token.isupper() and len(token) >= 2:
            suspect_tokens.append(token)
        elif 1 < len(token) <= 3 and token not in {"Api", "Sdk"}:
            suspect_tokens.append(token)
    if suspect_tokens:
        findings.append(
            _finding(
                "NAME104_SUSPECT_ABBREVIATION",
                name,
                f"Possible invented or unexplained abbreviation: {', '.join(suspect_tokens)}.",
                "warning",
            )
        )

    return findings


def grade_extracted_identifiers(extracted: dict, expectation: dict | None = None) -> dict:
    naming = expectation or {}
    types = extracted.get("types", []) or []
    type_names = {str(item.get("name", "")) for item in types if item.get("name")}
    namespace_names = set(extracted.get("namespaces", []) or [])
    namespace_segments = {part for namespace in namespace_names for part in str(namespace).split(".") if part}
    identifiers = type_names | namespace_names | namespace_segments

    findings: list[dict] = []
    for type_decl in types:
        findings.extend(_generic_type_findings(type_decl))

    required_type_names = set(naming.get("required_type_names", []) or [])
    forbidden_type_names = set(naming.get("forbidden_type_names", []) or [])
    required_identifiers = set(naming.get("required_identifiers", []) or [])
    forbidden_identifiers = set(naming.get("forbidden_identifiers", []) or [])

    for identifier in sorted(forbidden_type_names & type_names):
        findings.append(
            _finding("NAME003_FORBIDDEN_IDENTIFIER", identifier, "Forbidden Type name was generated.", "error")
        )
    for identifier in sorted(forbidden_identifiers & identifiers):
        findings.append(
            _finding("NAME003_FORBIDDEN_IDENTIFIER", identifier, "Forbidden identifier was generated.", "error")
        )
    for identifier in sorted(required_type_names - type_names):
        findings.append(
            _finding("NAME004_REQUIRED_IDENTIFIER_MISSING", identifier, "Required Type name is missing.", "error")
        )
    for identifier in sorted(required_identifiers - identifiers):
        findings.append(
            _finding("NAME004_REQUIRED_IDENTIFIER_MISSING", identifier, "Required identifier is missing.", "error")
        )

    if bool(naming.get("require_no_new_type")) and type_names:
        for identifier in sorted(type_names):
            findings.append(
                _finding("NAME005_UNEXPECTED_NEW_TYPE", identifier, "No new Type is allowed for this boundary case.", "error")
            )

    unique: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for finding in findings:
        key = (finding["code"], finding["identifier"], finding["message"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)

    hard = [item for item in unique if item["code"] in HARD_FINDING_CODES]
    warnings = [item for item in unique if item["code"] not in HARD_FINDING_CODES]
    return {
        "passed": not hard,
        "type_names": sorted(type_names),
        "identifiers": sorted(identifiers),
        "findings": unique,
        "errors": hard,
        "warnings": warnings,
    }


def grade_csharp_source(source: str, expectation: dict | None = None, source_path: str = "") -> dict:
    return grade_extracted_identifiers(extract_csharp_identifiers(source, source_path), expectation)


def resolve_artifact_path(path_value: str, allowed_root: Path = GOLDEN_ARTIFACT_ROOT) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise ArtifactEvidenceError("invalid_artifact_path", "Artifact path must be a non-empty string.")

    allowed = allowed_root.resolve()
    candidate = Path(path_value)
    resolved = candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise ArtifactEvidenceError(
            "artifact_path_outside_root",
            f"Artifact path is outside allowed Golden root: {path_value}",
        ) from exc

    if not resolved.is_file():
        raise ArtifactEvidenceError("artifact_missing", f"Generated artifact does not exist: {path_value}")
    return resolved


def grade_generated_artifacts(
    artifacts: list[dict],
    expectation: dict | None = None,
    allowed_root: Path = GOLDEN_ARTIFACT_ROOT,
) -> dict:
    extracted: list[dict] = []
    csharp_artifact_count = 0

    for artifact in artifacts or []:
        if not isinstance(artifact, dict):
            raise ArtifactEvidenceError("invalid_artifact_entry", "Generated artifact entry must be a mapping.")
        language = str(artifact.get("language", "")).strip().lower()
        if language not in {"csharp", "c#", "cs"}:
            continue
        csharp_artifact_count += 1
        path_value = artifact.get("path")
        path = resolve_artifact_path(path_value, allowed_root)
        source = path.read_text(encoding="utf-8")
        extracted.append(extract_csharp_identifiers(source, str(path.relative_to(ROOT))))

    if csharp_artifact_count == 0:
        raise ArtifactEvidenceError(
            "csharp_artifact_missing",
            "Naming evaluation requires at least one generated C# artifact.",
        )

    return grade_extracted_identifiers(merge_extracted(extracted), expectation)
