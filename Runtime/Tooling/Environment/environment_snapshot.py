"""Typed, provider-optional Environment Snapshot contract for Unity Runtime discovery."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, TypeAlias

import yaml
from jsonschema import Draft202012Validator

TriState: TypeAlias = bool | Literal["unknown"]
BindingStatus: TypeAlias = Literal["bound", "unbound", "ambiguous_binding", "not_running", "unknown"]

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = Path("Runtime/Contracts/environment-snapshot.schema.yaml")


@dataclass(frozen=True)
class ProjectSnapshot:
    root: str
    exists: TriState
    identity_status: Literal["bound", "invalid", "unknown"]
    unity_version: str | None
    required_paths: dict[str, TriState]


@dataclass(frozen=True)
class FilesystemSnapshot:
    readable: TriState
    writable: TriState
    writable_in_mutation_scope: TriState


@dataclass(frozen=True)
class GitSnapshot:
    available: TriState
    repository_bound: TriState


@dataclass(frozen=True)
class UnityEditorSnapshot:
    installed: TriState
    version: str | None
    executable_path: str | None
    project_version_match: TriState
    running: TriState
    safe_mode: TriState
    project_bound: TriState
    binding_status: BindingStatus
    bound_instance_id: str | None


@dataclass(frozen=True)
class UnityCliSnapshot:
    available: TriState
    version: str | None
    executable_path: str | None
    failure_class: Literal["unavailable", "unhealthy", "timeout", "unknown"] | None


@dataclass(frozen=True)
class PipelineSnapshot:
    installed: TriState
    reachable: TriState


@dataclass(frozen=True)
class ProviderBindingSnapshot:
    reachable: TriState
    available: TriState
    project_bound: TriState
    binding_status: BindingStatus
    bound_instance_id: str | None


@dataclass(frozen=True)
class AvailabilitySnapshot:
    available: TriState


@dataclass(frozen=True)
class BuildSnapshot:
    requested_target: str | None
    requested_target_module_available: TriState


@dataclass(frozen=True)
class PlayerRuntimeSnapshot:
    reachable: TriState
    instance_id: str | None


@dataclass(frozen=True)
class EnvironmentSnapshot:
    schema_version: str
    project: ProjectSnapshot
    filesystem: FilesystemSnapshot
    git: GitSnapshot
    unity_editor: UnityEditorSnapshot
    unity_cli: UnityCliSnapshot
    pipeline: PipelineSnapshot
    myunitymcp: ProviderBindingSnapshot
    coplay_mcp: ProviderBindingSnapshot
    test_framework: AvailabilitySnapshot
    build: BuildSnapshot
    player_runtime: PlayerRuntimeSnapshot
    profile_hint: str | None
    binding_fingerprint: str

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self, *, root: Path = ROOT) -> None:
        validate_environment_snapshot(self.to_dict(), root=root)


def validate_environment_snapshot(value: dict, *, root: Path = ROOT) -> None:
    schema = yaml.safe_load((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)


def validate_environment_snapshot_schema(*, root: Path = ROOT) -> None:
    schema = yaml.safe_load((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
