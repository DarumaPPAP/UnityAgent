#!/usr/bin/env python3
"""Validate UnityAgent Golden Regression task definitions."""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "Tests" / "GoldenTasks" / "cases.yaml"
CONTRACT_PATH = ROOT / ".ai" / "eval" / "golden-eval-contract.yaml"
POLICY_PATH = ROOT / ".ai" / "user-policy.yaml"
INDEX_PATH = ROOT / ".ai" / "context-index.yaml"
GRAPH_PATH = ROOT / ".ai" / "graph-contract.yaml"
NAMING_GATE = "namespace_and_type_naming_review"
NAMING_POLICY = "semantic_type_naming"
NAMING_GRADER = "type_naming"


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping: {path}")
    return data


def _as_string_set(value: object, case_id: str, field: str, errors: list[str]) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list):
        errors.append(f"{case_id}: {field} must be a list.")
        return set()
    result: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{case_id}: {field} contains a non-string or empty value.")
            continue
        result.add(item)
    return result


def validate_naming_expectation(
    case_id: str,
    expectation: dict,
    graders: list,
    route_contract: dict | None,
    errors: list[str],
) -> None:
    naming = expectation.get("naming")
    if not isinstance(naming, dict):
        errors.append(f"{case_id}: naming category requires expectation.naming mapping.")
        return

    required_type_names = _as_string_set(
        naming.get("required_type_names", []), case_id, "expectation.naming.required_type_names", errors
    )
    forbidden_type_names = _as_string_set(
        naming.get("forbidden_type_names", []), case_id, "expectation.naming.forbidden_type_names", errors
    )
    required_identifiers = _as_string_set(
        naming.get("required_identifiers", []), case_id, "expectation.naming.required_identifiers", errors
    )
    forbidden_identifiers = _as_string_set(
        naming.get("forbidden_identifiers", []), case_id, "expectation.naming.forbidden_identifiers", errors
    )

    type_overlap = required_type_names & forbidden_type_names
    if type_overlap:
        errors.append(f"{case_id}: naming Type names cannot be both required and forbidden: {sorted(type_overlap)}")
    identifier_overlap = required_identifiers & forbidden_identifiers
    if identifier_overlap:
        errors.append(
            f"{case_id}: naming identifiers cannot be both required and forbidden: {sorted(identifier_overlap)}"
        )

    require_no_new_type = naming.get("require_no_new_type", False)
    if not isinstance(require_no_new_type, bool):
        errors.append(f"{case_id}: expectation.naming.require_no_new_type must be boolean.")
    elif require_no_new_type and required_type_names:
        errors.append(f"{case_id}: require_no_new_type conflicts with required_type_names.")

    require_naming_gate = naming.get("require_naming_gate", True)
    if not isinstance(require_naming_gate, bool):
        errors.append(f"{case_id}: expectation.naming.require_naming_gate must be boolean.")
        require_naming_gate = True

    required_policies = set(expectation.get("required_policies", []) or [])
    if NAMING_POLICY not in required_policies:
        errors.append(f"{case_id}: naming case must require user policy {NAMING_POLICY}.")

    required_gates = set(expectation.get("required_gates", []) or [])
    if require_naming_gate and NAMING_GATE not in required_gates:
        errors.append(f"{case_id}: naming case must require gate {NAMING_GATE}.")

    if route_contract is not None:
        route_gates = set(route_contract.get("required_quality_gates", []) or []) | set(
            route_contract.get("conditional_quality_gates", []) or []
        )
        if NAMING_GATE not in route_gates:
            errors.append(f"{case_id}: route Task Contract does not declare {NAMING_GATE}.")

    if not any(
        isinstance(grader, dict)
        and grader.get("type") == "deterministic"
        and grader.get("id") == NAMING_GRADER
        for grader in graders or []
    ):
        errors.append(f"{case_id}: naming case requires deterministic grader id {NAMING_GRADER}.")


