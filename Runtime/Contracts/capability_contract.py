"""Capability contract validation shared by Runtime dispatch boundaries and local validation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
REQUEST_SCHEMA_PATH = Path("Runtime/Contracts/capability-request.schema.yaml")
RESOLUTION_SCHEMA_PATH = Path("Runtime/Contracts/capability-resolution.schema.yaml")
POLICY_PATH = Path("Policy/Security/tool-capability-policy.yaml")
ROUTING_PATH = Path("Orchestration/ToolRouting/capability-routing.yaml")
TASK_ROUTES_PATH = Path("Orchestration/Routing/task-routes.yaml")
CONTEXT_CATALOG_PATH = Path("Context/Selection/tool-capability-catalog.yaml")

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
            raise ValueError(f"{capability}: mutation_scope is required by Policy")


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
                        f"{route_id}/{capability}: operation_kind must match Policy ({policy_operation})",
                    )
                )
            minimum_evidence = set(policy["capabilities"][capability]["minimum_required_evidence"])
            if not minimum_evidence.issubset(evidence) or not evidence.issubset(schema_evidence):
                findings.append(
                    CapabilityContractFinding(
                        ROUTING_PATH.as_posix(),
                        f"{route_id}/{capability}: required_evidence does not satisfy Policy/schema",
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
    findings = validate_contract_foundation()
    if findings:
        for finding in findings:
            print(f"[ERROR] {finding.path}: {finding.message}")
        return 1
    print("Capability contract foundation validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
