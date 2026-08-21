#!/usr/bin/env python3
"""Validate UnityAgent Task Fingerprint routing contracts and regression cases."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


INDEX_PATH = Path(".ai/context-index.yaml")
CASES_PATH = Path("Tests/ContextRouting/cases.yaml")


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    index_path = root / INDEX_PATH
    cases_path = root / CASES_PATH

    if not index_path.is_file():
        return [f"Missing file: {INDEX_PATH}"]
    if not cases_path.is_file():
        return [f"Missing file: {CASES_PATH}"]

    index = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    cases_doc = yaml.safe_load(cases_path.read_text(encoding="utf-8")) or {}

    routing_rules = index.get("routing_rules", {})
    if routing_rules.get("task_fingerprint_required_before_domain_route") is not True:
        errors.append("Task Fingerprint must be required before domain routing.")
    if routing_rules.get("route_match_uses_fingerprint_not_trigger_strings") is not True:
        errors.append("Route matching must use Task Fingerprint instead of trigger strings.")
    if routing_rules.get("unknown_dimensions_must_not_be_guessed") is not True:
        errors.append("Unknown Task Fingerprint dimensions must not be guessed.")

    fingerprint = index.get("task_fingerprint")
    if not isinstance(fingerprint, dict):
        return errors + ["Missing task_fingerprint contract in context-index.yaml"]

    dimensions = fingerprint.get("dimensions", {})
    required_dimensions = fingerprint.get("required_dimensions", [])
    if not isinstance(dimensions, dict) or not dimensions:
        errors.append("task_fingerprint.dimensions must define allowed values.")
        dimensions = {}

    for dimension in required_dimensions:
        if dimension not in dimensions:
            errors.append(f"Required fingerprint dimension is undefined: {dimension}")

    routes = index.get("routes", {})
    if not isinstance(routes, dict) or not routes:
        return errors + ["No canonical routes found."]

    route_by_id: dict[str, dict] = {}
    for mapping_key, route in routes.items():
        if not isinstance(route, dict):
            errors.append(f"Route {mapping_key} must be a mapping.")
            continue

        route_id = route.get("id")
        if not route_id:
            errors.append(f"Route {mapping_key} has no id.")
            continue
        route_by_id[route_id] = route

        if "triggers" in route:
            errors.append(f"Route {route_id} still contains trigger-string routing.")

        match = route.get("fingerprint_match")
        if not isinstance(match, dict) or not match:
            errors.append(f"Route {route_id} has no fingerprint_match contract.")
            continue

        for dimension, accepted_values in match.items():
            if dimension not in dimensions:
                errors.append(f"Route {route_id} uses unknown fingerprint dimension: {dimension}")
                continue
            if not isinstance(accepted_values, list) or not accepted_values:
                errors.append(f"Route {route_id}.{dimension} must contain accepted values.")
                continue

            allowed_values = set(dimensions[dimension])
            for value in accepted_values:
                if value not in allowed_values:
                    errors.append(
                        f"Route {route_id}.{dimension} contains unsupported value: {value}"
                    )

    cases = cases_doc.get("cases", [])
    if not isinstance(cases, list):
        return errors + ["Tests/ContextRouting/cases.yaml cases must be a list."]

    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("id", "<unknown>")
        expected_route = case.get("expected_route")
        expected_fingerprint = case.get("expected_fingerprint")

        if expected_fingerprint is not None:
            if not isinstance(expected_fingerprint, dict):
                errors.append(f"{case_id}: expected_fingerprint must be a mapping.")
            else:
                for dimension, value in expected_fingerprint.items():
                    if dimension not in dimensions:
                        errors.append(f"{case_id}: unknown fingerprint dimension: {dimension}")
                        continue
                    if value not in dimensions[dimension]:
                        errors.append(
                            f"{case_id}: unsupported fingerprint value {dimension}={value}"
                        )

        if not expected_route:
            continue

        route = route_by_id.get(expected_route)
        if route is None:
            errors.append(f"{case_id}: expected route does not exist: {expected_route}")
            continue
        if not isinstance(expected_fingerprint, dict):
            errors.append(f"{case_id}: routed case requires expected_fingerprint.")
            continue

        match = route.get("fingerprint_match", {})
        for dimension, accepted_values in match.items():
            if dimension not in expected_fingerprint:
                errors.append(
                    f"{case_id}: expected_fingerprint lacks route-match dimension: {dimension}"
                )
                continue
            value = expected_fingerprint[dimension]
            if value not in accepted_values:
                errors.append(
                    f"{case_id}: {dimension}={value} does not match route {expected_route}: "
                    f"{accepted_values}"
                )

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate(root)

    if errors:
        print("Task Fingerprint validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Task Fingerprint validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
