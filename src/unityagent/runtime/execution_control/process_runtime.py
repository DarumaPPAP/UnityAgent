#!/usr/bin/env python3
"""Cross-platform bounded process runtime.

Imported from Unity-Graph-Engineering's hardened process runtime and adapted so
Runtime owns cancellation as well as hard timeout/process-tree cleanup.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO


@dataclass
class StreamingProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    cancelled: bool
    root_pid: int
    process_tree_cleanup: str
    remaining_processes: int
    duration_seconds: float
    first_output_latency_seconds: float | None
    event_count: int
    last_event_timestamp: str | None


def utf8_child_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base or os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _terminate_process_tree(process: subprocess.Popen[str]) -> tuple[str, int]:
    if process.poll() is not None:
        return "not_required", 0
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False, capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=utf8_child_env(),
        )
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)
        remaining = 0 if process.poll() is not None else 1
        status = "completed" if completed.returncode == 0 and remaining == 0 else "forced_root_only"
        return status, remaining

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return "not_required", 0
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5.0)
    remaining = 0 if process.poll() is not None else 1
    return ("completed" if remaining == 0 else "failed"), remaining


def run_streaming_process(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    stdout_path: Path,
    stderr_path: Path,
    env: dict[str, str] | None = None,
    stdin_text: str | None = None,
    cancel_event: threading.Event | None = None,
) -> StreamingProcessResult:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    if not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError("command must be a non-empty string array")
    if not cwd.is_dir():
        raise ValueError(f"cwd must be an existing directory: {cwd}")

    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    first_output_at: float | None = None
    last_event_timestamp: str | None = None
    event_count = 0
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    lock = threading.Lock()

    creationflags = 0
    popen_kwargs: dict[str, object] = {}
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(
        command, cwd=cwd, stdin=subprocess.PIPE if stdin_text is not None else None,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        errors="replace", shell=False, env=utf8_child_env(env),
        creationflags=creationflags, **popen_kwargs,
    )
    if stdin_text is not None and process.stdin is not None:
        process.stdin.write(stdin_text)
        process.stdin.close()

    def pump(stream: IO[str] | None, target: Path, collector: list[str], parse_events: bool) -> None:
        nonlocal first_output_at, event_count, last_event_timestamp
        if stream is None:
            return
        with target.open("w", encoding="utf-8", errors="replace", newline="") as writer:
            for line in iter(stream.readline, ""):
                writer.write(line)
                writer.flush()
                collector.append(line)
                now = time.perf_counter()
                with lock:
                    if first_output_at is None:
                        first_output_at = now
                    if parse_events:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            event = None
                        if isinstance(event, dict):
                            event_count += 1
                            last_event_timestamp = datetime.now(timezone.utc).isoformat()
        stream.close()

    stdout_thread = threading.Thread(target=pump, args=(process.stdout, stdout_path, stdout_lines, True), daemon=True)
    stderr_thread = threading.Thread(target=pump, args=(process.stderr, stderr_path, stderr_lines, False), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    cancelled = False
    cleanup_status = "not_required"
    remaining = 0
    deadline = started + timeout_seconds
    while process.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            cleanup_status, remaining = _terminate_process_tree(process)
            break
        if time.perf_counter() >= deadline:
            timed_out = True
            cleanup_status, remaining = _terminate_process_tree(process)
            break
        time.sleep(0.05)

    stdout_thread.join(timeout=5.0)
    stderr_thread.join(timeout=5.0)
    duration = time.perf_counter() - started
    first_latency = None if first_output_at is None else max(0.0, first_output_at - started)
    return StreamingProcessResult(
        returncode=process.returncode if process.returncode is not None else 124,
        stdout="".join(stdout_lines), stderr="".join(stderr_lines),
        timed_out=timed_out, cancelled=cancelled, root_pid=process.pid,
        process_tree_cleanup=cleanup_status, remaining_processes=remaining,
        duration_seconds=duration, first_output_latency_seconds=first_latency,
        event_count=event_count, last_event_timestamp=last_event_timestamp,
    )
