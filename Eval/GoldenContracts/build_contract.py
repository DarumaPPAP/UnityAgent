#!/usr/bin/env python3
"""Project legacy GoldenTask cases into canonical GoldenContract records.

This is evaluator-side only. The returned contract contains expectations and
must never be supplied to Runtime or Context materialization.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT / "Eval" / "Datasets" / "Golden" / "cases.yaml"


class GoldenContractError(ValueError):
    pass


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise GoldenContractError(f"expected mapping: {path}")
    return value


def build_contract(case: dict[str, Any], *, contract_revision: str) -> dict[str, Any]:
    case_id = str(case.get("id") or "").strip()
    expectation = case.get("expectation") or {}
    if not case_id or not isinstance(expectation, dict):
        raise GoldenContractError("case requires id and expectation mapping")

    expected_result: list[Any] = [{"outcome": expectation.get("outcome", "passed")}]
    naming = expectation.get("naming")
    if isinstance(naming, dict) and naming:
        expected_result.append({"naming": naming})

    invariants: list[Any] = []
    for policy in expectation.get("required_policies", []) or []:
        invariants.append({"required_policy": policy})
    for signal in expectation.get("required_signals", []) or []:
        invariants.append({"required_signal": signal})

    expected_trajectory: list[Any] = []
    if expectation.get("route"):
        expected_trajectory.append({"route": expectation["route"]})
    for grader in case.get("graders", []) or []:
        expected_trajectory.append({"grader": grader})

    forbidden = [{"signal": signal} for signal in expectation.get("forbidden_signals", []) or []]

    evidence_requirements: list[Any] = []
    for gate in expectation.get("required_gates", []) or []:
        evidence_requirements.append({"required_gate": gate})
    for knowledge in expectation.get("required_knowledge", []) or []:
        evidence_requirements.append({"required_knowledge": knowledge})

    return {
        "schema_version": "1.0",
        "contract_id": case_id,
        "contract_revision": contract_revision,
        "expected_result": expected_result,
        "invariants": invariants,
        "expected_trajectory": expected_trajectory,
        "forbidden": forbidden,
        "evidence_requirements": evidence_requirements,
    }


def build_all(*, cases_path: Path = DEFAULT_CASES, contract_revision: str) -> dict[str, Any]:
    document = _load_yaml(cases_path)
    cases = document.get("cases") or []
    if not isinstance(cases, list):
        raise GoldenContractError("cases must be an array")
    contracts = [build_contract(case, contract_revision=contract_revision) for case in cases]
    return {"schema_version": "1.0", "contracts": contracts}


def runtime_task_projection(case: dict[str, Any]) -> dict[str, Any]:
    """Return task-only data and fail closed if expectation-like keys leaked."""
    task = case.get("task") or {}
    if not isinstance(task, dict):
        raise GoldenContractError("task must be a mapping")
    forbidden = {
        "expectation", "expected_result", "invariants", "expected_trajectory",
        "forbidden", "evidence_requirements", "required_signals",
        "forbidden_signals", "required_policies", "required_gates",
    }
    leaked = sorted(forbidden & set(task))
    if leaked:
        raise GoldenContractError(f"Golden expectation leaked into task: {leaked}")
    return dict(task)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = build_all(cases_path=Path(args.cases), contract_revision=args.revision)
    output.write_text(yaml.safe_dump(result, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
