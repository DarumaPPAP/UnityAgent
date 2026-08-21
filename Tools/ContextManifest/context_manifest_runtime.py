#!/usr/bin/env python3
"""Context Manifest Runtime primitives for UnityAgent.

Canonical YAML remains the source of truth. This module builds one runtime
Context Manifest from a Task Fingerprint and explicit bindings, validates the
manifest against current Context/Harness contracts, records gate evidence, and
projects an Execution Graph view.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


INDEX_PATH = Path(".ai/context-index.yaml")
GRAPH_CONTRACT_PATH = Path(".ai/graph-contract.yaml")
USER_POLICY_PATH = Path(".ai/user-policy.yaml")
QUALITY_GATES_PATH = Path(".ai/harness/quality-gates.yaml")
RISK_LEVELS_PATH = Path(".ai/harness/risk-levels.yaml")
MCP_ACTIVATION_PATH = Path(".ai/harness/mcp-activation.yaml")

MANIFEST_SCHEMA_VERSION = "3.0"
GRAPH_SCHEMA_VERSION = "1.0"

EXECUTION_STATUSES = {
    "in_progress",
    "passed",
    "failed",
    "complete_with_unavailable",
}
MUTATION_EFFECTS = {"allow", "prohibit"}
GATE_REQUIREMENTS = {"required", "conditional"}

PATH_SUFFIXES = (
    ".md",
    ".yaml",
    ".yml",
    ".cs",
    ".shader",
    ".hlsl",
    ".compute",
    ".asmdef",
    ".json",
)


class ManifestError(ValueError):
    """Raised when a manifest request cannot be built safely."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ManifestError([f"Missing file: {path.as_posix()}"])
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ManifestError([f"Expected YAML mapping: {path.as_posix()}"])
    return data


def stable_node_id(node_type: str, stable_id: str) -> str:
    return f"{node_type}:{stable_id}"


def _is_path_reference(value: str) -> bool:
    return "/" in value or value.endswith(PATH_SUFFIXES)


