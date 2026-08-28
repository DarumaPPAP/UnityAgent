#!/usr/bin/env python3
"""Validate Production MUTATION contract against the phase11-mutation-01 failure mode."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BEHAVIOR_EVAL = ROOT / "Tools" / "BehaviorEval"
if str(BEHAVIOR_EVAL) not in sys.path:
    sys.path.insert(0, str(BEHAVIOR_EVAL))

from derive_signals import derive_signals  # noqa: E402

TASK_CONTRACT = ROOT / ".ai" / "harness" / "task-contracts" / "csharp-local-fix.yaml"
CONTEXT_PACK = ROOT / ".ai" / "context-packs" / "csharp-local-fix.yaml"
SAFE_PATCH_SKILL = ROOT / ".agents" / "skills" / "csharp-safe-patch" / "SKILL.md"
GOLDEN_CASES = ROOT / "Tests" / "GoldenTasks" / "cases.yaml"
SUITES = ROOT / "Tests" / "BehaviorEval" / "suites.yaml"
PRODUCTION_CONTRACTS = ROOT / "Tests" / "BehaviorEval" / "production-smoke-contracts.yaml"
FIXTURE_SOURCE = ROOT / "Tests" / "BehaviorEval" / "Fixtures" / "LocalPatch" / "CameraDebugger.cs"

REQUIRED_POLICIES = {
    "single_purpose_change": ".ai/user-policy.yaml#core_user_policies.single_purpose_change",
    "preserve_existing_structure": ".ai/user-policy.yaml#core_user_policies.preserve_existing_structure",
}


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping: {path}")
    return data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def golden_mutation_case() -> dict:
    for case in load_yaml(GOLDEN_CASES).get("cases", []) or []:
        if isinstance(case, dict) and case.get("id") == "GOLDEN-MUTATION-001":
            return case
    raise ValueError("GOLDEN-MUTATION-001 is missing.")


def production_suite_case() -> dict:
    suite = ((load_yaml(SUITES).get("suites", {}) or {}).get("production_smoke", {}) or {})
    for case in suite.get("cases", []) or []:
        if isinstance(case, dict) and case.get("golden_task_id") == "GOLDEN-MUTATION-001":
            return case
    raise ValueError("production_smoke/GOLDEN-MUTATION-001 is missing.")


def validate_policy_and_input_contract(errors: list[str]) -> None:
    contract = load_yaml(TASK_CONTRACT)
    required_inputs = set(contract.get("required_inputs", []) or [])
    require(required_inputs == {"goal_or_confirmed_error", "target_source"},
            "csharp-local-fix must keep only goal/error and target source as unconditional inputs.", errors)

    conditional = contract.get("conditional_inputs", {}) or {}
    require("unity_version" in conditional,
            "Unity version must be conditional for API-sensitive fixes.", errors)
    require("direct_dependencies" in conditional,
            "Direct callers/interfaces must be conditional for cross-boundary fixes.", errors)

    required_clauses = contract.get("required_policy_clauses", []) or []
    actual = {
        str(item.get("id")): str(item.get("source_path"))
        for item in required_clauses
        if isinstance(item, dict) and item.get("id") and item.get("source_path")
    }
    require(actual == REQUIRED_POLICIES,
            "csharp-local-fix must require exactly single_purpose_change and preserve_existing_structure with canonical provenance.", errors)

    completion = set(contract.get("completion", []) or [])
    require("single_purpose_change_policy_is_applied_and_recorded" in completion,
            "Completion must record single_purpose_change provenance.", errors)
    require("preserve_existing_structure_policy_is_applied_and_recorded" in completion,
            "Completion must record preserve_existing_structure provenance.", errors)


def validate_context_and_skill_fast_path(errors: list[str]) -> None:
    context = load_yaml(CONTEXT_PACK)
    required = context.get("required", []) or []
    required_bindings = {
        str(item.get("name"))
        for item in required
        if isinstance(item, dict) and item.get("type") == "binding" and item.get("name")
    }
    required_refs = {
        str(item.get("path"))
        for item in required
        if isinstance(item, dict) and item.get("type") == "repository_reference" and item.get("path")
    }
    require(required_bindings == {"target_source"},
            "csharp-local-fix context must not require direct callers for every local patch.", errors)
    require(".ai/user-policy.yaml" in required_refs,
            "csharp-local-fix context must include the authoritative user policy.", errors)

    rules = context.get("rules", {}) or {}
    require(rules.get("single_purpose_change") is True,
            "Context must preserve single-purpose mutation scope.", errors)
    require(rules.get("preserve_existing_structure") is True,
            "Context must preserve existing structure.", errors)
    require(rules.get("confirmed_local_compile_error_can_use_source_fast_path") is True,
            "Context must allow the confirmed local compile-error fast path.", errors)

    skill = SAFE_PATCH_SKILL.read_text(encoding="utf-8")
    require("User-confirmed local compile error fast path" in skill,
            "csharp-safe-patch must define the user-confirmed local compile-error fast path.", errors)
    require("Sourceから一意に確認済みの安全な局所Patchそのものを拒否しない" in skill,
            "Compile unavailability must not by itself block a source-proven safe local patch.", errors)
    require("Compile未実行をCompile PASSとして報告しない" in skill,
            "Safe-patch skill must keep compile evidence honest.", errors)


def validate_production_fixture_and_no_leak(errors: list[str]) -> None:
    fixture = FIXTURE_SOURCE.read_text(encoding="utf-8")
    require("_missingFarClipValue" in fixture and "_farClipValue" in fixture,
            "LocalPatch fixture must preserve one locally inspectable compile-error relationship.", errors)

    contracts = (load_yaml(PRODUCTION_CONTRACTS).get("cases", {}) or {})
    production = contracts.get("GOLDEN-MUTATION-001", {}) or {}
    prompt = str(production.get("production_prompt") or "")
    require(prompt.strip() != "", "Mutation Production prompt must exist.", errors)
    for leaked in ("_missingFarClipValue", "_farClipValue", "FarClip => _farClipValue"):
        require(leaked not in prompt, f"Mutation Production prompt leaks the patch answer: {leaked}", errors)

    suite_case = production_suite_case()
    require(suite_case.get("allowed_paths") == ["CameraDebugger.cs"],
            "Mutation Production case must allow exactly CameraDebugger.cs.", errors)
    require(str(suite_case.get("work_kind")) == "implementation",
            "Mutation Production case must execute as implementation work.", errors)


def validate_bounded_patch_signal(errors: list[str]) -> None:
    case = golden_mutation_case()
    suite_case = production_suite_case()
    before = FIXTURE_SOURCE.read_text(encoding="utf-8")
    after = before.replace("_missingFarClipValue", "_farClipValue")
    require(after != before, "Mutation fixture simulation must produce one patch.", errors)

    diff = """diff --git a/CameraDebugger.cs b/CameraDebugger.cs
