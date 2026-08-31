#!/usr/bin/env python3
"""Run the canonical Production regression gate on the local machine.

This is the standard local operating path. It reuses the existing Production
Smoke, Behavior Eval, RebaselineSummary and Baseline Comparator contracts while
letting the Codex CLI use the user's already-authenticated local ChatGPT session.

The runner deliberately removes OPENAI_API_KEY from the Production Smoke child
environment so the standard local path cannot silently switch to API-key billing.
The optional GitHub-hosted workflow remains available for explicit CI automation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml"
DEFAULT_ARTIFACT_ROOT = ROOT / "Artifacts/ProductionSmoke"
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_REASONING_EFFORT = "xhigh"
DEFAULT_TIMEOUT_SECONDS = 600.0

SMOKE = ROOT / ".github/ProductionSmoke/run_one_repo_smoke.py"
GRADE = ROOT / "Eval/Behavior/grade_production_smoke.py"
REBASELINE = ROOT / "Eval/Rebaseline/build_rebaseline_summary.py"
COMPARE = ROOT / "Eval/Regression/compare_baseline.py"
VALIDATE_FREEZE = ROOT / "Eval/Rebaseline/validate_baseline_freeze.py"


class LocalRegressionGateError(ValueError):
    pass


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("regression-local-%Y%m%d-%H%M%S")


def _safe_run_id(raw: str | None) -> str:
    value = raw or _default_run_id()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", value) or value in {".", ".."}:
        raise LocalRegressionGateError("run-id must be one safe path segment")
    return value


def _local_codex_environment(source: Mapping[str, str] | None = None) -> tuple[dict[str, str], bool]:
    env = dict(source or os.environ)
    removed = bool(env.pop("OPENAI_API_KEY", None))
    return env, removed


def _capture(command: list[str], *, env: Mapping[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=dict(env) if env is not None else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = ((completed.stdout or "") + (completed.stderr or "")).strip()
        raise LocalRegressionGateError(
            f"command failed ({completed.returncode}): {' '.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return ((completed.stdout or "") + (completed.stderr or "")).strip()


def _require_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise LocalRegressionGateError(f"required tool was not found on PATH: {name}")
    return executable


def _git_identity() -> tuple[str, str]:
    git = _require_tool("git")
    top = Path(_capture([git, "rev-parse", "--show-toplevel"]).splitlines()[0]).resolve()
    if os.path.normcase(str(top)) != os.path.normcase(str(ROOT.resolve())):
        raise LocalRegressionGateError(f"run from the UnityAgent repository: expected {ROOT}, got {top}")

    status = _capture([git, "status", "--porcelain", "--untracked-files=normal"])
    if status.strip():
        raise LocalRegressionGateError(
            "local regression gate requires a clean Git worktree so source_revision is trustworthy:\n"
            + status
        )

    revision = _capture([git, "rev-parse", "HEAD"]).splitlines()[0].strip()
    branch = _capture([git, "branch", "--show-current"]).splitlines()[0].strip() or "DETACHED"
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise LocalRegressionGateError(f"unexpected Git revision: {revision}")
    return revision, branch


def _codex_identity(env: Mapping[str, str]) -> tuple[str, str]:
    codex = _require_tool("codex")
    version_output = _capture([codex, "--version"], env=env)
    version = version_output.splitlines()[0].strip() if version_output else ""
    if not version:
        raise LocalRegressionGateError("Codex CLI did not report a version")
    return codex, version


def build_commands(
    *,
    run_id: str,
    source_revision: str,
    model: str,
    reasoning_effort: str,
    codex_version: str,
    timeout_seconds: float,
    baseline: Path,
) -> dict[str, list[str]]:
    run_root = DEFAULT_ARTIFACT_ROOT / run_id
    candidate = run_root / "rebaseline-summary.json"
    comparison = run_root / "baseline-comparison.json"
    python = sys.executable
    return {
        "validate_freeze": [python, str(VALIDATE_FREEZE), str(baseline)],
        "production_smoke": [
            python,
            str(SMOKE),
            "--run-id",
            run_id,
            "--model",
            model,
            "--reasoning-effort",
            reasoning_effort,
            "--timeout-seconds",
            str(timeout_seconds),
        ],
        "grade": [python, str(GRADE), "--run-id", run_id],
        "rebaseline": [
            python,
            str(REBASELINE),
            "--run-id",
            run_id,
            "--source-revision",
            source_revision,
            "--model",
            model,
            "--reasoning-effort",
            reasoning_effort,
            "--codex-version",
            codex_version,
        ],
        "compare": [
            python,
            str(COMPARE),
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--output",
            str(comparison),
            "--require-pass",
        ],
    }


def _run(command: list[str], *, env: Mapping[str, str] | None = None) -> int:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=dict(env) if env is not None else None,
        check=False,
    )
    return int(completed.returncode)


def _write_local_metadata(
    run_root: Path,
    *,
    branch: str,
    source_revision: str,
    codex_path: str,
    codex_version: str,
    api_key_removed: bool,
) -> None:
    if not run_root.is_dir():
        return
    metadata = {
        "schema_version": "1.0",
        "execution_mode": "local_chatgpt_codex_session",
        "git": {"branch": branch, "source_revision": source_revision, "worktree_clean": True},
        "codex": {"path": codex_path, "version": codex_version},
        "authentication": {
            "mode": "local_codex_session",
            "openai_api_key_removed_from_child_environment": api_key_removed,
        },
    }
    (run_root / "local-gate-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _comparison_decision(run_root: Path) -> str | None:
    path = run_root / "baseline-comparison.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    gate = value.get("gate") if isinstance(value, dict) else None
    if not isinstance(gate, dict):
        return None
    decision = gate.get("decision")
    return str(decision) if decision else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "xhigh"),
        default=DEFAULT_REASONING_EFFORT,
    )
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)

    try:
        if args.timeout_seconds <= 30:
            raise LocalRegressionGateError("timeout must be greater than 30 seconds")
        run_id = _safe_run_id(args.run_id)
        run_root = DEFAULT_ARTIFACT_ROOT / run_id
        if run_root.exists():
            raise LocalRegressionGateError(f"immutable run root already exists: {run_root}")

        baseline = args.baseline.resolve()
        if not baseline.is_file():
            raise LocalRegressionGateError(f"baseline manifest was not found: {baseline}")

        source_revision, branch = _git_identity()
        codex_env, api_key_removed = _local_codex_environment()
        codex_path, codex_version = _codex_identity(codex_env)
        commands = build_commands(
            run_id=run_id,
            source_revision=source_revision,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            codex_version=codex_version,
            timeout_seconds=args.timeout_seconds,
            baseline=baseline,
        )

        print(
            json.dumps(
                {
                    "gate": "baseline_regression",
                    "mode": "local_chatgpt_codex_session",
                    "run_id": run_id,
                    "branch": branch,
                    "source_revision": source_revision,
                    "model": args.model,
                    "reasoning_effort": args.reasoning_effort,
                    "codex_version": codex_version,
                    "openai_api_key_removed": api_key_removed,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        validate_code = _run(commands["validate_freeze"])
        if validate_code != 0:
            return validate_code

        smoke_code = _run(commands["production_smoke"], env=codex_env)
        _write_local_metadata(
            run_root,
            branch=branch,
            source_revision=source_revision,
            codex_path=codex_path,
            codex_version=codex_version,
            api_key_removed=api_key_removed,
        )
        grade_code = _run(commands["grade"])
        rebaseline_code = _run(commands["rebaseline"])
        comparison_code = _run(commands["compare"])

        decision = _comparison_decision(run_root)
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "production_smoke_exit": smoke_code,
                    "grade_exit": grade_code,
                    "rebaseline_exit": rebaseline_code,
                    "comparison_exit": comparison_code,
                    "gate_decision": decision,
                    "comparison": str(run_root / "baseline-comparison.json"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        if comparison_code != 0:
            return comparison_code
        if smoke_code != 0 or grade_code != 0 or rebaseline_code != 0:
            return 1
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Local regression gate failed: {exc}", file=sys.stderr)
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
