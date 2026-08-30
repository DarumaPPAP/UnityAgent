"""Validation for reviewed Phase 9 baseline freeze manifests.

A freeze manifest records which already-observed baseline_ready run was accepted.
It never launches Runtime, replays history, rewrites execution evidence, or changes
Phase 9 baseline eligibility semantics.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from Eval.Rebaseline.rebaseline import EXPECTED_CASES, REQUIRED_NAMESPACES
from Persistence.Contracts.definition_fingerprint import validate_definition_fingerprint
from Persistence.Store.atomic_store import PersistenceError

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "Eval/Rebaseline/baseline-freeze.schema.yaml"


class BaselineFreezeError(ValueError):
    pass


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise BaselineFreezeError(f"expected YAML mapping: {path}")
    return value


def _validate_artifact_ref(value: object, *, run_id: str, filename: str, field: str) -> None:
    raw = str(value or "").replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise BaselineFreezeError(f"{field} must be a repository-relative artifact reference")
    expected = PurePosixPath("Artifacts") / "ProductionSmoke" / run_id / filename
    if path != expected:
        raise BaselineFreezeError(f"{field} must reference {expected.as_posix()}")


def validate_baseline_freeze(freeze: dict[str, Any]) -> None:
    """Validate a reviewed freeze manifest without requiring local run artifacts."""
    try:
        Draft202012Validator(_yaml(SCHEMA_PATH)).validate(freeze)
    except ValidationError as exc:
        raise BaselineFreezeError(f"BaselineFreeze schema validation failed: {exc.message}") from exc

    run_id = str((freeze.get("accepted_run") or {}).get("run_id") or "")
    if freeze.get("freeze_id") != f"{run_id}-freeze":
        raise BaselineFreezeError("freeze_id must be '<accepted run_id>-freeze'")

    namespaces = {str(item) for item in (freeze.get("historical_replay") or {}).get("observed_namespaces") or []}
    if namespaces != REQUIRED_NAMESPACES:
        raise BaselineFreezeError("historical replay must freeze exactly ARCH,NAMING,MUTATION,EVIDENCE coverage")

    fingerprints = freeze.get("definition_fingerprints") or {}
    if set(fingerprints) != set(EXPECTED_CASES):
        raise BaselineFreezeError("definition_fingerprints must contain exactly the four canonical Phase 9 cases")
    for task_id in EXPECTED_CASES:
        try:
            validate_definition_fingerprint(
                fingerprints[task_id],
                field=f"definition_fingerprints.{task_id}",
            )
        except PersistenceError as exc:
            raise BaselineFreezeError(str(exc)) from exc

    provenance = freeze.get("provenance") or {}
    _validate_artifact_ref(
        provenance.get("rebaseline_summary_ref"),
        run_id=run_id,
        filename="rebaseline-summary.json",
        field="provenance.rebaseline_summary_ref",
    )
    _validate_artifact_ref(
        provenance.get("historical_replay_ref"),
        run_id=run_id,
        filename="historical-replay.json",
        field="provenance.historical_replay_ref",
    )
