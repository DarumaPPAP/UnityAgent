#!/usr/bin/env python3
"""Run UnityAgent contract validation without GitHub Actions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

YAML_ROOTS = (
    Path(".ai"),
    Path("Tests/ContractValidator"),
    Path("Tests/ContextRouting"),
    Path("Tests/SkillRouting"),
    Path("Tests/SkillEvals"),
)

VALIDATORS = (
    Path("Tools/SkillValidator/validate_skills.py"),
    Path("Tools/SkillEval/validate_skill_evals.py"),
    Path("Tools/ContractValidator/validate_contracts.py"),
    Path("Tools/ContextPackValidator/validate_context_packs.py"),
    Path("Tools/RouteGraphValidator/validate_route_graph.py"),
    Path("Tools/TaskFingerprintValidator/validate_task_fingerprints.py"),
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


def run_validator(path: Path) -> int:
    full_path = ROOT / path
    if not full_path.is_file():
        print(f"[FAIL] Missing validator: {path}")
        return 1

    print(f"\n== {path} ==")
    completed = subprocess.run(
        [sys.executable, str(full_path)],
        cwd=ROOT,
        check=False,
    )
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
        if run_validator(validator) != 0:
            failed.append(str(validator))

    if failed:
        print("\nUnityAgent local validation failed:")
        for validator in failed:
            print(f"- {validator}")
        return 1

    print("\nUnityAgent local validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
