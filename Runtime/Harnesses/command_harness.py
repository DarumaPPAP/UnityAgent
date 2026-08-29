"""Explicit command-backed Test/Performance/SCM harness surface."""
from __future__ import annotations
from pathlib import Path
from Runtime.Dispatcher.subprocess_dispatcher import DispatchRequest, dispatch


def run_command_harness(*, harness_id: str, command: list[str], cwd: str | Path, timeout_seconds: float, expect_json: bool = False) -> dict:
    if harness_id not in {"test", "performance", "scm", "unity", "tool"}:
        raise ValueError(f"unsupported harness id: {harness_id}")
    result = dispatch(DispatchRequest(command=command, cwd=Path(cwd).resolve(), timeout_seconds=timeout_seconds, expect_json=expect_json))
    return {"harness_id": harness_id, "status": result["status"], "failure_class": result.get("failure_class"), "exit_code": result["result"].returncode, "stdout": result["result"].stdout, "stderr": result["result"].stderr}
