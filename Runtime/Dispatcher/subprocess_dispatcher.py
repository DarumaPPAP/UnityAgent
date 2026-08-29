"""Bounded tool/subprocess dispatcher. It never selects semantic fallbacks."""
from __future__ import annotations
import json
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from Runtime.ExecutionControl.process_runtime import run_streaming_process


@dataclass(frozen=True)
class DispatchRequest:
    command: list[str]
    cwd: Path
    timeout_seconds: float
    stdin_text: str | None = None
    expect_json: bool = False
    env: dict[str, str] | None = None


def dispatch(request: DispatchRequest, *, cancel_event: threading.Event | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="unityagent-runtime-") as temp:
        temp_path = Path(temp)
        result = run_streaming_process(
            request.command, cwd=request.cwd, timeout_seconds=request.timeout_seconds,
            stdout_path=temp_path / "stdout.txt", stderr_path=temp_path / "stderr.txt",
            env=request.env, stdin_text=request.stdin_text, cancel_event=cancel_event,
        )

    if result.cancelled:
        return {"status": "cancelled", "failure_class": "runtime_cancelled", "result": result}
    if result.timed_out:
        return {"status": "failed", "failure_class": "runtime_timeout", "result": result}
    if result.returncode != 0:
        return {"status": "failed", "failure_class": "runtime_protocol_failure", "result": result}

    payload: Any = result.stdout
    if request.expect_json:
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return {"status": "failed", "failure_class": "runtime_protocol_failure", "reason": "tool returned non-JSON output", "result": result}
    return {"status": "passed", "failure_class": None, "payload": payload, "result": result}
