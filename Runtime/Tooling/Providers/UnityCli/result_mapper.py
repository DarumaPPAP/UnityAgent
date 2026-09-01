"""Unity CLI の JSON/NDJSON を human log に依存せず Runtime fact へ正規化する。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from Runtime.Tooling.Providers.NativeUnityEditor.log_parser import read_test_results

_SENSITIVE_KEY_PARTS = ("secret", "password", "token", "keystore", "credential")


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if any(part in str(key).casefold() for part in _SENSITIVE_KEY_PARTS):
                result[str(key)] = "***"
            else:
                result[str(key)] = redact_sensitive(item)
        return result
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    return value


def parse_json_sequence(text: str) -> list[Any]:
    """Pretty JSON、連結JSON、NDJSONを同じdecoderで厳密に読む。"""
    stripped = text.strip()
    if not stripped:
        return []
    decoder = json.JSONDecoder()
    index = 0
    values: list[Any] = []
    while index < len(stripped):
        while index < len(stripped) and stripped[index].isspace():
            index += 1
        if index >= len(stripped):
            break
        try:
            value, end = decoder.raw_decode(stripped, index)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Unity CLI returned malformed JSON/NDJSON at offset {index}") from exc
        values.append(value)
        index = end
    return values


def terminal_envelope(values: Iterable[Any]) -> dict[str, Any] | None:
    terminal: dict[str, Any] | None = None
    for value in values:
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("envelope"), dict):
            terminal = dict(value["envelope"])
            terminal.setdefault("_exitCode", value.get("exitCode"))
            continue
        if isinstance(value.get("success"), bool):
            terminal = dict(value)
            continue
        if value.get("type") == "result" and isinstance(value.get("success"), bool):
            terminal = dict(value)
    return redact_sensitive(terminal) if terminal is not None else None


def _error_codes(envelope: dict[str, Any] | None) -> tuple[str, ...]:
    if not envelope:
        return ()
    errors = envelope.get("errors")
    if not isinstance(errors, list):
        return ()
    codes: list[str] = []
    for item in errors:
        if isinstance(item, dict) and item.get("code"):
            codes.append(str(item["code"]))
    return tuple(codes)


def classify_cli_failure(
    *,
    exit_code: int | None,
    envelope: dict[str, Any] | None,
    dispatcher_failure_class: str | None = None,
) -> tuple[str, str]:
    if dispatcher_failure_class == "runtime_cancelled":
        return "cancelled", "Unity CLI execution was cancelled"
    if dispatcher_failure_class == "runtime_timeout":
        return "timeout", "Unity CLI execution timed out"

    codes = _error_codes(envelope)
    folded = " ".join(codes).casefold()
    if exit_code == 2 or "unknown_command" in folded or "unsupported" in folded or "usage" in folded:
        return "unsupported", "Unity CLI command is unavailable for the observed CLI version"
    if exit_code in {3, 4}:
        return "precondition_failed", f"Unity CLI precondition/authentication failed with exit code {exit_code}"
    if exit_code in {130, 143}:
        return "cancelled", f"Unity CLI was interrupted with exit code {exit_code}"
    if exit_code is None:
        return "execution_failed", "Unity CLI process result is unavailable"
    return "execution_failed", f"Unity CLI command failed with exit code {exit_code}"


def envelope_data(envelope: dict[str, Any] | None) -> Any:
    if not envelope:
        return None
    return redact_sensitive(envelope.get("data"))


def normalize_project_info(*, exit_code: int, stdout: str) -> dict[str, Any]:
    try:
        values = parse_json_sequence(stdout)
    except ValueError as exc:
        return {"status": "failed", "failure_class": "execution_failed", "reason": str(exc), "evidence": []}
    envelope = terminal_envelope(values)
    if exit_code != 0 or envelope is None or envelope.get("success") is not True:
        failure_class, reason = classify_cli_failure(exit_code=exit_code, envelope=envelope)
        return {"status": "failed", "failure_class": failure_class, "reason": reason, "evidence": []}
    data = envelope_data(envelope)
    if not isinstance(data, dict):
        return {
            "status": "failed",
            "failure_class": "not_observed",
            "reason": "Unity CLI project info did not return structured project data",
            "evidence": [],
        }
    return {
        "status": "passed",
        "failure_class": None,
        "reason": None,
        "project": data,
        "evidence": ["project_fact"],
    }


def normalize_compile_observation(*, exit_code: int, stdout: str) -> dict[str, Any]:
    try:
        values = parse_json_sequence(stdout)
    except ValueError as exc:
        return {"status": "failed", "failure_class": "execution_failed", "reason": str(exc), "evidence": []}
    envelope = terminal_envelope(values)
    if exit_code != 0 or envelope is None or envelope.get("success") is not True:
        failure_class, reason = classify_cli_failure(exit_code=exit_code, envelope=envelope)
        return {"status": "failed", "failure_class": failure_class, "reason": reason, "evidence": []}
    return {
        "status": "passed",
        "failure_class": None,
        "reason": None,
        "result": envelope_data(envelope),
        "evidence": ["compile_observation"],
    }


def normalize_test_execution(*, exit_code: int, stdout: str, test_results_path: Path) -> dict[str, Any]:
    try:
        values = parse_json_sequence(stdout)
    except ValueError as exc:
        return {"status": "failed", "failure_class": "execution_failed", "reason": str(exc), "evidence": []}
    envelope = terminal_envelope(values)
    test_result = read_test_results(test_results_path)

    if test_result is not None:
        result_name = str(test_result.get("result") or "").casefold()
        if int(test_result.get("failed") or 0) > 0 or result_name in {"failed", "failure"}:
            return {
                "status": "failed",
                "failure_class": "observed_test_failure",
                "reason": "Unity Test Framework observed failing tests",
                "test_result": test_result,
                "cli_result": envelope_data(envelope),
                "evidence": ["test_execution"],
            }
        if exit_code == 0 and result_name in {"passed", "pass", "success"}:
            if envelope is None or envelope.get("success") is not True:
                return {
                    "status": "failed",
                    "failure_class": "not_observed",
                    "reason": "test XML passed but terminal Unity CLI success envelope was not observed",
                    "test_result": test_result,
                    "evidence": [],
                }
            return {
                "status": "passed",
                "failure_class": None,
                "reason": None,
                "test_result": test_result,
                "cli_result": envelope_data(envelope),
                "evidence": ["test_execution"],
            }

    if exit_code != 0:
        failure_class, reason = classify_cli_failure(exit_code=exit_code, envelope=envelope)
        return {
            "status": "failed",
            "failure_class": failure_class,
            "reason": reason,
            "test_result": test_result,
            "evidence": [],
        }
    return {
        "status": "failed",
        "failure_class": "not_observed",
        "reason": "Unity Test Framework XML was not observed",
        "test_result": None,
        "evidence": [],
    }


def normalize_build_execution(*, exit_code: int, stdout: str, build_output_path: Path) -> dict[str, Any]:
    try:
        values = parse_json_sequence(stdout)
    except ValueError as exc:
        return {"status": "failed", "failure_class": "execution_failed", "reason": str(exc), "evidence": []}
    envelope = terminal_envelope(values)
    if exit_code != 0 or envelope is None or envelope.get("success") is not True:
        failure_class, reason = classify_cli_failure(exit_code=exit_code, envelope=envelope)
        return {"status": "failed", "failure_class": failure_class, "reason": reason, "evidence": []}
    if not build_output_path.exists():
        return {
            "status": "failed",
            "failure_class": "not_observed",
            "reason": "Unity CLI reported build success but build output was not observed",
            "evidence": [],
        }
    return {
        "status": "passed",
        "failure_class": None,
        "reason": None,
        "build_output": str(build_output_path),
        "cli_result": envelope_data(envelope),
        "evidence": ["build_execution"],
    }


def extract_command_catalog(stdout: str) -> tuple[dict[str, Any], ...]:
    values = parse_json_sequence(stdout)
    envelope = terminal_envelope(values)
    if envelope is None or envelope.get("success") is not True:
        return ()
    data = envelope_data(envelope)
    candidates: Any = data
    if isinstance(data, dict):
        for key in ("commands", "tools", "items"):
            if isinstance(data.get(key), list):
                candidates = data[key]
                break
    if not isinstance(candidates, list):
        return ()

    commands: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("command")
        if not isinstance(name, str) or not name.strip():
            continue
        commands.append(
            {
                "name": name,
                "description": str(item.get("description") or ""),
                "group": str(item.get("group") or ""),
                "runtime_only": bool(item.get("runtimeOnly", item.get("runtime_only", False))),
                "parameters": redact_sensitive(item.get("parameters") or item.get("schema") or {}),
            }
        )
    return tuple(commands)


def normalize_pipeline_command(*, exit_code: int, stdout: str, evidence: list[str]) -> dict[str, Any]:
    try:
        values = parse_json_sequence(stdout)
    except ValueError as exc:
        return {"status": "failed", "failure_class": "execution_failed", "reason": str(exc), "evidence": []}
    envelope = terminal_envelope(values)
    if exit_code != 0 or envelope is None or envelope.get("success") is not True:
        failure_class, reason = classify_cli_failure(exit_code=exit_code, envelope=envelope)
        return {"status": "failed", "failure_class": failure_class, "reason": reason, "evidence": []}
    return {
        "status": "passed",
        "failure_class": None,
        "reason": None,
        "result": envelope_data(envelope),
        "evidence": list(evidence),
    }
