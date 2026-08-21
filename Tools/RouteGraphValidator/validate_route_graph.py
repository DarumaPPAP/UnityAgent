#!/usr/bin/env python3
"""UnityAgentのCanonical Route GraphとUser Policy保護状態を検証します。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


INDEX_PATH = Path(".ai/context-index.yaml")
USER_POLICY_PATH = Path(".ai/user-policy.yaml")
EXECUTION_PROFILES_PATH = Path(".ai/execution-profiles.yaml")
QUALITY_GATES_PATH = Path(".ai/harness/quality-gates.yaml")
LEGACY_ROUTING_PATH = Path("SkillReferences/UNITY_SKILL_ROUTING.md")
OBSOLETE_CONSTITUTION_PATH = Path("Specs/ProjectConstitution.md")
OBSOLETE_HARNESS_PATHS = (
    Path(".ai/task-contracts"),
    Path(".ai/quality-gates.yaml"),
    Path(".ai/mutation-channels.yaml"),
    Path(".ai/risk-levels.yaml"),
    Path(".ai/mcp-routing.yaml"),
)

REQUIRED_ROUTE_IDS = {
    "architecture-design",
    "graphics-mcp",
    "csharp-local-fix",
    "rendering-incident",
    "shader-change",
    "renderer-feature-change",
    "performance-experiment",
    "asset-data-change",
    "portable-feature",
    "safe-import-integration",
    "visual-direction",
}

EXPECTED_ROUTE_BINDINGS = {
    "renderer-feature-change": (
        ".ai/context-packs/renderer-feature-change.yaml",
        ".ai/harness/task-contracts/renderer-feature-change.yaml",
    ),
    "asset-data-change": (
        ".ai/context-packs/asset-data-change.yaml",
        ".ai/harness/task-contracts/asset-data-change.yaml",
    ),
    "portable-feature": (
        ".ai/context-packs/portable-feature.yaml",
        ".ai/harness/task-contracts/portable-feature.yaml",
    ),
    "visual-direction": (
        ".ai/context-packs/visual-direction.yaml",
        ".ai/harness/task-contracts/visual-direction.yaml",
    ),
}

PROTECTED_COMMENT_SKILLS = (
    Path(".agents/skills/production-code-comments/SKILL.md"),
    Path(".agents/skills/learning-code-comments/SKILL.md"),
    Path(".agents/skills/comment-quality-reviewer/SKILL.md"),
)

KEBAB_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def scalar(value: str) -> str:
    return value.strip().strip("'\"")


def first_scalar(text: str, key: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.+)$", re.MULTILINE)
    match = pattern.search(text)
    return scalar(match.group(1)) if match else None


def parse_routes(index_text: str) -> dict[str, dict[str, str]]:
    routes: dict[str, dict[str, str]] = {}
    in_routes = False
    current_key: str | None = None

    for raw_line in index_text.splitlines():
        if raw_line == "routes:":
            in_routes = True
            continue
        if in_routes and raw_line and not raw_line.startswith(" "):
            break
        if not in_routes:
            continue

        route_match = re.match(r"^  ([a-z0-9_]+):$", raw_line)
        if route_match:
            current_key = route_match.group(1)
            routes[current_key] = {}
            continue

        property_match = re.match(
            r"^    (id|primary_skill|context_pack|task_contract):\s*(.+)$",
            raw_line,
        )
        if property_match and current_key is not None:
            routes[current_key][property_match.group(1)] = scalar(property_match.group(2))

    return routes


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    index_path = root / INDEX_PATH
    user_policy_path = root / USER_POLICY_PATH
    if not index_path.is_file():
        return [f"Missing file: {INDEX_PATH}"]
    if not user_policy_path.is_file():
        errors.append(f"Missing file: {USER_POLICY_PATH}")

    index_text = index_path.read_text(encoding="utf-8")
    routes = parse_routes(index_text)

    required_index_contracts = (
        "user_policy: .ai/user-policy.yaml",
        "task_contract_schema: .ai/harness/task-contracts/task-contract.schema.yaml",
        "quality_gates: .ai/harness/quality-gates.yaml",
        "mutation_channels: .ai/harness/mutation-channels.yaml",
        "risk_levels: .ai/harness/risk-levels.yaml",
        "mcp_activation_policy: .ai/harness/mcp-activation.yaml",
        "user_policy_must_be_loaded_before_domain_decision: true",
        "generic_best_practice_must_not_override_user_policy: true",
        "select_exactly_one_primary_route: true",
        "select_exactly_one_primary_task_contract: true",
        "route_id_format: kebab-case",
        "do_not_use_legacy_routing_document: true",
    )
    for contract in required_index_contracts:
        if contract not in index_text:
            errors.append(f"Missing canonical routing contract: {contract}")

    for obsolete_path in OBSOLETE_HARNESS_PATHS:
        if (root / obsolete_path).exists():
            errors.append(f"Obsolete pre-Harness path must not be restored: {obsolete_path}")

    ids = {data.get("id", "") for data in routes.values()}
    missing_ids = REQUIRED_ROUTE_IDS - ids
    unexpected_ids = ids - REQUIRED_ROUTE_IDS
    for route_id in sorted(missing_ids):
        errors.append(f"Missing canonical route id: {route_id}")
    for route_id in sorted(unexpected_ids):
        errors.append(f"Unexpected canonical route id: {route_id}")

    seen_ids: set[str] = set()
    for mapping_key, data in sorted(routes.items()):
        route_id = data.get("id")
        primary_skill = data.get("primary_skill")
        context_pack = data.get("context_pack")
        task_contract = data.get("task_contract")

        for field_name, value in (
            ("id", route_id),
            ("primary_skill", primary_skill),
            ("context_pack", context_pack),
            ("task_contract", task_contract),
        ):
            if not value:
                errors.append(f"Route {mapping_key} missing field: {field_name}")

        if not route_id:
            continue
        if not KEBAB_PATTERN.fullmatch(route_id):
            errors.append(f"Route id is not kebab-case: {route_id}")
        if route_id in seen_ids:
            errors.append(f"Duplicate route id: {route_id}")
        seen_ids.add(route_id)

        skill_path = root / f".agents/skills/{primary_skill}/SKILL.md" if primary_skill else None
        if skill_path is not None and not skill_path.is_file():
            errors.append(f"Route {route_id} references missing skill: {skill_path.relative_to(root)}")

        if context_pack:
            pack_path = root / context_pack
            if not pack_path.is_file():
                errors.append(f"Route {route_id} references missing context pack: {context_pack}")
            else:
                pack_text = pack_path.read_text(encoding="utf-8")
                pack_id = first_scalar(pack_text, "id")
                if pack_id != route_id and route_id not in {"performance-experiment", "safe-import-integration"}:
                    errors.append(
                        f"Route {route_id} uses context pack id {pack_id}; dedicated pack is required."
                    )
                expected_primary_path = f".agents/skills/{primary_skill}/SKILL.md"
                pack_primary = first_scalar(pack_text, "primary_skill")
                if pack_primary != expected_primary_path:
                    errors.append(
                        f"Route {route_id} primary skill mismatch: index={primary_skill}, pack={pack_primary}"
                    )

        if task_contract:
            contract_path = root / task_contract
            if not contract_path.is_file():
                errors.append(f"Route {route_id} references missing task contract: {task_contract}")
            else:
                contract_text = contract_path.read_text(encoding="utf-8")
                contract_id = first_scalar(contract_text, "id")
                if contract_id != route_id:
                    errors.append(
                        f"Route {route_id} task contract id mismatch: {contract_id}"
                    )

    for route_id, (expected_pack, expected_contract) in EXPECTED_ROUTE_BINDINGS.items():
        matching = next((data for data in routes.values() if data.get("id") == route_id), None)
        if matching is None:
            continue
        if matching.get("context_pack") != expected_pack:
            errors.append(f"Route {route_id} must use {expected_pack}")
        if matching.get("task_contract") != expected_contract:
            errors.append(f"Route {route_id} must use {expected_contract}")

    if (root / OBSOLETE_CONSTITUTION_PATH).exists():
        errors.append("Obsolete Specs/ProjectConstitution.md must not be restored.")

    legacy_routing = root / LEGACY_ROUTING_PATH
    if legacy_routing.is_file():
        legacy_text = legacy_routing.read_text(encoding="utf-8")
        if "Compatibility Reference" not in legacy_text:
            errors.append("Legacy routing path must remain a compatibility-only reference.")
        for obsolete_heading in (
            "## 3. State-based routing",
            "## 4. Failure routing",
            "## 5. Intent classifiers",
        ):
            if obsolete_heading in legacy_text:
                errors.append(f"Legacy routing table was restored: {obsolete_heading}")

    for skill_path in PROTECTED_COMMENT_SKILLS:
        full_path = root / skill_path
        if not full_path.is_file():
            errors.append(f"Missing protected comment skill: {skill_path}")
            continue
        text = full_path.read_text(encoding="utf-8")
        for marker in (
            "kind: user-policy-operation",
            "policy_owner: user",
            "protected: true",
            "policy_source: .ai/user-policy.yaml#comment_system",
        ):
            if marker not in text:
                errors.append(f"{skill_path} missing protected policy marker: {marker}")

    if user_policy_path.is_file():
        policy_text = user_policy_path.read_text(encoding="utf-8")
        for marker in (
            "policy_owner: user",
            "status: authoritative",
            "older_policy_must_not_overwrite_current_policy: true",
            "comment_system:",
            "simplification_requires_user_approval: true",
        ):
            if marker not in policy_text:
                errors.append(f"User policy missing marker: {marker}")

    execution_profiles = root / EXECUTION_PROFILES_PATH
    quality_gates = root / QUALITY_GATES_PATH
    if execution_profiles.is_file() and quality_gates.is_file():
        execution_text = execution_profiles.read_text(encoding="utf-8")
        quality_text = quality_gates.read_text(encoding="utf-8")
        if "- deferred_environment" in execution_text:
            errors.append("deferred_environment must be a reason_code, not a gate status.")
        for status in ("passed", "failed", "unavailable"):
            if f"- {status}" not in execution_text or f"- {status}" not in quality_text:
                errors.append(f"Quality gate status is not shared by both contracts: {status}")

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate(root)

    if errors:
        print("Route Graph validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Route Graph validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
