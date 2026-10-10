"""Capability contract validation shared by Runtime dispatch boundaries and local validation."""
from __future__ import annotations
from unityagent.resources import resource_root

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = resource_root()
if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
REQUEST_SCHEMA_PATH = Path("src/unityagent/runtime/contracts/capability-request.schema.yaml")
RESOLUTION_SCHEMA_PATH = Path("src/unityagent/runtime/contracts/capability-resolution.schema.yaml")
POLICY_PATH = Path("src/unityagent/policy/security/tool-capability-policy.yaml")
ROUTING_PATH = Path("src/unityagent/orchestration/tool_routing/capability-routing.yaml")
TASK_ROUTES_PATH = Path("src/unityagent/orchestration/routing/task-routes.yaml")
CONTEXT_CATALOG_PATH = Path("src/unityagent/context/selection/tool-capability-catalog.yaml")

FORBIDDEN_ORCHESTRATION_PROVIDER_TOKENS = (
    "unity_cli",
    "unity cli",
    "myunitymcp",
    "coplay_mcp",
    "coplay mcp",
)


@dataclass(frozen=True)
class CapabilityContractFinding:
    path: str
    message: str


def _yaml(root: Path, relative: Path) -> dict[str, Any]:
    value = yaml.safe_load((root / relative).read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"expected mapping: {relative}")
    return value


def validate_capability_request(value: dict[str, Any], *, root: Path = ROOT) -> None:
    schema = _yaml(root, REQUEST_SCHEMA_PATH)
    Draft202012Validator(schema).validate(value)

    policy = _yaml(root, POLICY_PATH)
    capability = str(value["capability"])
    capability_policy = (policy.get("capabilities") or {}).get(capability)
    if not isinstance(capability_policy, dict):
        raise ValueError(f"unknown capability: {capability}")

    expected_operation = str(capability_policy["operation_kind"])
    if value["operation_kind"] != expected_operation:
        raise ValueError(
            f"{capability}: operation_kind must be {expected_operation}, got {value['operation_kind']}"
        )

    required_evidence = set(value.get("required_evidence") or [])
    minimum_evidence = set(capability_policy.get("minimum_required_evidence") or [])
    if not minimum_evidence.issubset(required_evidence):
        raise ValueError(f"{capability}: required_evidence is weaker than Policy minimum")

    operation_policy = (policy.get("operation_kinds") or {}).get(expected_operation) or {}
    if operation_policy.get("requires_mutation_scope") is True:
        scope = value.get("mutation_scope")
        if not isinstance(scope, dict) or not scope.get("allowed_paths"):
            raise ValueError(f"{capability}: mutation_scope is required by src/unityagent/policy")


def validate_capability_resolution(value: dict[str, Any], *, root: Path = ROOT) -> None:
    schema = _yaml(root, RESOLUTION_SCHEMA_PATH)
    Draft202012Validator(schema).validate(value)
    if value["status"] == "resolved":
        if value.get("failure_class") is not None:
            raise ValueError("resolved capability cannot carry failure_class")
    elif value.get("failure_class") != value["status"]:
        raise ValueError("non-resolved capability status and failure_class must match")


