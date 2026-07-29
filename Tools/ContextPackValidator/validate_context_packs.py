#!/usr/bin/env python3
"""UnityAgent Context Packの参照Pathと最小契約を検証します。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


PACK_DIR = Path(".ai/context-packs")
INDEX_PATH = Path(".ai/context-index.yaml")
REQUIRED_PACKS = {
    "csharp-local-fix.yaml",
    "rendering-incident.yaml",
    "shader-change.yaml",
    "performance.yaml",
    "visual-direction.yaml",
}
LOCAL_REFERENCE_PATTERN = re.compile(
    r"(?:^|\s)(\.agents/[^\s]+|SkillReferences/[^\s]+|Specs/ProjectProfile\.md)(?:\s|$)"
)


def strip_yaml_scalar(value: str) -> str:
    return value.strip().strip("'\"")


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    index_path = root / INDEX_PATH
    pack_dir = root / PACK_DIR

    if not index_path.is_file():
        return [f"Missing file: {INDEX_PATH}"]

    index_text = index_path.read_text(encoding="utf-8")
    required_index_contracts = (
        "select_exactly_one_primary_route: true",
        "load_all_skills: false",
        "load_all_references: false",
        "direct_source_read_required_before_mutation: true",
        "knowledge_graph_is_navigation_only: true",
    )
    for contract in required_index_contracts:
        if contract not in index_text:
            errors.append(f"Missing index contract: {contract}")

    existing_packs = {path.name for path in pack_dir.glob("*.yaml")}
    missing_packs = REQUIRED_PACKS - existing_packs
    for pack in sorted(missing_packs):
        errors.append(f"Missing context pack: {pack}")

    for pack_path in sorted(pack_dir.glob("*.yaml")):
        text = pack_path.read_text(encoding="utf-8")

        for contract in ("required:", "conditional:", "excluded_by_default:", "limits:", "output:"):
            if contract not in text:
                errors.append(f"{pack_path.relative_to(root)} missing section: {contract}")

        if "SkillReferences/UNITY_AGENT_SUPERVISOR_MODEL.md" not in text:
            errors.append(
                f"{pack_path.relative_to(root)} must exclude the legacy Supervisor adapter by default."
            )

        if "context_expansion_hops: 1" not in text:
            errors.append(f"{pack_path.relative_to(root)} must limit context expansion to one hop.")

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.startswith("-"):
                continue

            candidate = strip_yaml_scalar(line[1:])
            if not candidate.startswith((".agents/", "SkillReferences/", "Specs/")):
                continue

            path = root / candidate
            if not path.exists():
                errors.append(
                    f"Broken local reference in {pack_path.relative_to(root)}: {candidate}"
                )

    knowledge_pilot = root / ".ai/knowledge-graph-pilot.yaml"
    if not knowledge_pilot.is_file():
        errors.append("Missing Knowledge Graph pilot contract.")
    else:
        pilot_text = knowledge_pilot.read_text(encoding="utf-8")
        for contract in (
            "max_indexed_files: 200",
            "navigation_only: true",
            "direct_source_read_before_mutation: true",
            "inferred_edge_is_not_confirmed_fact: true",
        ):
            if contract not in pilot_text:
                errors.append(f"Missing Knowledge Graph contract: {contract}")

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate(root)

    if errors:
        print("Context Pack validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Context Pack validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
