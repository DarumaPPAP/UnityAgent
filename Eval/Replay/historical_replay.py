#!/usr/bin/env python3
"""Replay legacy Production bundles through canonical Runtime/Eval contracts."""
from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from Eval.Attribution.attribution import build_eval_record
from Eval.Replay.legacy_bundle_normalizer import NormalizationError, normalize_bundle

NAMESPACES = ("ARCH", "NAMING", "MUTATION", "EVIDENCE")


class HistoricalReplayError(ValueError):
    pass


def _namespace(normalized: dict[str, Any]) -> str | None:
    step_id = str((normalized.get("execution_result") or {}).get("step_id") or "").upper()
    for name in NAMESPACES:
        if f"GOLDEN-{name}-" in step_id:
            return name
    return None


def _upgrade_eval(normalized: dict[str, Any]) -> dict[str, Any]:
    old = normalized.get("eval_record") or {}
    failure_class = old.get("failure_class")
    # Historical v1 transport has no explicit attribution. Upgrade only typed
    # canonical classes; never infer a class from response/stderr prose.
    try:
        return build_eval_record(
            eval_id=str(old.get("eval_id") or ""),
            run_id=str(old.get("run_id") or ""),
            source_execution_result_ref=str(old.get("source_execution_result_ref") or ""),
            failure_class=failure_class,
            observation_state=str(old.get("observation_state") or "") or None,
            runtime_failure_ref=old.get("runtime_failure_ref"),
            evidence_refs=list(old.get("evidence_refs") or []),
            reason=str(old.get("reason") or ""),
        )
    except ValueError:
        # Old observed evaluator detail classes predate EvalRecord 1.1. Preserve
        # the Phase-1 record exactly rather than inventing a new attribution.
        return dict(old)


def replay_bundle_directory(bundle: Path) -> dict[str, Any]:
    normalized = normalize_bundle(bundle)
    normalized["eval_record"] = _upgrade_eval(normalized)
    return {
        "bundle": bundle.name,
        "namespace": _namespace(normalized),
        "normalized": normalized,
    }


def _safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as stream:
        for info in stream.infolist():
            member = Path(info.filename)
            if member.is_absolute() or ".." in member.parts:
                raise HistoricalReplayError(f"unsafe archive member: {info.filename}")
        stream.extractall(destination)


def replay_path(path: Path) -> list[dict[str, Any]]:
    path = path.expanduser().resolve()
    if not path.exists():
        raise HistoricalReplayError(f"replay input does not exist: {path}")
    if path.is_file():
        if path.suffix.lower() != ".zip":
            raise HistoricalReplayError("historical replay file must be a .zip archive")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _safe_extract(path, root)
            bundles = sorted({item.parent for item in root.rglob("execution-envelope.yaml")})
            if not bundles:
                raise HistoricalReplayError(f"archive contains no execution-envelope.yaml: {path.name}")
            return [replay_bundle_directory(bundle) for bundle in bundles]
    if (path / "execution-envelope.yaml").is_file():
        return [replay_bundle_directory(path)]
    bundles = sorted({item.parent for item in path.rglob("execution-envelope.yaml")})
    if not bundles:
        raise HistoricalReplayError(f"directory contains no execution bundles: {path}")
    return [replay_bundle_directory(bundle) for bundle in bundles]


def replay(inputs: list[Path], *, require_namespaces: set[str] | None = None) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for item in inputs:
        cases.extend(replay_path(item))
    observed_namespaces = sorted({str(case["namespace"]) for case in cases if case.get("namespace")})
    required = set(require_namespaces or set())
    missing = sorted(required - set(observed_namespaces))
    if missing:
        raise HistoricalReplayError(f"historical replay missing namespaces: {missing}")
    eligible = sum(bool((case["normalized"].get("eval_record") or {}).get("quality_denominator_eligible")) for case in cases)
    return {
        "schema_version": "1.0",
        "case_count": len(cases),
        "observed_namespaces": observed_namespaces,
        "quality_denominator_eligible_count": eligible,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--require-namespaces", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    required = {item.strip().upper() for item in args.require_namespaces.split(",") if item.strip()}
    unknown = sorted(required - set(NAMESPACES))
    if unknown:
        print(f"unknown replay namespaces: {unknown}")
        return 2
    try:
        result = replay(args.inputs, require_namespaces=required)
    except (OSError, zipfile.BadZipFile, NormalizationError, HistoricalReplayError) as exc:
        print(f"historical replay failed: {exc}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
