"""Phase 9 unified Production Re-baseline aggregation.

This module never launches Runtime, Codex, Unity, or historical replay. It only
combines already-observed Eval facts, DefinitionFingerprints, and optional
historical replay facts into one RebaselineSummary.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from Persistence.Contracts.definition_fingerprint import validate_definition_fingerprint
from Persistence.Store.atomic_store import PersistenceError

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "Eval/Rebaseline/rebaseline-summary.schema.yaml"
TAXONOMY_PATH = ROOT / "Eval/Attribution/failure-taxonomy.yaml"
EXPECTED_CASES = (
    "GOLDEN-ARCH-001",
    "GOLDEN-NAMING-001",
    "GOLDEN-MUTATION-001",
    "GOLDEN-EVIDENCE-001",
)
REQUIRED_NAMESPACES = {"ARCH", "NAMING", "MUTATION", "EVIDENCE"}
LEGACY_NOT_OBSERVED_ALIASES = {
    "broken_eval": "evaluator_contract_failure",
    "unavailable_evidence": "unavailable_required_evidence",
}


class RebaselineError(ValueError):
    pass


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise RebaselineError(f"expected YAML mapping: {path}")
    return value


def _taxonomy() -> dict[str, dict[str, Any]]:
    failures = _yaml(TAXONOMY_PATH).get("failures") or {}
    if not isinstance(failures, dict) or not failures:
        raise RebaselineError("failure taxonomy has no canonical failure classes")
    return {str(key): value for key, value in failures.items() if isinstance(value, dict)}


def _canonical_failure_classes(result: dict[str, Any], taxonomy: dict[str, dict[str, Any]]) -> list[str]:
    status = str(result.get("status") or "")
    observation = str(result.get("observation_state") or "")
    eligible = bool(result.get("quality_denominator_eligible"))
    details = [str(item) for item in result.get("failure_details") or []]

    if observation == "observed" and eligible:
        if status == "passed":
            if details:
                raise RebaselineError("observed passed case cannot contain failure_details")
            return []
        if status == "failed":
            return ["agent_behavior_regression"]
        raise RebaselineError(f"invalid observed case status: {status}")

    if observation != "not_observed" or eligible:
        raise RebaselineError(
            "non-Agent failure must be not_observed and quality_denominator_eligible=false"
        )

    classes: set[str] = set()
    for detail in details:
        if detail in taxonomy and detail != "agent_behavior_regression":
            classes.add(detail)
        elif detail in LEGACY_NOT_OBSERVED_ALIASES:
            classes.add(LEGACY_NOT_OBSERVED_ALIASES[detail])
    if not classes:
        raise RebaselineError(
            "not_observed case requires a typed infrastructure/permission/fixture/evidence failure class"
        )
    return sorted(classes)


def _historical_summary(historical_replay: dict[str, Any] | None) -> dict[str, Any]:
    if historical_replay is None:
        return {
            "status": "pending",
            "observed_namespaces": [],
            "case_count": 0,
            "quality_denominator_eligible_count": 0,
        }
    namespaces = sorted({str(item) for item in historical_replay.get("observed_namespaces") or []})
    unknown = sorted(set(namespaces) - REQUIRED_NAMESPACES)
    if unknown:
        raise RebaselineError(f"historical replay contains unknown namespaces: {unknown}")
    return {
        "status": "passed" if REQUIRED_NAMESPACES.issubset(set(namespaces)) else "failed",
        "observed_namespaces": namespaces,
        "case_count": int(historical_replay.get("case_count") or 0),
        "quality_denominator_eligible_count": int(
            historical_replay.get("quality_denominator_eligible_count") or 0
        ),
    }


def build_rebaseline_summary(
    eval_summary: dict[str, Any],
    *,
    run_id: str,
    source_revision: str,
    model: str,
    reasoning_effort: str,
    codex_version: str,
    definition_fingerprints: dict[str, dict[str, Any]],
    historical_replay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one aggregate taxonomy/baseline summary from the complete suite."""
    taxonomy = _taxonomy()
    raw_results = eval_summary.get("results") or []
    if not isinstance(raw_results, list):
        raise RebaselineError("eval_summary.results must be an array")

    by_task: dict[str, dict[str, Any]] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            raise RebaselineError("eval result entry must be an object")
        task_id = str(item.get("task_id") or "")
        if task_id not in EXPECTED_CASES:
            raise RebaselineError(f"unexpected Phase 9 case: {task_id}")
        if task_id in by_task:
            raise RebaselineError(f"duplicate Phase 9 case: {task_id}")
        by_task[task_id] = item

    valid_fingerprints: dict[str, dict[str, Any]] = {}
    for task_id, fingerprint in definition_fingerprints.items():
        if task_id not in EXPECTED_CASES:
            raise RebaselineError(f"unexpected DefinitionFingerprint case: {task_id}")
        try:
            validate_definition_fingerprint(fingerprint, field=f"definition_fingerprints.{task_id}")
        except PersistenceError as exc:
            raise RebaselineError(str(exc)) from exc
        valid_fingerprints[task_id] = fingerprint

    taxonomy_counts: Counter[str] = Counter({key: 0 for key in taxonomy})
    attribution_counts: Counter[str] = Counter()
    cases: dict[str, dict[str, Any]] = {}
    for task_id in EXPECTED_CASES:
        result = by_task.get(task_id)
        if result is None:
            continue
        classes = _canonical_failure_classes(result, taxonomy)
        attributions = sorted({str(taxonomy[item].get("attribution") or "") for item in classes})
        if not attributions:
            attributions = ["none"]
        for failure_class in classes:
            taxonomy_counts[failure_class] += 1
        for attribution in attributions:
            attribution_counts[attribution] += 1
        cases[task_id] = {
            "task_id": task_id,
            "status": str(result.get("status") or ""),
            "observation_state": str(result.get("observation_state") or ""),
            "quality_denominator_eligible": bool(result.get("quality_denominator_eligible")),
            "taxonomy_failure_classes": classes,
            "attributions": attributions,
            "diagnostic_failure_details": sorted({str(item) for item in result.get("failure_details") or []}),
        }

    total = len(cases)
    observed = sum(item["observation_state"] == "observed" for item in cases.values())
    denominator = sum(item["quality_denominator_eligible"] for item in cases.values())
    quality_passed = sum(
        item["quality_denominator_eligible"] and item["status"] == "passed"
        for item in cases.values()
    )
    rate = (quality_passed / denominator) if denominator else 0.0
    historical = _historical_summary(historical_replay)

    smoke_reasons: list[str] = []
    missing_cases = [task_id for task_id in EXPECTED_CASES if task_id not in cases]
    if missing_cases:
        smoke_reasons.append(f"missing production cases: {','.join(missing_cases)}")
    not_observed = [task_id for task_id, item in cases.items() if item["observation_state"] != "observed"]
    if not_observed:
        smoke_reasons.append(f"production behavior not observed: {','.join(not_observed)}")
    failed = [task_id for task_id, item in cases.items() if item["status"] != "passed"]
    if failed:
        smoke_reasons.append(f"production cases failed: {','.join(failed)}")
    ineligible = [task_id for task_id, item in cases.items() if not item["quality_denominator_eligible"]]
    if ineligible:
        smoke_reasons.append(f"quality denominator excludes cases: {','.join(ineligible)}")
    if denominator != len(EXPECTED_CASES) or quality_passed != len(EXPECTED_CASES) or rate != 1.0:
        smoke_reasons.append("production quality is not 4/4 observed passes")
    missing_fingerprints = [task_id for task_id in EXPECTED_CASES if task_id not in valid_fingerprints]
    if missing_fingerprints:
        smoke_reasons.append(f"missing DefinitionFingerprint: {','.join(missing_fingerprints)}")
    active_taxonomy = [key for key, count in taxonomy_counts.items() if count]
    if active_taxonomy:
        smoke_reasons.append(f"canonical failure taxonomy is non-zero: {','.join(active_taxonomy)}")

    smoke_clean = not smoke_reasons
    reasons = list(smoke_reasons)
    if historical["status"] == "pending":
        reasons.append("historical replay coverage is pending")
    elif historical["status"] != "passed":
        reasons.append("historical replay does not cover ARCH,NAMING,MUTATION,EVIDENCE")

    eligible = not reasons
    if eligible:
        status = "baseline_ready"
    elif smoke_clean and historical["status"] == "pending":
        status = "smoke_passed_pending_historical"
    else:
        status = "not_eligible"

    summary = {
        "schema_version": "1.0",
        "phase": 9,
        "run_id": str(run_id),
        "status": status,
        "source": {
            "repository": "DarumaPPAP/UnityAgent",
            "revision": str(source_revision),
        },
        "runtime": {
            "model": str(model),
            "reasoning_effort": str(reasoning_effort),
            "codex_version": str(codex_version),
            "production_execution_observed": (
                len(cases) == len(EXPECTED_CASES)
                and all(item["observation_state"] == "observed" for item in cases.values())
            ),
        },
        "cases": cases,
        "taxonomy": {
            "counts": {key: int(taxonomy_counts[key]) for key in taxonomy},
            "attribution_counts": dict(sorted(attribution_counts.items())),
        },
        "diagnostics": {
            "failure_detail_counts": {
                str(key): int(value)
                for key, value in sorted((eval_summary.get("failure_counts") or {}).items())
            },
        },
        "quality": {
            "total": total,
            "observed": observed,
            "not_observed": total - observed,
            "quality_denominator": denominator,
            "quality_passed": quality_passed,
            "regression_pass_rate": rate,
        },
        "definition_fingerprints": {
            task_id: valid_fingerprints[task_id]
            for task_id in EXPECTED_CASES
            if task_id in valid_fingerprints
        },
        "historical_replay": historical,
        "baseline": {
            "eligible": eligible,
            "freeze_status": "ready" if eligible else "pending",
            "reasons": reasons,
        },
    }
    validate_rebaseline_summary(summary)
    return summary


