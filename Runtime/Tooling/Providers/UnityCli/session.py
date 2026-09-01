"""Unity CLI shell のNDJSON protocolを bounded batch として利用する。"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Sequence

from Runtime.Dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from Runtime.Tooling.Providers.UnityCli.command_builder import (
    FORBIDDEN_COMMAND_NAMES,
    build_shell_ndjson_command,
    validate_safe_argv,
)
from Runtime.Tooling.Providers.UnityCli.result_mapper import parse_json_sequence, redact_sensitive


class UnityCliNdjsonSession:
    """Cross-call resident processを保持せず、1 batch内だけstartup costを共有する。"""

    def __init__(
        self,
        executable_path: str | Path,
        cwd: str | Path,
        *,
        dispatch_fn: Callable[..., dict[str, Any]] = dispatch,
    ) -> None:
        self.executable_path = Path(executable_path)
        self.cwd = Path(cwd).expanduser().resolve()
        self.dispatch_fn = dispatch_fn

    @staticmethod
    def _request_frame(request_id: str, argv: Sequence[str]) -> str:
        safe = validate_safe_argv(argv)
        if not safe:
            raise ValueError("session argv cannot be empty")
        if safe[0].casefold() in FORBIDDEN_COMMAND_NAMES:
            raise ValueError(f"raw eval is prohibited in Unity CLI session: {safe[0]}")
        return json.dumps({"id": request_id, "argv": list(safe)}, ensure_ascii=False)

    def run(
        self,
        commands: Sequence[Sequence[str]],
        *,
        timeout_seconds: float,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if not commands:
            return {"status": "passed", "failure_class": None, "responses": []}

        frames = [
            self._request_frame(str(index), argv)
            for index, argv in enumerate(commands, start=1)
        ]
        frames.append(json.dumps({"type": "shutdown"}))
        command = build_shell_ndjson_command(self.executable_path)
        outcome = self.dispatch_fn(
            DispatchRequest(
                command=list(command.argv),
                cwd=self.cwd,
                timeout_seconds=timeout_seconds,
                stdin_text="\n".join(frames) + "\n",
            ),
            cancel_event=cancel_event,
        )
        if outcome.get("status") == "cancelled" or outcome.get("failure_class") == "runtime_cancelled":
            return {"status": "failed", "failure_class": "cancelled", "responses": []}
        if outcome.get("failure_class") == "runtime_timeout":
            return {"status": "failed", "failure_class": "timeout", "responses": []}

        result = outcome.get("result")
        if result is None:
            return {"status": "failed", "failure_class": "execution_failed", "responses": []}
        try:
            values = parse_json_sequence(str(getattr(result, "stdout", "") or ""))
        except ValueError:
            return {"status": "failed", "failure_class": "execution_failed", "responses": []}

        responses = [
            redact_sensitive(value)
            for value in values
            if isinstance(value, dict) and "id" in value and isinstance(value.get("envelope"), dict)
        ]
        if len(responses) != len(commands):
            return {
                "status": "failed",
                "failure_class": "execution_failed",
                "reason": "NDJSON session response count did not match request count",
                "responses": responses,
            }
        if any(int(item.get("exitCode", 1)) != 0 for item in responses):
            return {
                "status": "failed",
                "failure_class": "execution_failed",
                "reason": "one or more NDJSON session commands failed",
                "responses": responses,
            }
        return {"status": "passed", "failure_class": None, "responses": responses}
