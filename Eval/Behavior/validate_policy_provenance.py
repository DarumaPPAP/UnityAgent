#!/usr/bin/env python3
"""Regression validation for canonical policy provenance normalization."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
for path in (ROOT, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from normalize_result import BehaviorEvidenceError, _canonical_node_id  # noqa: E402

FIXTURE = ROOT / "Eval" / "Datasets" / "Behavior" / "ProtocolFixtures" / "qualified-policy-fragment.yaml"
MINIMUM_COHESIVE_SOURCE = "Policy/User/user-policy.yaml#core_user_policies.minimum_cohesive_solution_first"
SEMANTIC_NAMING_SOURCE = "Policy/User/user-policy.yaml#core_user_policies.semantic_type_naming"


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
            # Historical fixture provenance may retain the legacy source path; the
            # semantic contract is the canonical leaf clause identity.
            require(
                _canonical_node_id(loaded[0], "policy") == "minimum_cohesive_solution_first",
                "full dotted YAML fragment must normalize to the canonical leaf clause id",
                errors,
            )
    except (OSError, yaml.YAMLError, BehaviorEvidenceError) as exc:
        errors.append(f"phase11-naming-03 regression fixture failed: {exc}")

    for source, expected in (
        (MINIMUM_COHESIVE_SOURCE, "minimum_cohesive_solution_first"),
        (SEMANTIC_NAMING_SOURCE, "semantic_type_naming"),
    ):
        try:
            derived = _canonical_node_id({"id": "", "source_path": source}, "policy")
            require(derived == expected, f"canonical policy leaf derivation drifted: {expected}", errors)
        except BehaviorEvidenceError as exc:
            errors.append(f"canonical fragment leaf derivation failed: {exc}")

    try:
        _canonical_node_id(
            {"id": "minimum_cohesive_solution_first", "source_path": SEMANTIC_NAMING_SOURCE},
            "policy",
        )
        errors.append("mismatched policy id and fragment leaf must be rejected")
    except BehaviorEvidenceError:
        pass

    try:
        prefixed = _canonical_node_id(
            {"id": "policy:semantic_type_naming", "source_path": SEMANTIC_NAMING_SOURCE},
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
        "Policy provenance validation passed: historical fixture leaf identity plus canonical provenance, "
        "leaf derivation, mismatch rejection, and policy prefix normalization."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
