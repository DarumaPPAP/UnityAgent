"""Phase 10 comparison of a frozen baseline against one Production candidate.

The comparator is intentionally read-only. It validates existing Phase 9 freeze and
RebaselineSummary contracts, classifies definition/runtime drift, compares observed
Production quality, and derives a merge-gate decision. It never runs Runtime, Codex,
historical replay, or mutation logic, and it never updates the frozen baseline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from Eval.Rebaseline.baseline_freeze import validate_baseline_freeze
from Eval.Rebaseline.rebaseline import EXPECTED_CASES, validate_rebaseline_summary

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "Eval/Regression/baseline-comparison.schema.yaml"

# A change to these fields changes the evaluation/runtime definition enough that a
# candidate must not be called a regression against the frozen Phase 9 baseline.
BLOCKING_FINGERPRINT_FIELDS = (
    "architecture_version",
    "policy_revision",
    "prompt_revision",
    "graph_revision",
    "runtime_profile_revision",
    "tool_schema_revision",
    "checkpoint_schema_revision",
    "evidence_schema_revision",
    "eval_contract_revision",
)

# These fields are expected to move when evaluating a new implementation while the
# comparison contract itself remains stable.
INFORMATIONAL_FINGERPRINT_FIELDS = ("context_revision",)


class BaselineComparisonError(ValueError):
    pass


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise BaselineComparisonError(f"expected YAML mapping: {path}")
    return value


def _drift(scope: str, field: str, baseline: object, candidate: object) -> dict[str, str]:
    return {
        "scope": scope,
        "field": field,
        "baseline": str(baseline if baseline is not None else ""),
        "candidate": str(candidate if candidate is not None else ""),
    }


def _baseline_identity(freeze: dict[str, Any]) -> dict[str, str]:
    runtime = freeze["runtime"]
    return {
        "freeze_id": str(freeze["freeze_id"]),
        "run_id": str(freeze["accepted_run"]["run_id"]),
        "source_revision": str(freeze["source"]["revision"]),
        "model": str(runtime["model"]),
        "reasoning_effort": str(runtime["reasoning_effort"]),
        "codex_version": str(runtime["codex_version"]),
    }


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, str]:
    runtime = candidate["runtime"]
    return {
        "run_id": str(candidate["run_id"]),
        "source_revision": str(candidate["source"]["revision"]),
        "model": str(runtime["model"]),
        "reasoning_effort": str(runtime["reasoning_effort"]),
        "codex_version": str(runtime["codex_version"]),
    }


def _comparability(freeze: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    blocking: list[dict[str, str]] = []
    informational: list[dict[str, str]] = []
    missing: list[str] = []

    baseline_identity = _baseline_identity(freeze)
    candidate_identity = _candidate_identity(candidate)

    for field in ("model", "reasoning_effort"):
        if baseline_identity[field] != candidate_identity[field]:
            blocking.append(_drift("runtime", field, baseline_identity[field], candidate_identity[field]))

    if baseline_identity["source_revision"] != candidate_identity["source_revision"]:
        informational.append(
            _drift(
                "source",
                "revision",
                baseline_identity["source_revision"],
                candidate_identity["source_revision"],
            )
        )

    if baseline_identity["codex_version"] != candidate_identity["codex_version"]:
        informational.append(
            _drift(
                "runtime",
                "codex_version",
                baseline_identity["codex_version"],
                candidate_identity["codex_version"],
            )
        )

    baseline_fingerprints = freeze.get("definition_fingerprints") or {}
    candidate_fingerprints = candidate.get("definition_fingerprints") or {}
    for task_id in EXPECTED_CASES:
        baseline_fp = baseline_fingerprints.get(task_id)
        candidate_fp = candidate_fingerprints.get(task_id)
        if not isinstance(candidate_fp, dict):
            missing.append(f"definition_fingerprints.{task_id}")
            continue
        if not isinstance(baseline_fp, dict):
            # The Phase 9 freeze validator should make this unreachable, but keep
            # the comparator fail-closed if an invalid caller bypasses validation.
            missing.append(f"baseline.definition_fingerprints.{task_id}")
            continue
        for field in BLOCKING_FINGERPRINT_FIELDS:
            if str(baseline_fp.get(field) or "") != str(candidate_fp.get(field) or ""):
                blocking.append(
                    _drift(task_id, field, baseline_fp.get(field), candidate_fp.get(field))
                )
        for field in INFORMATIONAL_FINGERPRINT_FIELDS:
            if str(baseline_fp.get(field) or "") != str(candidate_fp.get(field) or ""):
                informational.append(
                    _drift(task_id, field, baseline_fp.get(field), candidate_fp.get(field))
                )

    if missing:
        status = "insufficient_evidence"
    elif blocking:
        status = "not_comparable"
    elif informational:
        status = "comparable_with_drift"
    else:
        status = "strict_comparable"

    return {
        "status": status,
        "blocking_drift": blocking,
        "informational_drift": informational,
        "missing_evidence": sorted(set(missing)),
    }


def _quality(value: dict[str, Any]) -> dict[str, Any]:
    quality = value["quality"]
    return {
        "total": int(quality["total"]),
        "observed": int(quality["observed"]),
        "quality_denominator": int(quality["quality_denominator"]),
        "quality_passed": int(quality["quality_passed"]),
        "regression_pass_rate": float(quality["regression_pass_rate"]),
    }


def _case_deltas(candidate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidate_cases = candidate.get("cases") or {}
    output: dict[str, dict[str, Any]] = {}
    for task_id in EXPECTED_CASES:
        item = candidate_cases.get(task_id)
        if not isinstance(item, dict):
            output[task_id] = {
                "baseline_status": "passed",
                "candidate_status": "missing",
                "candidate_observation_state": "missing",
                "candidate_quality_denominator_eligible": None,
                "transition": "passed->missing",
                "regression": False,
            }
            continue
        status = str(item.get("status") or "missing")
        observation = str(item.get("observation_state") or "missing")
        eligible = bool(item.get("quality_denominator_eligible"))
        regression = observation == "observed" and eligible and status == "failed"
        output[task_id] = {
            "baseline_status": "passed",
            "candidate_status": status,
            "candidate_observation_state": observation,
            "candidate_quality_denominator_eligible": eligible,
            "transition": f"passed->{status}",
            "regression": regression,
        }
    return output


def _quality_below_baseline(baseline: dict[str, Any], candidate: dict[str, Any]) -> bool:
    return (
        candidate["total"] < baseline["total"]
        or candidate["observed"] < baseline["observed"]
        or candidate["quality_denominator"] < baseline["quality_denominator"]
        or candidate["quality_passed"] < baseline["quality_passed"]
        or candidate["regression_pass_rate"] < baseline["regression_pass_rate"]
    )


def build_baseline_comparison(
    freeze: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    """Build one Phase 10 comparison without executing production behavior."""
    validate_baseline_freeze(freeze)
    validate_rebaseline_summary(candidate)

    comparability = _comparability(freeze, candidate)
    baseline_quality = _quality(freeze)
    candidate_quality = _quality(candidate)
    cases = _case_deltas(candidate)

    counts = {
        str(key): int(value)
        for key, value in sorted(((candidate.get("taxonomy") or {}).get("counts") or {}).items())
    }
    active_failure_classes = sorted(key for key, value in counts.items() if value > 0)
    agent_regression_count = int(counts.get("agent_behavior_regression", 0))
    non_agent_failures = [
        key for key in active_failure_classes if key != "agent_behavior_regression"
    ]

    reasons: list[str] = []
    if comparability["status"] == "insufficient_evidence":
        decision = "BLOCK_INCONCLUSIVE"
        reasons.append("candidate_comparability_evidence_missing")
    elif comparability["status"] == "not_comparable":
        decision = "REBASELINE_REQUIRED"
        reasons.append("evaluation_or_runtime_definition_changed")
    else:
        incomplete_cases = [
            task_id
            for task_id, item in cases.items()
            if item["candidate_status"] == "missing"
        ]
        not_observed_cases = [
            task_id
            for task_id, item in cases.items()
            if item["candidate_observation_state"] != "observed"
        ]
        ineligible_cases = [
            task_id
            for task_id, item in cases.items()
            if item["candidate_quality_denominator_eligible"] is not True
        ]
        regressed_cases = [
            task_id for task_id, item in cases.items() if item["regression"]
        ]

        if incomplete_cases:
            reasons.append("candidate_cases_incomplete")
        if not_observed_cases:
            reasons.append("candidate_not_fully_observed")
        if ineligible_cases:
            reasons.append("candidate_quality_denominator_incomplete")
        if non_agent_failures:
            reasons.append("non_agent_failure_present")
        if regressed_cases or agent_regression_count:
            reasons.append("agent_behavior_regression_present")

        if incomplete_cases or not_observed_cases or ineligible_cases or non_agent_failures:
            decision = "BLOCK_INCONCLUSIVE"
        elif regressed_cases or agent_regression_count:
            decision = "BLOCK_REGRESSION"
        elif _quality_below_baseline(baseline_quality, candidate_quality):
            # With all cases observed/eligible and no infrastructure taxonomy, a
            # lower quality result is an observed Agent regression even if a future
            # summary representation changes how the case detail is expressed.
            decision = "BLOCK_REGRESSION"
            reasons.append("candidate_quality_below_frozen_baseline")
        else:
            decision = "PASS"
            reasons.append("candidate_meets_frozen_baseline")

    comparison = {
        "schema_version": "1.0",
        "phase": 10,
        "baseline": _baseline_identity(freeze),
        "candidate": _candidate_identity(candidate),
        "comparability": comparability,
        "quality_delta": {
            "baseline": baseline_quality,
            "candidate": candidate_quality,
            "quality_passed_delta": (
                candidate_quality["quality_passed"] - baseline_quality["quality_passed"]
            ),
            "regression_pass_rate_delta": (
                candidate_quality["regression_pass_rate"]
                - baseline_quality["regression_pass_rate"]
            ),
        },
        "cases": cases,
        "taxonomy": {
            "candidate_counts": counts,
            "active_failure_classes": active_failure_classes,
        },
        "gate": {
            "decision": decision,
            "reasons": sorted(set(reasons)),
        },
    }
    validate_baseline_comparison(comparison)
    return comparison


def validate_baseline_comparison(comparison: dict[str, Any]) -> None:
    """Validate the report schema and derived decision/comparability invariants."""
    try:
        Draft202012Validator(_yaml(SCHEMA_PATH)).validate(comparison)
    except ValidationError as exc:
        raise BaselineComparisonError(
            f"BaselineComparison schema validation failed: {exc.message}"
        ) from exc

    comparability = comparison["comparability"]
    status = comparability["status"]
    blocking = comparability["blocking_drift"]
    informational = comparability["informational_drift"]
    missing = comparability["missing_evidence"]
    decision = comparison["gate"]["decision"]

    if status == "strict_comparable" and (blocking or informational or missing):
        raise BaselineComparisonError("strict_comparable cannot contain recorded drift or missing evidence")
    if status == "comparable_with_drift" and (blocking or missing or not informational):
        raise BaselineComparisonError(
            "comparable_with_drift requires informational drift only"
        )
    if status == "not_comparable" and (not blocking or missing):
        raise BaselineComparisonError(
            "not_comparable requires blocking drift and complete comparison evidence"
        )
    if status == "insufficient_evidence" and not missing:
        raise BaselineComparisonError(
            "insufficient_evidence requires missing comparison evidence"
        )

    quality_delta = comparison["quality_delta"]
    baseline_quality = quality_delta["baseline"]
    candidate_quality = quality_delta["candidate"]
    expected_pass_delta = candidate_quality["quality_passed"] - baseline_quality["quality_passed"]
    expected_rate_delta = (
        candidate_quality["regression_pass_rate"] - baseline_quality["regression_pass_rate"]
    )
    if quality_delta["quality_passed_delta"] != expected_pass_delta:
        raise BaselineComparisonError("quality_passed_delta is inconsistent")
    if abs(float(quality_delta["regression_pass_rate_delta"]) - expected_rate_delta) > 1e-12:
        raise BaselineComparisonError("regression_pass_rate_delta is inconsistent")

    cases = comparison["cases"]
    for task_id in EXPECTED_CASES:
        item = cases[task_id]
        expected_transition = f"passed->{item['candidate_status']}"
        if item["transition"] != expected_transition:
            raise BaselineComparisonError(f"{task_id} transition is inconsistent")
        expected_regression = (
            item["candidate_observation_state"] == "observed"
            and item["candidate_quality_denominator_eligible"] is True
            and item["candidate_status"] == "failed"
        )
        if bool(item["regression"]) != expected_regression:
            raise BaselineComparisonError(f"{task_id} regression flag is inconsistent")

    counts = comparison["taxonomy"]["candidate_counts"]
    expected_active = sorted(key for key, value in counts.items() if int(value) > 0)
    if comparison["taxonomy"]["active_failure_classes"] != expected_active:
        raise BaselineComparisonError("active_failure_classes is inconsistent with candidate_counts")

    incomplete = any(item["candidate_status"] == "missing" for item in cases.values())
    not_observed = any(
        item["candidate_observation_state"] != "observed" for item in cases.values()
    )
    ineligible = any(
        item["candidate_quality_denominator_eligible"] is not True
        for item in cases.values()
    )
    regression = any(item["regression"] for item in cases.values())
    agent_regression = int(counts.get("agent_behavior_regression", 0)) > 0
    non_agent_failure = any(
        value > 0 and key != "agent_behavior_regression"
        for key, value in counts.items()
    )
    quality_below = _quality_below_baseline(baseline_quality, candidate_quality)

    if decision == "REBASELINE_REQUIRED":
        if status != "not_comparable":
            raise BaselineComparisonError(
                "REBASELINE_REQUIRED requires not_comparable definition/runtime drift"
            )
        return

    if decision == "BLOCK_INCONCLUSIVE":
        inconclusive = (
            status == "insufficient_evidence"
            or (
                status in {"strict_comparable", "comparable_with_drift"}
                and (incomplete or not_observed or ineligible or non_agent_failure)
            )
        )
        if not inconclusive:
            raise BaselineComparisonError(
                "BLOCK_INCONCLUSIVE requires missing/unfinished/non-Agent evidence"
            )
        return

    if status not in {"strict_comparable", "comparable_with_drift"}:
        raise BaselineComparisonError(
            f"{decision} requires a comparable candidate"
        )
    if incomplete or not_observed or ineligible or non_agent_failure:
        raise BaselineComparisonError(
            f"{decision} cannot be used when Production observation is inconclusive"
        )

    if decision == "BLOCK_REGRESSION":
        if not (regression or agent_regression or quality_below):
            raise BaselineComparisonError(
                "BLOCK_REGRESSION requires observed regression evidence"
            )
        return

    if decision != "PASS":
        raise BaselineComparisonError(f"unknown gate decision invariant: {decision}")
    if regression or agent_regression or quality_below:
        raise BaselineComparisonError("PASS cannot contain regression evidence")
    if comparison["taxonomy"]["active_failure_classes"]:
        raise BaselineComparisonError("PASS cannot contain active failure taxonomy")
    if any(item["candidate_status"] != "passed" for item in cases.values()):
        raise BaselineComparisonError("PASS requires all canonical cases to pass")
    if any(item["candidate_observation_state"] != "observed" for item in cases.values()):
        raise BaselineComparisonError("PASS requires all canonical cases to be observed")
    if any(item["candidate_quality_denominator_eligible"] is not True for item in cases.values()):
        raise BaselineComparisonError("PASS requires all canonical cases to be quality eligible")