--- a/CameraDebugger.cs
+++ b/CameraDebugger.cs
@@ -5,5 +5,5 @@ public sealed class CameraDebugger
     private float _farClipValue = 1000f;
 
     // Behavior Eval fixture: this symbol is intentionally invalid so the local-fix task has one bounded compile error.
-    public float FarClip => _missingFarClipValue;
+    public float FarClip => _farClipValue;
 }
"""
    derived = derive_signals(
        case,
        suite_case,
        manifest_route="csharp-local-fix",
        response_text="既知Compile ErrorだけをCameraDebugger.cs内で最小修正した。",
        diff_text=diff,
        artifacts=[{
            "path": "CameraDebugger.cs",
            "language": "csharp",
            "kind": "modified_source",
            "source": after,
        }],
        gates={"static_review": "passed", "compile": "passed"},
    )
    signals = set(derived.get("signals", []) or [])
    require("bounded_patch" in signals, "A one-file allowed mutation must derive bounded_patch.", errors)
    for forbidden in ("unrelated_refactor", "unrelated_rename", "public_contract_change"):
        require(forbidden not in signals, f"Bounded patch must not derive forbidden signal: {forbidden}", errors)

    structure = derived.get("structure", {}) or {}
    require(structure.get("changed_paths") == ["CameraDebugger.cs"],
            "Mutation structure must report exactly CameraDebugger.cs as changed.", errors)
    require(structure.get("new_type_names") == [],
            "Bounded local patch must not appear as a new Type.", errors)

    coverage = derived.get("evidence_coverage", {}) or {}
    require(coverage.get("covered_invariants") == 5 and coverage.get("total_invariants") == 5,
            "Mutation fixture must cover all 5 deterministic invariants.", errors)
    require(float(coverage.get("rate", 0.0)) == 1.0,
            "Mutation Production evidence coverage must be 1.0.", errors)


def main() -> int:
    errors: list[str] = []
    try:
        validate_policy_and_input_contract(errors)
        validate_context_and_skill_fast_path(errors)
        validate_production_fixture_and_no_leak(errors)
        validate_bounded_patch_signal(errors)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        errors.append(str(exc))

    if errors:
        print("Mutation Production contract validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Mutation Production contract validation passed: bounded local compile-error fixes have canonical policy provenance, "
        "conditional context inputs, no Golden leak, and 5/5 deterministic patch evidence."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