def main() -> int:
    errors: list[str] = []
    try:
        suite = load_yaml(CASES_PATH)
        contract = load_yaml(CONTRACT_PATH)
        policy = load_yaml(POLICY_PATH)
        index = load_yaml(INDEX_PATH)
        graph = load_yaml(GRAPH_PATH)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Golden Task validation failed:\n- {exc}")
        return 1

    cases = suite.get("cases", [])
    if not isinstance(cases, list):
        errors.append("cases must be a list.")
        cases = []

    minimum_cases = int(contract.get("initial_suite", {}).get("minimum_cases", 20))
    if len(cases) < minimum_cases:
        errors.append(f"Golden suite requires at least {minimum_cases} cases; found {len(cases)}.")

    ids = [str(case.get("id", "")) for case in cases if isinstance(case, dict)]
    duplicates = [case_id for case_id, count in Counter(ids).items() if case_id and count > 1]
    for case_id in duplicates:
        errors.append(f"Duplicate Golden Task id: {case_id}")

    routes = {
        str(route.get("id"))
        for route in (index.get("routes", {}) or {}).values()
        if isinstance(route, dict) and route.get("id")
    }
    policies = set((policy.get("core_user_policies", {}) or {}).keys())
    gate_ids: set[str] = set()
    quality_path = ROOT / ".ai" / "harness" / "quality-gates.yaml"
    try:
        gate_ids = set((load_yaml(quality_path).get("gates", {}) or {}).keys())
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Failed to load quality gates: {exc}")

    pairs: dict[str, list[str]] = defaultdict(list)
    pair_boundaries: dict[str, set[str]] = defaultdict(set)
    categories: set[str] = set()

    for index_no, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            errors.append(f"Case #{index_no} must be a mapping.")
            continue
        case_id = str(case.get("id", "")).strip()
        pair_id = str(case.get("pair_id", "")).strip()
        boundary = str(case.get("boundary", "")).strip()
        category = str(case.get("category", "")).strip()
        expectation = case.get("expectation", {})
        graders = case.get("graders", [])

        if not case_id:
            errors.append(f"Case #{index_no} missing id.")
        if case.get("kind") != "regression":
            errors.append(f"{case_id}: kind must be regression.")
        if not pair_id:
            errors.append(f"{case_id}: pair_id is required.")
        else:
            pairs[pair_id].append(case_id)
            pair_boundaries[pair_id].add(boundary)
        if boundary not in {"require", "forbid"}:
            errors.append(f"{case_id}: boundary must be require or forbid.")
        if category:
            categories.add(category)

        if not isinstance(expectation, dict):
            errors.append(f"{case_id}: expectation must be a mapping.")
            continue
        route = expectation.get("route")
        if route and route not in routes:
            errors.append(f"{case_id}: unknown route {route}.")
        route_contract = None
        if route in routes:
            for route_def in (index.get("routes", {}) or {}).values():
                if isinstance(route_def, dict) and route_def.get("id") == route:
                    contract_path = route_def.get("task_contract")
                    if contract_path:
                        try:
                            route_contract = load_yaml(ROOT / str(contract_path))
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"{case_id}: failed to load route Task Contract: {exc}")
                    break
        for rule in expectation.get("required_policies", []) or []:
            if rule not in policies:
                errors.append(f"{case_id}: unknown user policy {rule}.")

        contract_gates: set[str] = set()
        contract_knowledge: set[str] = set()
        if route_contract is not None:
            contract_gates = set(route_contract.get("required_quality_gates", []) or []) | set(
                route_contract.get("conditional_quality_gates", []) or []
            )
            contract_knowledge = set(route_contract.get("required_knowledge", []) or [])
        for gate in expectation.get("required_gates", []) or []:
            if gate not in gate_ids:
                errors.append(f"{case_id}: unknown quality gate {gate}.")
            if route_contract is not None and gate not in contract_gates:
                errors.append(f"{case_id}: gate {gate} is not declared by route Task Contract {route}.")
        expected_knowledge = set(expectation.get("required_knowledge", []) or [])
        if route_contract is not None and not expected_knowledge.issubset(contract_knowledge):
            errors.append(
                f"{case_id}: expected required_knowledge is not declared by route Task Contract: "
                f"{sorted(expected_knowledge - contract_knowledge)}"
            )

        required = set(expectation.get("required_signals", []) or [])
        forbidden = set(expectation.get("forbidden_signals", []) or [])
        overlap = required & forbidden
        if overlap:
            errors.append(f"{case_id}: signals cannot be both required and forbidden: {sorted(overlap)}")
        if expectation.get("outcome") != "passed":
            errors.append(f"{case_id}: regression expectation outcome must be passed.")
        if not any(isinstance(grader, dict) and grader.get("type") == "deterministic" for grader in graders or []):
            errors.append(f"{case_id}: at least one deterministic grader is required.")

        if category == "naming":
            validate_naming_expectation(case_id, expectation, graders, route_contract, errors)

    minimum_pairs = int(contract.get("initial_suite", {}).get("minimum_boundary_pairs", 8))
    valid_pairs = 0
    for pair_id, members in sorted(pairs.items()):
        if len(members) < 2:
            errors.append(f"Boundary pair {pair_id} has fewer than two cases.")
        if pair_boundaries[pair_id] != {"require", "forbid"}:
            errors.append(f"Boundary pair {pair_id} must contain require and forbid cases.")
        else:
            valid_pairs += 1
    if valid_pairs < minimum_pairs:
        errors.append(f"Golden suite requires at least {minimum_pairs} complete boundary pairs; found {valid_pairs}.")

    required_categories = set(contract.get("initial_suite", {}).get("target_categories", []) or [])
    missing_categories = required_categories - categories
    if missing_categories:
        errors.append(f"Golden suite missing target categories: {sorted(missing_categories)}")

    node_types = set(graph.get("node_types", []) or [])
    edge_types = set(graph.get("edge_types", []) or [])
    views = set(graph.get("visualization_contract", {}).get("required_views", []) or [])
    for node_type in ("golden_task", "grader", "regression_result"):
        if node_type not in node_types:
            errors.append(f"Graph contract missing Phase 7 node type: {node_type}")
    for edge_type in ("expects", "evaluated_by", "produces_regression_result", "compares_to"):
        if edge_type not in edge_types:
            errors.append(f"Graph contract missing Phase 7 edge type: {edge_type}")
    if "regression" not in views:
        errors.append("Graph contract missing regression visualization view.")

    if errors:
        print("Golden Task validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Golden Task validation passed: {len(cases)} cases / {valid_pairs} boundary pairs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