def _routes(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = index.get("routes", {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(route.get("id")): route
        for route in raw.values()
        if isinstance(route, dict) and route.get("id")
    }


def _validate_fingerprint(
    index: dict[str, Any],
    route: dict[str, Any],
    fingerprint: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    contract = index.get("task_fingerprint", {})
    dimensions = contract.get("dimensions", {}) if isinstance(contract, dict) else {}
    required_dimensions = (
        contract.get("required_dimensions", []) if isinstance(contract, dict) else []
    )

    if not isinstance(fingerprint, dict):
        return ["task.fingerprint must be a mapping."]

    for dimension in required_dimensions:
        if dimension not in fingerprint:
            errors.append(f"Missing Task Fingerprint dimension: {dimension}")

    for dimension, value in fingerprint.items():
        allowed = dimensions.get(dimension)
        if not isinstance(allowed, list):
            errors.append(f"Unknown Task Fingerprint dimension: {dimension}")
        elif value not in allowed:
            errors.append(f"Unsupported Task Fingerprint value: {dimension}={value}")

    match = route.get("fingerprint_match", {})
    if not isinstance(match, dict):
        errors.append(f"Route {route.get('id')} has no fingerprint_match mapping.")
        return errors

    for dimension, accepted in match.items():
        if dimension not in fingerprint:
            errors.append(
                f"Fingerprint lacks route-match dimension for {route.get('id')}: {dimension}"
            )
            continue
        if fingerprint[dimension] not in accepted:
            errors.append(
                f"Fingerprint does not match route {route.get('id')}: "
                f"{dimension}={fingerprint[dimension]} not in {accepted}"
            )

    return errors


def _normalize_binding(name: str, raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        kind = str(raw.get("kind", "scalar"))
        values = raw.get("values", [])
        reason = str(raw.get("reason", "required_context"))
    else:
        kind = "scalar"
        values = raw if isinstance(raw, list) else [raw]
        reason = "required_context"

    if not isinstance(values, list):
        values = [values]

    return {
        "name": name,
        "kind": kind,
        "values": [str(value) for value in values],
        "reason": reason,
    }


def _canonical_context_item(source_path: str, reason: str) -> dict[str, Any]:
    return {
        "node_id": stable_node_id("source", source_path),
        "source_path": source_path,
        "reason": reason,
    }


def _gate_entries(contract: dict[str, Any]) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for gate in contract.get("required_quality_gates", []) or []:
        gates.append(
            {
                "node_id": stable_node_id("quality_gate", str(gate)),
                "id": str(gate),
                "requirement": "required",
            }
        )
    for gate in contract.get("conditional_quality_gates", []) or []:
        gates.append(
            {
                "node_id": stable_node_id("quality_gate", str(gate)),
                "id": str(gate),
                "requirement": "conditional",
            }
        )
    return gates


def _mutation_entries(contract_id: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for rule in contract.get("allowed_mutations", []) or []:
        rule_id = str(rule)
        entries.append(
            {
                "node_id": stable_node_id(
                    "mutation_rule", f"{contract_id}:allow:{rule_id}"
                ),
                "id": rule_id,
                "effect": "allow",
            }
        )
    for rule in contract.get("prohibited_mutations", []) or []:
        rule_id = str(rule)
        entries.append(
            {
                "node_id": stable_node_id(
                    "mutation_rule", f"{contract_id}:prohibit:{rule_id}"
                ),
                "id": rule_id,
                "effect": "prohibit",
            }
        )
    return entries


def _loaded_paths(manifest: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for section, key in (("policy", "loaded"), ("knowledge", "loaded")):
        values = manifest.get(section, {}).get(key, [])
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict) and item.get("source_path"):
                    paths.add(str(item["source_path"]))

    context = manifest.get("context", {})
    for key in ("required_context", "conditional_context", "source_files"):
        values = context.get(key, [])
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict) and item.get("source_path"):
                    paths.add(str(item["source_path"]))
    return paths


def derive_execution_status(manifest: dict[str, Any]) -> str:
    gates = manifest.get("harness", {}).get("quality_gates", [])
    required = [
        gate
        for gate in gates
        if isinstance(gate, dict) and gate.get("requirement") == "required"
    ]

    statuses = [gate.get("status") for gate in required]
    if any(status == "failed" for status in statuses):
        return "failed"
    if required and all(status == "passed" for status in statuses):
        return "passed"
    if required and all(status in {"passed", "unavailable"} for status in statuses):
        if any(status == "unavailable" for status in statuses):
            return "complete_with_unavailable"
    return "in_progress"


def build_manifest(
    root: Path,
    request: dict[str, Any],
    previous_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    index = load_yaml(root / INDEX_PATH)
    route_by_id = _routes(index)

    task = request.get("task", {})
    if not isinstance(task, dict):
        raise ManifestError(["request.task must be a mapping."])

    task_id = str(task.get("id", "")).strip()
    route_id = str(task.get("route", "")).strip()
    fingerprint = task.get("fingerprint", {})

    if not task_id:
        errors.append("request.task.id is required.")
    if not route_id:
        errors.append("request.task.route is required.")
    route = route_by_id.get(route_id)
    if route is None:
        errors.append(f"Unknown route: {route_id}")
    else:
        errors.extend(_validate_fingerprint(index, route, fingerprint))

    if errors:
        raise ManifestError(errors)

    context_pack_path = Path(str(route["context_pack"]))
    contract_path = Path(str(route["task_contract"]))
    context_pack = load_yaml(root / context_pack_path)
    contract = load_yaml(root / contract_path)

    previous_attempt = None
    previous_manifest_id = None
    attempt = 1
    previous_failure = None
    if previous_manifest is not None:
        previous_meta = previous_manifest.get("manifest", {})
        previous_attempt = int(previous_meta.get("attempt", 0))
        previous_manifest_id = str(previous_meta.get("id", "")).strip()
        if previous_attempt < 1 or not previous_manifest_id:
            raise ManifestError(["Previous manifest has invalid id or attempt."])
        previous_task = previous_manifest.get("task", {})
        if previous_task.get("id") != task_id:
            raise ManifestError(["Previous manifest task id does not match retry request."])
        attempt = previous_attempt + 1
        previous_execution = previous_manifest.get("execution", {})
        previous_failure = {
            "manifest_id": previous_manifest_id,
            "attempt": previous_attempt,
            "status": previous_execution.get("status"),
            "failure_reason": previous_execution.get("failure_reason"),
            "evidence_ids": [
                item.get("id")
                for item in previous_execution.get("evidence", [])
                if isinstance(item, dict) and item.get("id")
            ],
        }

    manifest_id = str(request.get("manifest_id", "")).strip()
    if not manifest_id:
        manifest_id = f"{task_id}-a{attempt}"

    bindings_raw = request.get("bindings", {})
    if not isinstance(bindings_raw, dict):
        raise ManifestError(["request.bindings must be a mapping."])
    bindings = [
        _normalize_binding(str(name), raw)
        for name, raw in sorted(bindings_raw.items())
    ]
    binding_names = {binding["name"] for binding in bindings}

    source_files: list[dict[str, Any]] = []
    for binding in bindings:
        if binding["kind"] != "source":
            continue
        for source_path in binding["values"]:
            source_files.append(
                {
                    "node_id": stable_node_id("source", source_path),
                    "source_path": source_path,
                    "binding": binding["name"],
                    "reason": binding["reason"],
                }
            )

    conditions = request.get("conditions", []) or []
    if not isinstance(conditions, list):
        raise ManifestError(["request.conditions must be a list."])
    conditions = [str(value) for value in conditions]

    required_context: list[dict[str, Any]] = []
    conditional_context: list[dict[str, Any]] = []
    unresolved: set[str] = {
        str(value) for value in (request.get("unresolved_bindings", []) or [])
    }

    for value in context_pack.get("required", []) or []:
        value = str(value)
        if _is_path_reference(value):
            required_context.append(_canonical_context_item(value, "required_context"))
        elif value not in binding_names:
            unresolved.add(value)

    conditional_map = context_pack.get("conditional", {}) or {}
    if not isinstance(conditional_map, dict):
        raise ManifestError([f"{context_pack_path} conditional must be a mapping."])

    for condition in conditions:
        values = conditional_map.get(condition)
        if values is None:
            raise ManifestError(
                [f"Unknown Context Pack condition for {route_id}: {condition}"]
            )
        for value in values or []:
            value = str(value)
            if _is_path_reference(value):
                conditional_context.append(
                    _canonical_context_item(value, "conditional_context")
                )
            elif value not in binding_names:
                unresolved.add(value)

    for required_input in contract.get("required_inputs", []) or []:
        required_input = str(required_input)
        if required_input not in binding_names:
            unresolved.add(required_input)

    project_facts: list[dict[str, Any]] = []
    for item in request.get("project_facts", []) or []:
        if not isinstance(item, dict):
            raise ManifestError(["project_facts entries must be mappings."])
        key = str(item.get("key", "")).strip()
        source_path = str(item.get("source_path", "")).strip()
        if not key or not source_path:
            raise ManifestError(["project_facts require key and source_path."])
        project_facts.append(
            {
                "node_id": stable_node_id("project_fact", key),
                "key": key,
                "value": item.get("value"),
                "source_path": source_path,
                "reason": str(item.get("reason", "project_fact")),
            }
        )

    knowledge: list[dict[str, Any]] = []
    for raw in request.get("knowledge", []) or []:
        if isinstance(raw, str):
            source_path = raw
            reason = "required_context"
        elif isinstance(raw, dict):
            source_path = str(raw.get("source_path", "")).strip()
            reason = str(raw.get("reason", "required_context"))
        else:
            raise ManifestError(["knowledge entries must be strings or mappings."])
        if not source_path:
            raise ManifestError(["knowledge source_path must not be empty."])
        knowledge.append(
            {
                "node_id": stable_node_id("knowledge", source_path),
                "source_path": source_path,
                "reason": reason,
            }
        )

    tools: list[dict[str, Any]] = []
    for raw in request.get("tools", []) or []:
        if not isinstance(raw, dict) or not raw.get("id"):
            raise ManifestError(["tools entries require id."])
        tool_id = str(raw["id"])
        tools.append(
            {
                "node_id": stable_node_id("tool", tool_id),
                "id": tool_id,
                "reason": str(raw.get("reason", "harness_contract")),
            }
        )

    excluded_context = [
        {
            "node_id": stable_node_id("source", str(value)),
            "source_path": str(value),
            "reason": "excluded_context",
        }
        for value in context_pack.get("excluded_by_default", []) or []
    ]

    primary_skill_name = str(route.get("primary_skill", "")).strip()
    primary_skill_path = (
        f".agents/skills/{primary_skill_name}/SKILL.md"
        if primary_skill_name
        else None
    )
    contract_id = str(contract.get("id", route_id))

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest": {
            "id": manifest_id,
            "graph_kind": "execution",
            "attempt": attempt,
        },
        "task": {
            "id": task_id,
            "route": route_id,
            "fingerprint": copy.deepcopy(fingerprint),
        },
        "policy": {
            "loaded": [
                {
                    "node_id": stable_node_id("policy", "user-policy"),
                    "source_path": USER_POLICY_PATH.as_posix(),
                    "reason": "user_policy",
                }
            ]
        },
        "project_facts": {"loaded": project_facts},
        "context": {
            "context_pack": {
                "node_id": stable_node_id("context_pack", str(context_pack.get("id"))),
                "source_path": context_pack_path.as_posix(),
            },
            "primary_skill": {
                "node_id": stable_node_id("skill", primary_skill_name),
                "source_path": primary_skill_path,
            },
            "bindings": bindings,
            "conditions_applied": conditions,
            "required_context": required_context,
            "conditional_context": conditional_context,
            "source_files": source_files,
            "excluded_context": excluded_context,
        },
        "knowledge": {"loaded": knowledge},
        "harness": {
            "task_contract": {
                "node_id": stable_node_id("task_contract", contract_id),
                "source_path": contract_path.as_posix(),
            },
            "mutation_rules": _mutation_entries(contract_id, contract),
            "risk_level": {
                "node_id": stable_node_id("risk_level", str(contract.get("risk_level"))),
                "id": contract.get("risk_level"),
            },
            "quality_gates": _gate_entries(contract),
        },
        "tools": {"activated": tools},
        "execution": {
            "evidence": [],
            "unresolved_bindings": sorted(unresolved),
            "status": "in_progress",
        },
        "graph_projection": {
            "contract": GRAPH_CONTRACT_PATH.as_posix(),
            "graph_kind": "execution",
            "manifest_is_graph_instance": True,
            "stable_node_ids_required_when_emitted": True,
            "typed_edges_required": True,
            "provenance_required": True,
            "source_of_truth_remains_canonical_yaml": True,
        },
    }

    if previous_manifest_id is not None:
        manifest["manifest"]["previous_manifest_id"] = previous_manifest_id
        manifest["manifest"]["previous_attempt"] = previous_attempt
        manifest["execution"]["previous_failure"] = previous_failure

    for evidence in request.get("evidence", []) or []:
        if not isinstance(evidence, dict):
            raise ManifestError(["evidence entries must be mappings."])
        manifest = apply_gate_evidence(
            root,
            manifest,
            gate=str(evidence.get("gate", "")),
            status=str(evidence.get("status", "")),
            evidence_id=str(evidence.get("id", "")),
            reason=str(evidence.get("reason", "")),
            source_path=evidence.get("source_path"),
            remaining_validation=evidence.get("remaining_validation"),
            failure_reason=evidence.get("failure_reason"),
        )

    validation_errors = validate_manifest(root, manifest)
    if validation_errors:
        raise ManifestError(validation_errors)

    return manifest


def validate_manifest(root: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    index = load_yaml(root / INDEX_PATH)
    graph_contract = load_yaml(root / GRAPH_CONTRACT_PATH)
    quality_contract = load_yaml(root / QUALITY_GATES_PATH)

    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(
            f"Context Manifest schema_version must be {MANIFEST_SCHEMA_VERSION}."
        )

    meta = manifest.get("manifest", {})
    if not isinstance(meta, dict):
        return ["manifest must be a mapping."]
    manifest_id = str(meta.get("id", "")).strip()
    if not manifest_id:
        errors.append("manifest.id is required.")
    if meta.get("graph_kind") != "execution":
        errors.append("manifest.graph_kind must be execution.")
    attempt = meta.get("attempt")
    if not isinstance(attempt, int) or attempt < 1:
        errors.append("manifest.attempt must be an integer >= 1.")
    elif attempt > 1:
        if not meta.get("previous_manifest_id"):
            errors.append("Retry manifest requires previous_manifest_id.")
        if meta.get("previous_attempt") != attempt - 1:
            errors.append("Retry manifest previous_attempt must equal attempt - 1.")

    task = manifest.get("task", {})
    if not isinstance(task, dict):
        return errors + ["task must be a mapping."]
    task_id = str(task.get("id", "")).strip()
    route_id = str(task.get("route", "")).strip()
    if not task_id:
        errors.append("task.id is required.")

    route = _routes(index).get(route_id)
    if route is None:
        errors.append(f"Manifest references unknown route: {route_id}")
        return errors
    errors.extend(_validate_fingerprint(index, route, task.get("fingerprint", {})))

    context_pack_path = str(route.get("context_pack", ""))
    contract_path = str(route.get("task_contract", ""))
    contract = load_yaml(root / Path(contract_path))
    context_pack = load_yaml(root / Path(context_pack_path))

    policy_loaded = manifest.get("policy", {}).get("loaded", [])
    if not any(
        isinstance(item, dict)
        and item.get("source_path") == USER_POLICY_PATH.as_posix()
        for item in policy_loaded
    ):
        errors.append("Context Manifest must record .ai/user-policy.yaml.")

    context = manifest.get("context", {})
    if context.get("context_pack", {}).get("source_path") != context_pack_path:
        errors.append("Context Pack binding does not match canonical route.")

    primary_skill = str(route.get("primary_skill", ""))
    expected_skill_path = f".agents/skills/{primary_skill}/SKILL.md"
    if context.get("primary_skill", {}).get("source_path") != expected_skill_path:
        errors.append("Primary Skill binding does not match canonical route.")

    harness = manifest.get("harness", {})
    if harness.get("task_contract", {}).get("source_path") != contract_path:
        errors.append("Task Contract binding does not match canonical route.")

    if harness.get("risk_level", {}).get("id") != contract.get("risk_level"):
        errors.append("Risk level does not match selected Task Contract.")

    expected_mutations = {
        ("allow", str(rule))
        for rule in contract.get("allowed_mutations", []) or []
    } | {
        ("prohibit", str(rule))
        for rule in contract.get("prohibited_mutations", []) or []
    }
    actual_mutations = {
        (str(item.get("effect")), str(item.get("id")))
        for item in harness.get("mutation_rules", [])
        if isinstance(item, dict)
    }
    missing_mutations = expected_mutations - actual_mutations
    if missing_mutations:
        errors.append(
            f"Manifest is missing Task Contract mutation rules: {sorted(missing_mutations)}"
        )
    for effect, _ in actual_mutations:
        if effect not in MUTATION_EFFECTS:
            errors.append(f"Unsupported mutation effect: {effect}")

    gate_statuses = set(quality_contract.get("result_statuses", []) or [])
    known_gates = set((quality_contract.get("gates", {}) or {}).keys())
    actual_gates: dict[str, dict[str, Any]] = {}
    for gate in harness.get("quality_gates", []) or []:
        if not isinstance(gate, dict) or not gate.get("id"):
            errors.append("quality_gates entries require id.")
            continue
        gate_id = str(gate["id"])
        actual_gates[gate_id] = gate
        if gate_id not in known_gates:
            errors.append(f"Unknown quality gate: {gate_id}")
        requirement = gate.get("requirement")
        if requirement not in GATE_REQUIREMENTS:
            errors.append(f"Unsupported gate requirement: {gate_id}={requirement}")
        status = gate.get("status")
        if status is not None and status not in gate_statuses:
            errors.append(f"Unsupported gate status: {gate_id}={status}")

    for gate_id in contract.get("required_quality_gates", []) or []:
        gate = actual_gates.get(str(gate_id))
        if gate is None or gate.get("requirement") != "required":
            errors.append(f"Missing required quality gate: {gate_id}")
    for gate_id in contract.get("conditional_quality_gates", []) or []:
        gate = actual_gates.get(str(gate_id))
        if gate is None or gate.get("requirement") != "conditional":
            errors.append(f"Missing conditional quality gate: {gate_id}")

    bindings = context.get("bindings", []) or []
    binding_names = {
        str(item.get("name"))
        for item in bindings
        if isinstance(item, dict) and item.get("name")
    }
    unresolved = {
        str(value)
        for value in manifest.get("execution", {}).get("unresolved_bindings", []) or []
    }

    required_context_paths = {
        str(item.get("source_path"))
        for item in context.get("required_context", []) or []
        if isinstance(item, dict) and item.get("source_path")
    }
    conditional_context_paths = {
        str(item.get("source_path"))
        for item in context.get("conditional_context", []) or []
        if isinstance(item, dict) and item.get("source_path")
    }

    for value in context_pack.get("required", []) or []:
        value = str(value)
        if _is_path_reference(value):
            if value not in required_context_paths:
                errors.append(f"Missing required Context Pack source: {value}")
        elif value not in binding_names and value not in unresolved:
            errors.append(
                f"Required Context Pack binding is neither resolved nor unresolved: {value}"
            )

    conditional_map = context_pack.get("conditional", {}) or {}
    for condition in context.get("conditions_applied", []) or []:
        if condition not in conditional_map:
            errors.append(f"Unknown applied Context Pack condition: {condition}")
            continue
        for value in conditional_map.get(condition, []) or []:
            value = str(value)
            if _is_path_reference(value):
                if value not in conditional_context_paths:
                    errors.append(
                        f"Missing conditional Context Pack source for {condition}: {value}"
                    )
            elif value not in binding_names and value not in unresolved:
                errors.append(
                    f"Conditional binding is neither resolved nor unresolved: {value}"
                )

    for required_input in contract.get("required_inputs", []) or []:
        required_input = str(required_input)
        if required_input not in binding_names and required_input not in unresolved:
            errors.append(
                f"Task Contract input is neither resolved nor unresolved: {required_input}"
            )

    loaded_paths = _loaded_paths(manifest)
    for item in context.get("excluded_context", []) or []:
        if not isinstance(item, dict):
            continue
        source_path = str(item.get("source_path", ""))
        if source_path and source_path in loaded_paths:
            errors.append(f"Excluded Context was loaded: {source_path}")

    provenance_reasons = set(
        graph_contract.get("provenance", {}).get("reasons", []) or []
    )
    provenance_lists = [
        policy_loaded,
        manifest.get("project_facts", {}).get("loaded", []),
        context.get("required_context", []),
        context.get("conditional_context", []),
        context.get("source_files", []),
        context.get("excluded_context", []),
        manifest.get("knowledge", {}).get("loaded", []),
        manifest.get("tools", {}).get("activated", []),
        manifest.get("execution", {}).get("evidence", []),
    ]
    for items in provenance_lists:
        for item in items or []:
            if not isinstance(item, dict):
                continue
            reason = item.get("reason")
            if not reason:
                errors.append(
                    f"Missing provenance reason on item: {item.get('node_id') or item}"
                )
            elif reason not in provenance_reasons:
                errors.append(f"Unsupported provenance reason: {reason}")

    for items in provenance_lists:
        local = [
            str(item["node_id"])
            for item in items or []
            if isinstance(item, dict) and item.get("node_id")
        ]
        if len(local) != len(set(local)):
            errors.append("Duplicate stable node_id within one manifest section.")

    execution = manifest.get("execution", {})
    evidence = execution.get("evidence", []) or []
    evidence_ids: set[str] = set()
    for item in evidence:
        if not isinstance(item, dict):
            errors.append("evidence entries must be mappings.")
            continue
        evidence_id = str(item.get("id", "")).strip()
        status = item.get("status")
        gate_id = str(item.get("gate", "")).strip()
        if not evidence_id:
            errors.append("Evidence id is required.")
        elif evidence_id in evidence_ids:
            errors.append(f"Duplicate evidence id: {evidence_id}")
        evidence_ids.add(evidence_id)
        if status not in gate_statuses:
            errors.append(f"Unsupported evidence status: {evidence_id}={status}")
        if gate_id and gate_id not in actual_gates:
            errors.append(f"Evidence references unselected gate: {evidence_id}->{gate_id}")
        if status == "unavailable" and not item.get("remaining_validation"):
            errors.append(
                f"Unavailable evidence requires remaining_validation: {evidence_id}"
            )

    expected_status = derive_execution_status(manifest)
    actual_status = execution.get("status")
    if actual_status not in EXECUTION_STATUSES:
        errors.append(f"Unsupported execution.status: {actual_status}")
    elif actual_status != expected_status:
        errors.append(
            f"execution.status is inconsistent with required gates: "
            f"{actual_status} != {expected_status}"
        )

    projection = manifest.get("graph_projection", {})
    if projection.get("contract") != GRAPH_CONTRACT_PATH.as_posix():
        errors.append("graph_projection.contract must reference .ai/graph-contract.yaml.")
    if projection.get("graph_kind") != "execution":
        errors.append("graph_projection.graph_kind must be execution.")
    for key in (
        "manifest_is_graph_instance",
        "stable_node_ids_required_when_emitted",
        "typed_edges_required",
        "provenance_required",
        "source_of_truth_remains_canonical_yaml",
    ):
        if projection.get(key) is not True:
            errors.append(f"graph_projection.{key} must be true.")

    return errors


def apply_gate_evidence(
    root: Path,
    manifest: dict[str, Any],
    *,
    gate: str,
    status: str,
    evidence_id: str,
    reason: str,
    source_path: str | None = None,
    remaining_validation: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    result = copy.deepcopy(manifest)
    quality_contract = load_yaml(root / QUALITY_GATES_PATH)
    allowed_statuses = set(quality_contract.get("result_statuses", []) or [])

    errors: list[str] = []
    if status not in allowed_statuses:
        errors.append(f"Unsupported gate status: {status}")
    if not gate:
        errors.append("gate is required.")
    if not evidence_id:
        errors.append("evidence_id is required.")
    if not reason:
        errors.append("evidence reason is required.")
    if status == "unavailable" and not remaining_validation:
        errors.append("unavailable evidence requires remaining_validation.")
    if errors:
        raise ManifestError(errors)

    gates = result.get("harness", {}).get("quality_gates", [])
    selected_gate = next(
        (
            item
            for item in gates
            if isinstance(item, dict) and str(item.get("id")) == gate
        ),
        None,
    )
    if selected_gate is None:
        raise ManifestError([f"Gate is not selected by this manifest: {gate}"])
    selected_gate["status"] = status

    evidence_item: dict[str, Any] = {
        "node_id": stable_node_id(
            "evidence", f"{result['manifest']['id']}:{evidence_id}"
        ),
        "id": evidence_id,
        "gate": gate,
        "status": status,
        "reason": reason,
    }
    if source_path:
        evidence_item["source_path"] = str(source_path)
    if remaining_validation:
        evidence_item["remaining_validation"] = str(remaining_validation)

    evidence_list = result.setdefault("execution", {}).setdefault("evidence", [])
    evidence_list[:] = [
        item
        for item in evidence_list
        if not (isinstance(item, dict) and item.get("id") == evidence_id)
    ]
    evidence_list.append(evidence_item)

    if failure_reason:
        result["execution"]["failure_reason"] = str(failure_reason)

    result["execution"]["status"] = derive_execution_status(result)
    return result


def project_execution_graph(
    root: Path,
    manifest: dict[str, Any],
    manifest_source_path: str,
) -> dict[str, Any]:
    validation_errors = validate_manifest(root, manifest)
    if validation_errors:
        raise ManifestError(validation_errors)

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(
        node_id: str,
        node_type: str,
        label: str,
        source_path: str,
        reason: str,
    ) -> None:
        if node_id in nodes:
            return
        nodes[node_id] = {
            "id": node_id,
            "type": node_type,
            "label": label,
            "provenance": {
                "source_path": source_path,
                "reason": reason,
            },
        }

    def add_edge(source: str, target: str, edge_type: str, reason: str) -> None:
        edge = {
            "source": source,
            "target": target,
            "type": edge_type,
            "reason": reason,
        }
        if edge not in edges:
            edges.append(edge)

    meta = manifest["manifest"]
    task = manifest["task"]
    context = manifest["context"]
    harness = manifest["harness"]
    execution = manifest["execution"]

    attempt_id = stable_node_id("attempt", meta["id"])
    task_id = stable_node_id("task", task["id"])
    fingerprint_id = stable_node_id("task_fingerprint", task["id"])
    route_id = stable_node_id("route", task["route"])

    add_node(
        attempt_id,
        "attempt",
        f"Attempt {meta['attempt']}",
        manifest_source_path,
        "runtime_evidence",
    )
    add_node(task_id, "task", task["id"], manifest_source_path, "runtime_evidence")
    add_node(
        fingerprint_id,
        "task_fingerprint",
        "Task Fingerprint",
        manifest_source_path,
        "runtime_evidence",
    )
    add_node(route_id, "route", task["route"], INDEX_PATH.as_posix(), "canonical_binding")

    add_edge(attempt_id, task_id, "depends_on", "runtime_evidence")
    add_edge(task_id, fingerprint_id, "classifies_as", "runtime_evidence")
    add_edge(fingerprint_id, route_id, "selects", "canonical_binding")

    pack = context["context_pack"]
    pack_id = pack["node_id"]
    add_node(pack_id, "context_pack", task["route"], pack["source_path"], "canonical_binding")
    add_edge(route_id, pack_id, "selects", "canonical_binding")

    skill = context["primary_skill"]
    if skill.get("node_id") and skill.get("source_path"):
        add_node(
            skill["node_id"],
            "skill",
            skill["node_id"].split(":", 1)[-1],
            skill["source_path"],
            "canonical_binding",
        )
        add_edge(route_id, skill["node_id"], "uses_skill", "canonical_binding")

    contract = harness["task_contract"]
    contract_id = contract["node_id"]
    add_node(
        contract_id,
        "task_contract",
        contract_id.split(":", 1)[-1],
        contract["source_path"],
        "harness_contract",
    )
    add_edge(route_id, contract_id, "selects", "harness_contract")

    for item in manifest.get("policy", {}).get("loaded", []) or []:
        node_id = item["node_id"]
        add_node(
            node_id,
            "policy",
            node_id.split(":", 1)[-1],
            item["source_path"],
            item["reason"],
        )
        add_edge(task_id, node_id, "applies_policy", item["reason"])

    for key, edge_type in (
        ("required_context", "requires"),
        ("conditional_context", "conditionally_requires"),
        ("source_files", "reads_source"),
        ("excluded_context", "excludes"),
    ):
        for item in context.get(key, []) or []:
            node_id = item["node_id"]
            add_node(
                node_id,
                "source",
                item["source_path"],
                item["source_path"],
                item["reason"],
            )
            add_edge(pack_id, node_id, edge_type, item["reason"])

    for item in manifest.get("knowledge", {}).get("loaded", []) or []:
        node_id = item["node_id"]
        add_node(
            node_id,
            "knowledge",
            item["source_path"],
            item["source_path"],
            item["reason"],
        )
        add_edge(pack_id, node_id, "uses_knowledge", item["reason"])

    risk = harness.get("risk_level", {})
    if risk.get("node_id"):
        add_node(
            risk["node_id"],
            "risk_level",
            str(risk.get("id")),
            RISK_LEVELS_PATH.as_posix(),
            "harness_contract",
        )
        add_edge(contract_id, risk["node_id"], "depends_on", "harness_contract")

    for item in harness.get("mutation_rules", []) or []:
        node_id = item["node_id"]
        add_node(
            node_id,
            "mutation_rule",
            str(item["id"]),
            contract["source_path"],
            "harness_contract",
        )
        edge_type = (
            "allows_mutation" if item["effect"] == "allow" else "prohibits_mutation"
        )
        add_edge(contract_id, node_id, edge_type, "harness_contract")

    for gate in harness.get("quality_gates", []) or []:
        node_id = gate["node_id"]
        add_node(
            node_id,
            "quality_gate",
            str(gate["id"]),
            QUALITY_GATES_PATH.as_posix(),
            "quality_gate",
        )
        edge_type = (
            "requires_gate"
            if gate.get("requirement") == "required"
            else "conditionally_requires"
        )
        add_edge(contract_id, node_id, edge_type, "quality_gate")

    for item in manifest.get("tools", {}).get("activated", []) or []:
        node_id = item["node_id"]
        add_node(
            node_id,
            "tool",
            str(item["id"]),
            MCP_ACTIVATION_PATH.as_posix(),
            item["reason"],
        )
        add_edge(attempt_id, node_id, "uses_tool", item["reason"])

    for item in execution.get("evidence", []) or []:
        node_id = item["node_id"]
        add_node(
            node_id,
            "evidence",
            str(item["id"]),
            item.get("source_path") or manifest_source_path,
            item["reason"],
        )
        add_edge(attempt_id, node_id, "produces_evidence", item["reason"])
        gate_id = item.get("gate")
        if gate_id:
            gate_node = stable_node_id("quality_gate", str(gate_id))
            add_edge(node_id, gate_node, "validates", "quality_gate")

    previous_id = meta.get("previous_manifest_id")
    if previous_id:
        previous_attempt_node = stable_node_id("attempt", str(previous_id))
        add_node(
            previous_attempt_node,
            "attempt",
            f"Previous Attempt {meta.get('previous_attempt')}",
            manifest_source_path,
            "runtime_evidence",
        )
        add_edge(previous_attempt_node, attempt_id, "retries_as", "runtime_evidence")

    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "graph_kind": "execution",
        "manifest_id": meta["id"],
        "root_node": attempt_id,
        "metadata": {
            "task_id": task["id"],
            "route": task["route"],
            "attempt": meta["attempt"],
            "status": execution.get("status"),
        },
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
