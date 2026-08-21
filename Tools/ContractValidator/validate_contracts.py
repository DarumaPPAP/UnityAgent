#!/usr/bin/env python3
"""Validate UnityAgent Knowledge and Task Contract YAML without dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

KEY_PATTERN = re.compile(r"^([a-zA-Z0-9_-]+):(?:\s*(.*))?$")
KNOWLEDGE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
TASK_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

KNOWLEDGE_REQUIRED = {
    "id",
    "version",
    "status",
    "use_when",
    "required_inputs",
    "implementation_contract",
    "prohibited",
    "required_evidence",
    "human_reference",
}
TASK_REQUIRED = {
    "id",
    "default_execution_profile",
    "risk_level",
    "required_inputs",
    "allowed_mutations",
    "prohibited_mutations",
    "required_knowledge",
    "required_quality_gates",
    "completion",
    "stop_conditions",
    "result_format",
}
PROFILES = {"generic_planning", "personal_full_control", "team_safe_import"}
RISK_LEVELS = {"R0", "R1", "R2", "R3", "R4"}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate UnityAgent contract YAML files.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args()


def read_text(path: Path, root: Path) -> tuple[str | None, list[Finding]]:
    try:
        return path.read_text(encoding="utf-8"), []
    except (OSError, UnicodeError) as error:
        return None, [
            Finding(
                "error",
                "CONTRACT001",
                path.relative_to(root).as_posix(),
                f"Cannot read UTF-8 text: {error}",
            )
        ]


def top_level_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        if not raw_line or raw_line[0].isspace() or raw_line.lstrip().startswith("#"):
            continue
        match = KEY_PATTERN.match(raw_line.rstrip())
        if not match:
            continue
        values[match.group(1)] = (match.group(2) or "").strip().strip('"').strip("'")
    return values


def validate_required(
    path: Path, root: Path, values: dict[str, str], required: set[str], prefix: str
) -> list[Finding]:
    relative = path.relative_to(root).as_posix()
    return [
        Finding("error", f"{prefix}002", relative, f"Missing top-level field: {key}")
        for key in sorted(required.difference(values))
    ]


def validate_knowledge(path: Path, root: Path) -> list[Finding]:
    text, findings = read_text(path, root)
    if text is None:
        return findings
    values = top_level_values(text)
    findings.extend(validate_required(path, root, values, KNOWLEDGE_REQUIRED, "KNOWLEDGE"))
    relative = path.relative_to(root).as_posix()
    knowledge_id = values.get("id", "")
    if knowledge_id and not KNOWLEDGE_ID_PATTERN.fullmatch(knowledge_id):
        findings.append(Finding("error", "KNOWLEDGE003", relative, "Invalid knowledge id."))
    if values.get("status") not in {"draft", "reviewed", "deprecated"}:
        findings.append(Finding("error", "KNOWLEDGE004", relative, "Invalid status."))
    if len(text.splitlines()) > 250:
        findings.append(
            Finding("warning", "KNOWLEDGE101", relative, "Knowledge contract exceeds 250 lines.")
        )
    return findings


def validate_task(path: Path, root: Path) -> list[Finding]:
    text, findings = read_text(path, root)
    if text is None:
        return findings
    values = top_level_values(text)
    findings.extend(validate_required(path, root, values, TASK_REQUIRED, "TASK"))
    relative = path.relative_to(root).as_posix()
    task_id = values.get("id", "")
    if task_id and not TASK_ID_PATTERN.fullmatch(task_id):
        findings.append(Finding("error", "TASK003", relative, "Invalid task contract id."))
    if values.get("default_execution_profile") not in PROFILES:
        findings.append(Finding("error", "TASK004", relative, "Invalid execution profile."))
    if values.get("risk_level") not in RISK_LEVELS:
        findings.append(Finding("error", "TASK005", relative, "Invalid risk level."))
    return findings


def validate_index(root: Path, knowledge_files: list[Path]) -> list[Finding]:
    index_path = root / ".ai" / "knowledge" / "index.yaml"
    text, findings = read_text(index_path, root)
    if text is None:
        return findings
    for knowledge_file in knowledge_files:
        knowledge_text, read_findings = read_text(knowledge_file, root)
        findings.extend(read_findings)
        if knowledge_text is None:
            continue
        knowledge_id = top_level_values(knowledge_text).get("id")
        if knowledge_id and knowledge_id not in text:
            findings.append(
                Finding(
                    "error",
                    "INDEX001",
                    index_path.relative_to(root).as_posix(),
                    f"Knowledge id is not indexed: {knowledge_id}",
                )
            )
    return findings


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    knowledge_root = root / ".ai" / "knowledge" / "rendering"
    task_root = root / ".ai" / "harness" / "task-contracts"

    knowledge_files = sorted(knowledge_root.glob("*.yaml")) if knowledge_root.is_dir() else []
    task_files = (
        sorted(path for path in task_root.glob("*.yaml") if not path.name.endswith(".schema.yaml"))
        if task_root.is_dir()
        else []
    )

    findings: list[Finding] = []
    if not knowledge_files:
        findings.append(Finding("error", "KNOWLEDGE000", str(knowledge_root), "No knowledge contracts found."))
    if not task_files:
        findings.append(Finding("error", "TASK000", str(task_root), "No task contracts found."))

    for path in knowledge_files:
        findings.extend(validate_knowledge(path, root))
    for path in task_files:
        findings.extend(validate_task(path, root))
    if knowledge_files:
        findings.extend(validate_index(root, knowledge_files))

    findings.sort(key=lambda item: (item.severity != "error", item.path, item.code))
    errors = sum(item.severity == "error" for item in findings)
    warnings = sum(item.severity == "warning" for item in findings)

    payload = {
        "knowledge_contracts": len(knowledge_files),
        "task_contracts": len(task_files),
        "errors": errors,
        "warnings": warnings,
        "findings": [asdict(item) for item in findings],
    }
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in findings:
            print(f"[{item.severity.upper()}] {item.code} {item.path}: {item.message}")
        print(
            f"Validated {len(knowledge_files)} knowledge contract(s) and "
            f"{len(task_files)} task contract(s): {errors} error(s), {warnings} warning(s)."
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
