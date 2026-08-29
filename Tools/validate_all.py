#!/usr/bin/env python3
"""Run canonical UnityAgent validation without GitHub Actions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

YAML_ROOTS = (
    Path("Policy"),
    Path("Context"),
    Path("Orchestration"),
    Path("Runtime"),
    Path("Persistence"),
    Path("Operations"),
    Path("Eval"),
    Path(".agents"),
)

VALIDATORS = (
    Path("Policy/Validators/validate_user_policy_integrity.py"),
    Path("Context/Validators/validate_stale_paths.py"),
    Path("Tools/SkillValidator/validate_skills.py"),
    Path("Tools/SkillEval/validate_skill_evals.py"),
    Path("Tools/ContractValidator/validate_contracts.py"),
    Path("Tools/ContextPackValidator/validate_context_packs.py"),
    Path("Eval/Golden/validate_gate_catalog.py"),
    Path("Eval/Golden/validate_required_knowledge.py"),
    Path("Eval/Golden/validate_golden_tasks.py"),
    Path("Eval/Golden/validate_naming_grader.py"),
    Path("Eval/Golden/validate_typed_context_v3.py"),
    Path("Eval/Golden/validate_context_budget_v1.py"),
    Path("Eval/Behavior/validate_behavior_eval.py"),
    Path("Eval/Behavior/validate_policy_provenance.py"),
    Path("Eval/Behavior/validate_naming_production_contract.py"),
    Path("Eval/Behavior/validate_mutation_production_contract.py"),
    Path("Eval/Behavior/validate_production_smoke.py"),
    Path("Eval/Behavior/validate_run_integrity.py"),
    Path("Eval/Behavior/validate_phase8_cutover.py"),
)

TEST_SUITES = (
    Path("Policy/Tests"),
    Path("Context/Tests"),
    Path("Runtime/Tests"),
    Path("Orchestration/Tests"),
    Path("Persistence/Tests"),
    Path("Eval/Tests"),
    Path("Operations/Tests"),
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
            except Exception as exc:  # noqa: BLE001 - report parser failure with file path.
                errors.append(f"{path.relative_to(ROOT)}: {exc}")
    return errors


def run_command(label: str, command: list[str]) -> int:
    print(f"\n== {label} ==")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def main() -> int:
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
        if run_command(str(validator), [sys.executable, str(full_path)]) != 0:
            failed.append(str(validator))

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