def validate_rebaseline_summary(summary: dict[str, Any]) -> None:
    """Validate schema plus Phase 9 invariants without executing production code."""
    try:
        Draft202012Validator(_yaml(SCHEMA_PATH)).validate(summary)
    except ValidationError as exc:
        raise RebaselineError(f"RebaselineSummary schema validation failed: {exc.message}") from exc

    taxonomy = _taxonomy()
    if set(summary["taxonomy"]["counts"]) != set(taxonomy):
        raise RebaselineError("RebaselineSummary taxonomy keys differ from failure-taxonomy authority")

    quality = summary["quality"]
    cases = summary["cases"]
    if quality["total"] != len(cases):
        raise RebaselineError("quality.total does not match case count")
    observed = sum(item["observation_state"] == "observed" for item in cases.values())
    denominator = sum(item["quality_denominator_eligible"] for item in cases.values())
    passed = sum(
        item["quality_denominator_eligible"] and item["status"] == "passed"
        for item in cases.values()
    )
    expected_rate = (passed / denominator) if denominator else 0.0
    if quality["observed"] != observed or quality["not_observed"] != len(cases) - observed:
        raise RebaselineError("quality observation counts are inconsistent")
    if quality["quality_denominator"] != denominator or quality["quality_passed"] != passed:
        raise RebaselineError("quality denominator counts are inconsistent")
    if abs(float(quality["regression_pass_rate"]) - expected_rate) > 1e-12:
        raise RebaselineError("regression_pass_rate is inconsistent")

    eligible = bool(summary["baseline"]["eligible"])
    if eligible != (summary["status"] == "baseline_ready"):
        raise RebaselineError("baseline.eligible and status=baseline_ready must agree")
    if eligible and summary["baseline"]["reasons"]:
        raise RebaselineError("eligible baseline cannot contain blocking reasons")
    if eligible and summary["historical_replay"]["status"] != "passed":
        raise RebaselineError("eligible baseline requires passed historical replay")