def validate_contract_foundation(root: Path = ROOT) -> list[CapabilityContractFinding]:
    findings: list[CapabilityContractFinding] = []
    request_schema = _yaml(root, REQUEST_SCHEMA_PATH)
    policy = _yaml(root, POLICY_PATH)
    routing = _yaml(root, ROUTING_PATH)
    task_routes = _yaml(root, TASK_ROUTES_PATH)
    context_catalog = _yaml(root, CONTEXT_CATALOG_PATH)

    Draft202012Validator.check_schema(request_schema)
    Draft202012Validator.check_schema(_yaml(root, RESOLUTION_SCHEMA_PATH))

    schema_capabilities = set(request_schema["properties"]["capability"]["enum"])
    schema_operation_kinds = set(request_schema["properties"]["operation_kind"]["enum"])
    schema_evidence = set(request_schema["properties"]["required_evidence"]["items"]["enum"])
    policy_capabilities = set((policy.get("capabilities") or {}).keys())
    context_capabilities = set((context_catalog.get("capabilities") or {}).keys())

    if schema_capabilities != policy_capabilities:
        findings.append(
            CapabilityContractFinding(
                POLICY_PATH.as_posix(),
                "Policy capability set must exactly match CapabilityRequest schema.",
            )
        )
    if schema_capabilities != context_capabilities:
        findings.append(
            CapabilityContractFinding(
                CONTEXT_CATALOG_PATH.as_posix(),
                "Context capability set must exactly match CapabilityRequest schema.",
            )
        )

    operation_kinds = policy.get("operation_kinds") or {}
    if set(operation_kinds) != schema_operation_kinds:
        findings.append(
            CapabilityContractFinding(
                POLICY_PATH.as_posix(),
                "Policy operation_kind set must exactly match CapabilityRequest schema.",
            )
        )

    for capability, capability_policy in (policy.get("capabilities") or {}).items():
        operation_kind = str((capability_policy or {}).get("operation_kind") or "")
        if operation_kind not in schema_operation_kinds:
            findings.append(
                CapabilityContractFinding(
                    POLICY_PATH.as_posix(),
                    f"{capability}: unknown operation_kind {operation_kind}",
                )
            )
        required_evidence = set((capability_policy or {}).get("minimum_required_evidence") or [])
        if not required_evidence or not required_evidence.issubset(schema_evidence):
            findings.append(
                CapabilityContractFinding(
                    POLICY_PATH.as_posix(),
                    f"{capability}: invalid minimum_required_evidence",
                )
            )

    canonical_routes = set((task_routes.get("routes") or {}).keys())
    capability_routes = set((routing.get("routes") or {}).keys())
    if capability_routes != canonical_routes:
        findings.append(
            CapabilityContractFinding(
                ROUTING_PATH.as_posix(),
                "Capability routing must cover exactly the canonical task route ids during shadow rollout.",
            )
        )

    declared_conditions = set(routing.get("conditions") or [])
    for route_id, route in (routing.get("routes") or {}).items():
        serialized = yaml.safe_dump(route, sort_keys=True, allow_unicode=True).lower()
        for token in FORBIDDEN_ORCHESTRATION_PROVIDER_TOKENS:
            if token in serialized:
                findings.append(
                    CapabilityContractFinding(
                        ROUTING_PATH.as_posix(),
                        f"{route_id}: provider product token is forbidden in semantic capability routing: {token}",
                    )
                )

        candidate_templates = (route or {}).get("candidate_capabilities") or []
        reasoning_templates = (route or {}).get("reasoning_capabilities") or []
        task_route = (task_routes.get("routes") or {}).get(route_id) or {}
        if candidate_templates and (not task_route.get("specialist_pilot") or not task_route.get("specialist_profile")):
            findings.append(CapabilityContractFinding(ROUTING_PATH.as_posix(), f"{route_id}: candidate capability requires a Candidate Specialist route"))
        if reasoning_templates:
            from unityagent.runtime.reference_implementation.profiles import SubAgentProfileCatalog, ProfileValidationError
            try:
                catalog = SubAgentProfileCatalog.from_file(root / "src/unityagent/runtime/reference_implementation/subagent-catalog.yaml")
                profile = catalog.get(task_route.get("specialist_profile"))
                if task_route.get("specialist_pilot") or profile.execution.get("kind") != "reasoning" or candidate_templates:
                    raise ValueError("reasoning capability requires a registered reasoning Specialist route")
                requested = {item.get("capability") for item in reasoning_templates if isinstance(item, dict)}
                if not requested.issubset(profile.capabilities):
                    raise ValueError("reasoning capability is outside the registered Profile")
                observed = {item.get("capability") for item in route.get("capabilities", []) if item.get("when") == "always"}
                if not set(profile.execution["required_observation_capabilities"]).issubset(observed):
                    raise ValueError("reasoning route omits required observation capabilities")
            except (ProfileValidationError, ValueError, OSError) as exc:
                findings.append(CapabilityContractFinding(ROUTING_PATH.as_posix(), f"{route_id}: {exc}"))
        for template in candidate_templates + reasoning_templates:
            if not isinstance(template, dict) or set(template) != {"capability", "operation_kind", "required_evidence", "preferred_surface", "when"}:
                findings.append(CapabilityContractFinding(ROUTING_PATH.as_posix(), f"{route_id}: invalid candidate capability template"))
                continue
            if template["operation_kind"] != "read":
                findings.append(CapabilityContractFinding(ROUTING_PATH.as_posix(), f"{route_id}: candidate capability must be read-only"))
            if not isinstance(template["capability"], str) or not template["capability"] or not isinstance(template["required_evidence"], list) or not template["required_evidence"] or template["when"] not in declared_conditions:
                findings.append(CapabilityContractFinding(ROUTING_PATH.as_posix(), f"{route_id}: invalid candidate capability requirement"))

        for template in (route or {}).get("capabilities") or []:
            capability = str(template.get("capability") or "")
            operation_kind = str(template.get("operation_kind") or "")
            evidence = set(template.get("required_evidence") or [])
            condition = str(template.get("when") or "")
            if capability not in schema_capabilities:
                findings.append(
                    CapabilityContractFinding(
                        ROUTING_PATH.as_posix(),
                        f"{route_id}: unknown capability {capability}",
                    )
                )
                continue
            policy_operation = str(policy["capabilities"][capability]["operation_kind"])
            if operation_kind != policy_operation:
                findings.append(
                    CapabilityContractFinding(
                        ROUTING_PATH.as_posix(),
                        f"{route_id}/{capability}: operation_kind must match src/unityagent/policy ({policy_operation})",
                    )
                )
            minimum_evidence = set(policy["capabilities"][capability]["minimum_required_evidence"])
            if not minimum_evidence.issubset(evidence) or not evidence.issubset(schema_evidence):
                findings.append(
                    CapabilityContractFinding(
                        ROUTING_PATH.as_posix(),
                        f"{route_id}/{capability}: required_evidence does not satisfy src/unityagent/policy/schema",
                    )
                )
            if condition not in declared_conditions:
                findings.append(
                    CapabilityContractFinding(
                        ROUTING_PATH.as_posix(),
                        f"{route_id}/{capability}: unknown condition {condition}",
                    )
                )

    return findings


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    findings = validate_contract_foundation(root=args.root)
    if findings:
        for finding in findings:
            print(f"[ERROR] {finding.path}: {finding.message}")
        return 1
    print("Capability contract foundation validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
