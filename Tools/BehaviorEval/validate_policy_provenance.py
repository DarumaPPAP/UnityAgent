#!/usr/bin/env python3
"""Regression validation for canonical policy provenance normalization."""

from __future__ import annotations

from pathlib import Path

import yaml

from normalize_result import BehaviorEvidenceError, _canonical_node_id


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "Tests" / "BehaviorEval" / "ProtocolFixtures" / "qualified-policy-fragment.yaml"


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []

    try:
        fixture = yaml.safe_load(FIXTURE.read_text(encoding="utf-8")) or {}
        loaded = ((fixture.get("policy", {}) or {}).get("loaded", []) or [])
        require(len(loaded) == 1, "qualified policy regression fixture must contain exactly one policy", errors)
        if loaded:
            require(
                _canonical_node_id(loaded[0], "policy") == "minimum_cohesive_solution_first",
                "full dotted YAML fragment must normalize to the canonical leaf clause id",
                errors,
            )
    except (OSError, yaml.YAMLError, BehaviorEvidenceError) as exc:
        errors.append(f"phase11-naming-03 regression fixture failed: {exc}")

    try:
        derived = _canonical_node_id(
            {
                "id": "",
                "source_path": ".unityagent-control/.ai/user-policy.yaml#core_user_policies.semantic_type_naming",
            },
            "policy",
        )
        require(derived == "semantic_type_naming", "missing policy id must derive from fragment leaf", errors)
    except BehaviorEvidenceError as exc:
        errors.append(f"fragment leaf derivation failed: {exc}")

    try:
        _canonical_node_id(
            {
                "id": "minimum_cohesive_solution_first",
                "source_path": ".unityagent-control/.ai/user-policy.yaml#core_user_policies.semantic_type_naming",
            },
            "policy",
        )
        errors.append("mismatched policy id and fragment leaf must be rejected")
    except BehaviorEvidenceError:
        pass

    try:
        prefixed = _canonical_node_id(
            {
                "id": "policy:semantic_type_naming",
                "source_path": ".unityagent-control/.ai/user-policy.yaml#core_user_policies.semantic_type_naming",
            },
            "policy",
        )
        require(prefixed == "semantic_type_naming", "policy: prefix normalization drifted", errors)
    except BehaviorEvidenceError as exc:
        errors.append(f"policy prefix normalization failed: {exc}")

    if errors:
        print("Policy provenance validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Policy provenance validation passed: full YAML fragment -> canonical leaf id, "
        "leaf derivation, mismatch rejection, and policy prefix normalization."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
