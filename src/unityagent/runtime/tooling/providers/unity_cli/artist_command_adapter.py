"""既存Pipeline transportへ渡すArtist入力。承認境界未接続のApplyは構築しない。"""
from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Literal

from unityagent.runtime.tooling.providers.unity_cli.command_builder import UnityCliCommand, build_pipeline_command
from unityagent.runtime.tooling.providers.unity_cli.result_mapper import parse_json_sequence


@dataclass(frozen=True)
class ArtistCommand:
    name: Literal["inspect", "plan", "preview", "apply", "capture", "evaluate", "refine", "history", "cinematic"]
    request_json: str | None = None
    plan_id: str | None = None
    expected_revision: str | None = None
    approval_token: str | None = None
    capture_id: str | None = None
    decision: Literal["accepted", "rejected", "needs_refine"] | None = None
    notes: str | None = None
    evaluation_id: str | None = None
    operation: Literal["inspect", "plan", "preview", "apply"] | None = None


_OPTIONS = {
    "inspect": (), "history": (),
    "plan": ("request_json", "expected_revision"),
    "preview": ("plan_id", "expected_revision"),
    "apply": ("plan_id", "expected_revision", "approval_token"),
    "capture": ("request_json",),
    "evaluate": ("capture_id", "decision", "notes"),
    "refine": ("evaluation_id", "request_json"),
    "cinematic": ("operation", "request_json", "plan_id", "expected_revision", "approval_token"),
}
_REQUIRED = {"preview": ("plan_id",), "evaluate": ("capture_id", "decision"), "refine": ("evaluation_id", "request_json")}
READ_ONLY_COMMANDS = frozenset({"inspect", "history", "plan", "preview", "cinematic"})


def build_artist_pipeline_command(executable: str | Path, project_root: str | Path, command: ArtistCommand) -> UnityCliCommand:
    if not isinstance(command, ArtistCommand) or not isinstance(command.name, str) or command.name not in _OPTIONS:
        raise ValueError("Artist command must be a typed, allowlisted command")
    operation = command.operation or "inspect"
    if command.name == "apply" or command.name == "cinematic" and operation == "apply":
        raise PermissionError("Artist mutation is blocked until authenticated Control Plane approval and Editor E2E are verified")
    allowed = _OPTIONS[command.name]
    for field in fields(command):
        value = getattr(command, field.name)
        if field.name != "name" and value is not None:
            if field.name not in allowed:
                raise ValueError(f"argument {field.name} is not valid for artist.{command.name}")
            if not isinstance(value, str) or not value.strip() or value.startswith("-") or "\0" in value:
                raise ValueError(f"argument {field.name} must be a non-empty string value, not a CLI option")
    if command.name == "cinematic" and operation not in {"inspect", "plan", "preview"}:
        raise ValueError("invalid cinematic operation")
    if command.approval_token is not None:
        raise ValueError("approval token is not accepted by a read-only Artist command")
    required = _REQUIRED.get(command.name, ())
    if command.name == "cinematic" and operation == "preview":
        required = ("plan_id",)
    if any(getattr(command, key) is None for key in required):
        raise ValueError(f"artist.{command.name} requires {', '.join(required)}")
    if command.name == "cinematic" and operation in {"inspect", "plan"} and command.plan_id is not None:
        raise ValueError("cinematic plan id is only valid for preview")
    if command.request_json is not None:
        values = parse_json_sequence(command.request_json, strict=True)
        if len(values) != 1 or not isinstance(values[0], dict):
            raise ValueError("Artist request JSON must contain an object")
    if command.decision is not None and command.decision not in {"accepted", "rejected", "needs_refine"}:
        raise ValueError("invalid human review decision")
    argv = []
    for key in allowed:
        value = getattr(command, key)
        if value is not None:
            argv.extend(["--" + key.replace("_", "-"), value])
    return build_pipeline_command(executable, project_root, f"artist.{command.name}", argv)
