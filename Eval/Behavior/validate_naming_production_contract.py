#!/usr/bin/env python3
"""Validate Production Naming policy provenance and observed-source coverage contracts."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
for path in (ROOT, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from derive_signals import derive_signals  # noqa: E402

BOOTSTRAP = ROOT / "AGENTS.md"
ARCH_CONTRACT = ROOT / "Orchestration" / "Contracts" / "TaskContracts" / "architecture-design.yaml"
ARCH_CONTEXT = ROOT / "Context" / "Packs" / "architecture-design.yaml"
PRODUCTION_CONTRACTS = ROOT / "Eval" / "Datasets" / "Behavior" / "production-smoke-contracts.yaml"
ENGINEERING_POLICY_ID = "engineering_principles"
ENGINEERING_POLICY_SOURCE = "Policy/User/user-policy.yaml#core_user_policies.engineering_principles"
ENGINEERING_REFERENCE = "SkillReferences/ENGINEERING_DESIGN_PRINCIPLES.md"


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping: {path}")
    return data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _canonical_ref(value: object) -> str:
    return str(value or "").replace("\\", "/").strip()


def validate_architecture_policy_anchor(errors: list[str]) -> None:
    contract = load_yaml(ARCH_CONTRACT)
    required_clauses = contract.get("required_policy_clauses", []) or []
    matching = [
        item
        for item in required_clauses
        if isinstance(item, dict)
        and item.get("id") == ENGINEERING_POLICY_ID
        and _canonical_ref(item.get("source_path")) == ENGINEERING_POLICY_SOURCE
    ]
    require(
        len(matching) == 1,
        "architecture-design must require exactly one canonical engineering_principles policy clause.",
        errors,
    )
    completion = set(contract.get("completion", []) or [])
    require(
        "engineering_principles_policy_is_applied_and_recorded" in completion,
        "architecture-design completion must record engineering_principles provenance.",
        errors,
    )

    context = load_yaml(ARCH_CONTEXT)
    decisions = ((context.get("metadata", {}) or {}).get("decisions", []) or [])
    require(
        any(
            isinstance(item, dict)
            and _canonical_ref(item.get("source_ref")) == ENGINEERING_POLICY_SOURCE
            for item in decisions
        ),
        "architecture-design context must anchor the canonical engineering_principles clause.",
        errors,
    )
    require(
        ((context.get("rules", {}) or {}).get("engineering_principles_review_required")) is True,
        "architecture-design context must require engineering principles review.",
        errors,
    )
    required_refs = {
        str(item.get("path"))
        for item in context.get("required", []) or []
        if isinstance(item, dict) and item.get("type") == "repository_reference" and item.get("path")
    }
    require(
        ENGINEERING_REFERENCE in required_refs,
        "architecture-design context must include ENGINEERING_DESIGN_PRINCIPLES.md as a required reference.",
        errors,
    )

    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    require(
        "required_policy_clauses" in bootstrap and "Policy provenance" in bootstrap,
        "Bootstrap must require selected-route required_policy_clauses to be recorded as policy provenance.",
        errors,
    )


def validate_naming_production_prompt(errors: list[str]) -> None:
    contracts = load_yaml(PRODUCTION_CONTRACTS)
    cases = contracts.get("cases", {}) or {}
    case = cases.get("GOLDEN-NAMING-001", {}) or {}
    prompt = str(case.get("production_prompt") or "")
    require(case.get("primary_focus") == "naming", "GOLDEN-NAMING-001 primary_focus must remain naming.", errors)
    require("Type Naming Review" in prompt, "Naming Production prompt must explicitly request Type Naming Review.", errors)
    require("既存 CameraDebugger の名前を維持すべきか" in prompt, "Naming Production prompt must review preservation of the existing CameraDebugger name.", errors)
    require("新規 Type が本当に必要か" in prompt, "Naming Production prompt must review whether a new Type is actually necessary.", errors)
    require("新規 Type または Rename を提案する場合だけ" in prompt, "Detailed Type Naming rules must stay conditional on an actual new-Type or Rename proposal.", errors)
    require("必要なら Type Naming" not in prompt, "Ambiguous optional Naming wording must not return to the Production prompt.", errors)


def validate_observed_source_naming_coverage(errors: list[str]) -> None:
    case = {
        "id": "GOLDEN-NAMING-001",
        "expectation": {
            "route": "architecture-design",
            "required_signals": [],
            "forbidden_signals": [],
            "naming": {
                "required_type_names": [],
                "forbidden_type_names": [
                    "MainCameraFarClippingPlaneRuntimeValueChangeNotificationController",
                    "CameraFarClipWatcher",
                ],
                "required_identifiers": [],
                "forbidden_identifiers": [],
                "require_no_new_type": True,
                "require_naming_gate": True,
            },
        },
    }
    artifacts = [
        {
            "path": "CameraDebugger.cs",
            "language": "csharp",
            "kind": "observed_source",
            "source": "namespace Fixture\n{\n    public sealed class CameraDebugger\n    {\n    }\n}\n",
        }
    ]
    derived = derive_signals(
        case,
        {},
        manifest_route="architecture-design",
        response_text="既存 CameraDebugger を維持し、新規 Type は作成しない。",
        diff_text="",
        artifacts=artifacts,
        gates={"architecture_fit": "passed", "file_granularity": "passed"},
    )
    coverage = derived.get("evidence_coverage", {}) or {}
    require(coverage.get("total_invariants") == 4, "Naming regression fixture must expose 4 invariants.", errors)
    require(coverage.get("covered_invariants") == 4, "Observed C# source must cover all naming invariants.", errors)
    require(float(coverage.get("rate", 0.0)) == 1.0, "Observed-source naming evidence coverage must be 1.0.", errors)
    structure = derived.get("structure", {}) or {}
    require(structure.get("observed_type_names") == ["CameraDebugger"], "CameraDebugger must be observed.", errors)
    require(structure.get("new_type_names") == [], "Observed source must not be misclassified as a new Type.", errors)
    require("new_type_created" not in set(derived.get("signals", []) or []), "Observed source must not derive new_type_created.", errors)


def main() -> int:
    errors: list[str] = []
    try:
        validate_architecture_policy_anchor(errors)
        validate_naming_production_prompt(errors)
        validate_observed_source_naming_coverage(errors)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        errors.append(str(exc))

    if errors:
        print("Naming Production contract validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Naming Production contract validation passed: engineering_principles provenance is canonicalized, "
        "the no-new-Type naming review prompt is explicit, and observed C# sources provide complete naming coverage."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
