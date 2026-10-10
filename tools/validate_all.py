#!/usr/bin/env python3
"""Run canonical UnityAgent validation without GitHub Actions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

YAML_ROOTS = (
    Path("src/unityagent/policy"),
    Path("src/unityagent/context"),
    Path("src/unityagent/orchestration"),
    Path("src/unityagent/runtime"),
    Path("src/unityagent/persistence"),
    Path("src/unityagent/operations"),
    Path("eval"),
    Path(".agents"),
)

VALIDATORS = (
    Path("tools/validate_layout.py"),
    Path("tools/policy_validator/validate_user_policy_integrity.py"),
    Path("tools/context_validator/validate_stale_paths.py"),
    Path("tools/orchestration_validator/validate_loops.py"),
    Path("src/unityagent/runtime/contracts/capability_contract.py"),
    Path("tools/validate_catalog_import_gate.py"),
    Path("tools/production_tool_runtime/validate_production_tool_runtime.py"),
    Path("tools/layer_boundary_validator/validate_layer_boundaries.py"),
    Path("tools/repository_authority_validator/validate_repository_authority.py"),
    Path("tools/branch_policy/validate_branch_policy.py"),
    Path("tools/documentation_validator/validate_documentation.py"),
    Path("tools/context_explorer/validate.py"),
    Path("tools/skill_validator/validate_skills.py"),
    Path("tools/skill_eval/validate_skill_evals.py"),
    Path("tools/contract_validator/validate_contracts.py"),
    Path("tools/context_pack_validator/validate_context_packs.py"),
    Path("eval/golden/validate_gate_catalog.py"),
    Path("eval/golden/validate_required_knowledge.py"),
    Path("eval/golden/validate_golden_tasks.py"),
    Path("eval/golden/validate_naming_grader.py"),
    Path("eval/golden/validate_typed_context_v3.py"),
    Path("eval/golden/validate_context_budget_v1.py"),
    Path("eval/behavior/validate_behavior_eval.py"),
    Path("eval/behavior/validate_policy_provenance.py"),
    Path("eval/behavior/validate_naming_production_contract.py"),
    Path("eval/behavior/validate_mutation_production_contract.py"),
    Path("eval/behavior/validate_production_smoke.py"),
    Path("eval/behavior/validate_run_integrity.py"),
    Path("eval/behavior/validate_cutover.py"),
)

CHECK_COMMANDS = (
    (
        "parent-graph-mermaid",
        [sys.executable, str(ROOT / "tools/graph_visualization/generate_parent_graph_mermaid.py"), "--check"],
    ),
)

TEST_SUITES = (
    Path("tests/packaging"),
    Path("tests/policy"),
    Path("tests/context"),
    Path("tests/runtime"),
    Path("tests/runtime/reference_implementation"),
    Path("tests/orchestration"),
    Path("tests/persistence"),
    Path("tests/eval"),
    Path("tests/operations"),
    Path("tests/context_explorer"),
    Path("tests/architecture"),
    Path("tests/content_pilot"),
)


def validate_yaml() -> list[str]:
    errors: list[str] = []
    for relative_root in YAML_ROOTS:
        root = ROOT / relative_root
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.yaml")):
            try:
                with path.open(encoding="utf-8") as stream:
                    yaml.safe_load(stream)
            except Exception as exc:
                errors.append(f"{path.relative_to(ROOT)}: {exc}")
    return errors


def run_command(label: str, command: list[str]) -> int:
    print(f"\n== {label} ==")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def main() -> int:
    # Tests exercise the current authored definitions through the wheel resource API.
    if run_command("package-resource-refresh", [sys.executable, str(ROOT / "setup.py"), "build_resources"]) != 0:
        return 1
    yaml_errors = validate_yaml()
    if yaml_errors:
        print("YAML syntax validation failed:")
        for error in yaml_errors:
            print(f"- {error}")
        return 1
    print("YAML syntax validation passed.")

    failed: list[str] = []
    for validator in VALIDATORS:
        full_path = ROOT / validator
        if not full_path.is_file():
            failed.append(f"missing:{validator}")
            continue
        command = [sys.executable, str(full_path)]
        if validator.name == "capability_contract.py":
            command.extend(["--root", str(ROOT)])
        if run_command(str(validator), command) != 0:
            failed.append(str(validator))

    for label, command in CHECK_COMMANDS:
        if run_command(label, command) != 0:
            failed.append(label)

    for suite in TEST_SUITES:
        full_path = ROOT / suite
        if not full_path.is_dir():
            failed.append(f"missing:{suite}")
            continue
        label = f"unittest:{suite}"
        command = [sys.executable, "-m", "unittest", "discover", "-s", str(suite), "-p", "test_*.py"]
        if run_command(label, command) != 0:
            failed.append(label)

    if failed:
        print("\nUnityAgent local validation failed:")
        for item in failed:
            print(f"- {item}")
        return 1

    print("\nUnityAgent canonical local validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
