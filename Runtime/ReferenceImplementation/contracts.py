"""Strict cross-process contracts for the canonical UnityAgent Runtime.

The v1.1 wire shape is retained for compatibility, while identity, capability,
scope, value and evidence rules are supplied by a :class:`SubAgentProfile`.
Concrete product values live in the profile catalog rather than in this generic
contract module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
import secrets
from typing import Any, ClassVar, Mapping

import yaml
from jsonschema import Draft202012Validator, ValidationError

from .canonicalization import digest_for
from .profiles import (
    CATALOG,
    ProfileValidationError,
    SubAgentProfile,
    default_profile,
    profile_for_capability,
    profile_for_grant,
    profile_for_task,
)


class ContractValidationError(ValueError):
    """A reference contract cannot be accepted at a trust boundary."""


def _object(value: Any, *, name: str, required: set[str], optional: set[str] = set()) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{name} must be an object")
    actual = set(value)
    missing = required - actual
    unknown = actual - required - optional
    if missing:
        raise ContractValidationError(f"{name} missing fields: {sorted(missing)}")
    if unknown:
        raise ContractValidationError(f"{name} has unknown fields: {sorted(unknown)}")
    return dict(value)


def _text(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{name} must be a non-empty string")
    return value


def _version(value: Any, *, name: str = "schema_version") -> str:
    if value != "1.1":
        raise ContractValidationError(f"{name} must be 1.1")
    return "1.1"


def _list(value: Any, *, name: str, min_items: int = 0) -> list[Any]:
    if not isinstance(value, list) or len(value) < min_items or len(set(map(repr, value))) != len(value):
        raise ContractValidationError(f"{name} must be a unique list with at least {min_items} item(s)")
    return list(value)


def _iso(value: Any, *, name: str) -> str:
    text = _text(value, name=name)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractValidationError(f"{name} must be an ISO-8601 timestamp") from exc
    return text


def _number(value: Any, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ContractValidationError(f"{name} must be a finite number")
    return float(value)


def _digest(value: Any, *, name: str) -> str:
    text = _text(value, name=name)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text.lower()):
        raise ContractValidationError(f"{name} must be a SHA-256 hex digest")
    return text.lower()


def _digest_match(payload: dict[str, Any], *, field: str, name: str) -> None:
    expected = digest_for(payload, field)
    if payload.get(field) != expected:
        raise ContractValidationError(f"{name} digest mismatch")


_DEFAULT_PROFILE = default_profile()
ALLOWED_EVIDENCE = frozenset(_DEFAULT_PROFILE.required_evidence)
ALLOWED_CAPABILITIES = frozenset(_DEFAULT_PROFILE.capabilities)
KNOWN_EVIDENCE = CATALOG.evidence_types()
FORBIDDEN_CAPABILITY_TOKENS = ("install", "installer", "shell", "filesystem", "project.write", "package")

_SCHEMA_PATH = Path(__file__).with_name("Schemas") / "reference-implementation.schema.yaml"
_COMPLETION_PROOF_ISSUER = object()


def contract_envelope(contract_type: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """Return and validate the only wire representation for v1.1 contracts."""
    envelope = {"contract_type": _text(contract_type, name="contract_type"), "value": dict(value)}
    schema = yaml.safe_load(_SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(envelope)
    except ValidationError as exc:
        raise ContractValidationError(f"{contract_type} envelope failed JSON Schema validation: {exc.message}") from exc
    return envelope


def validate_contract_envelope(value: Mapping[str, Any], expected_type: str | None = None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError("contract envelope must be an object")
    schema = yaml.safe_load(_SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(dict(value))
    except ValidationError as exc:
        raise ContractValidationError(f"contract envelope failed JSON Schema validation: {exc.message}") from exc
    contract_type = str(value["contract_type"])
    if expected_type is not None and contract_type != expected_type:
        raise ContractValidationError(f"expected {expected_type} envelope, got {contract_type}")
    return dict(value["value"])


def _scope(value: Any, *, name: str = "scope", profile: SubAgentProfile | None = None) -> dict[str, Any]:
    scope = _object(
        value,
        name=name,
        required={"target_guids", "component_type", "property_paths", "mutation_channels"},
    )
    selected = profile or _DEFAULT_PROFILE
    try:
        return selected.validate_scope(scope)
    except ProfileValidationError as exc:
        raise ContractValidationError(f"{name} is outside the SubAgent profile: {exc}") from exc


def _budgets(value: Any, *, name: str = "budgets") -> dict[str, int]:
    required = {
        "max_parent_total_calls", "max_parent_reentries", "max_global_replans", "max_escalations",
        "max_child_llm_calls", "max_tool_calls", "max_wall_clock_ms", "max_child_wall_clock_ms",
        "max_child_input_tokens", "max_child_output_tokens", "max_parent_input_tokens",
        "max_parent_output_tokens", "max_process_restarts", "max_provider_retries",
    }
    data = _object(value, name=name, required=required)
    result: dict[str, int] = {}
    for key in required:
        number = data[key]
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            raise ContractValidationError(f"{name}.{key} must be a non-negative integer")
        result[key] = number
    return result


@dataclass(frozen=True)
class TaskContract:
    schema_version: str
    task_id: str
    run_id: str
    goal_type: str
    project: dict[str, str]
    project_fingerprint: str
    scope: dict[str, Any]
    required_evidence: list[str]
    budgets: dict[str, int]
    issued_at: str
    contract_digest: str

    _required: ClassVar[set[str]] = {
        "schema_version", "task_id", "run_id", "goal_type", "project", "project_fingerprint",
        "scope", "required_evidence", "budgets", "issued_at", "contract_digest",
    }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, profile: SubAgentProfile | None = None) -> "TaskContract":
        data = _object(value, name="TaskContract", required=cls._required)
        _version(data["schema_version"])
        task_id, run_id, goal_type = (_text(data[key], name=key) for key in ("task_id", "run_id", "goal_type"))
        try:
            selected = profile or profile_for_task(data)
        except ProfileValidationError as exc:
            raise ContractValidationError(str(exc)) from exc
        if goal_type != selected.goal_type:
            raise ContractValidationError("TaskContract goal_type is unsupported by the selected SubAgent profile")
        project = _object(data["project"], name="TaskContract.project", required={"root", "name"})
        project = {"root": _text(project["root"], name="project.root"), "name": _text(project["name"], name="project.name")}
        fingerprint = _digest(data["project_fingerprint"], name="project_fingerprint")
        scope = _scope(data["scope"], profile=selected)
        required_evidence = [_text(item, name="required_evidence item") for item in _list(data["required_evidence"], name="required_evidence", min_items=1)]
        if set(required_evidence) != set(selected.required_evidence):
            raise ContractValidationError("TaskContract required_evidence must match the selected SubAgent profile")
        budgets = _budgets(data["budgets"])
        issued_at = _iso(data["issued_at"], name="issued_at")
        contract_digest = _digest(data["contract_digest"], name="contract_digest")
        result = cls("1.1", task_id, run_id, goal_type, project, fingerprint, scope, required_evidence, budgets, issued_at, contract_digest)
        _digest_match(result.to_dict(), field="contract_digest", name="TaskContract")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "goal_type": self.goal_type,
            "project": dict(self.project),
            "project_fingerprint": self.project_fingerprint,
            "scope": dict(self.scope),
            "required_evidence": list(self.required_evidence),
            "budgets": dict(self.budgets),
            "issued_at": self.issued_at,
            "contract_digest": self.contract_digest,
        }

    def to_envelope(self) -> dict[str, Any]:
        return contract_envelope("TaskContract", self.to_dict())

    @classmethod
    def from_envelope(cls, value: Mapping[str, Any], *, profile: SubAgentProfile | None = None) -> "TaskContract":
        return cls.from_dict(validate_contract_envelope(value, "TaskContract"), profile=profile)

    @classmethod
    def issue(
        cls,
        *,
        task_id: str,
        run_id: str,
        project: dict[str, str],
        project_fingerprint: str,
        issued_at: str,
        budgets: dict[str, int],
        scope: dict[str, Any] | None = None,
        profile: SubAgentProfile | None = None,
    ) -> "TaskContract":
        selected = profile or _DEFAULT_PROFILE
        value = {
            "schema_version": "1.1", "task_id": task_id, "run_id": run_id,
            "goal_type": selected.goal_type, "project": project,
            "project_fingerprint": project_fingerprint,
            "scope": scope or selected.default_scope,
            "required_evidence": sorted(selected.required_evidence), "budgets": budgets, "issued_at": issued_at,
        }
        value["contract_digest"] = digest_for(value, "contract_digest")
        return cls.from_dict(value, profile=selected)


@dataclass(frozen=True)
class ApprovalDecision:
    schema_version: str
    approval_decision_id: str
    task_id: str
    run_id: str
    project: dict[str, str]
    project_fingerprint: str
    contract_digest: str
    capability: str
    scope: dict[str, Any]
    parameter_envelope: dict[str, float]
    required_evidence: list[str]
    status: str
    expires_at: str
    revocation_epoch: int
    human_review: str
    decision_digest: str

    _required: ClassVar[set[str]] = {
        "schema_version", "approval_decision_id", "task_id", "run_id", "project", "project_fingerprint",
        "contract_digest", "capability", "scope", "parameter_envelope", "required_evidence", "status",
        "expires_at", "revocation_epoch", "human_review", "decision_digest",
    }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, profile: SubAgentProfile | None = None) -> "ApprovalDecision":
        data = _object(value, name="ApprovalDecision", required=cls._required)
        _version(data["schema_version"])
        capability = _text(data["capability"], name="capability")
        try:
            selected = profile or profile_for_capability(data)
        except ProfileValidationError as exc:
            raise ContractValidationError(str(exc)) from exc
        if capability != selected.primary_capability:
            raise ContractValidationError("ApprovalDecision capability is unsupported by the selected SubAgent profile")
        project = _object(data["project"], name="ApprovalDecision.project", required={"root", "name"})
        project = {"root": _text(project["root"], name="project.root"), "name": _text(project["name"], name="project.name")}
        envelope = _object(data["parameter_envelope"], name="parameter_envelope", required={"min", "max"})
        lower, upper = (_number(envelope[key], name=f"parameter_envelope.{key}") for key in ("min", "max"))
        try:
            selected.validate_parameter_envelope({"min": lower, "max": upper})
        except ProfileValidationError as exc:
            raise ContractValidationError(f"parameter envelope is invalid: {exc}") from exc
        evidence = [_text(item, name="required_evidence item") for item in _list(data["required_evidence"], name="required_evidence", min_items=1)]
        if set(evidence) != set(selected.required_evidence):
            raise ContractValidationError("ApprovalDecision evidence floor does not match the selected SubAgent profile")
        status = _text(data["status"], name="status")
        if status not in {"active", "revoked", "expired"}:
            raise ContractValidationError("ApprovalDecision status is invalid")
        epoch = data["revocation_epoch"]
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
            raise ContractValidationError("revocation_epoch must be a non-negative integer")
        human_review = _text(data["human_review"], name="human_review")
        if human_review not in {"approved", "pending", "rejected"}:
            raise ContractValidationError("human_review is invalid")
        result = cls(
            "1.1", _text(data["approval_decision_id"], name="approval_decision_id"), _text(data["task_id"], name="task_id"),
            _text(data["run_id"], name="run_id"), project, _digest(data["project_fingerprint"], name="project_fingerprint"),
            _digest(data["contract_digest"], name="contract_digest"), capability, _scope(data["scope"], name="ApprovalDecision.scope", profile=selected),
            {"min": lower, "max": upper}, evidence, status, _iso(data["expires_at"], name="expires_at"), epoch, human_review,
            _digest(data["decision_digest"], name="decision_digest"),
        )
        _digest_match(result.to_dict(), field="decision_digest", name="ApprovalDecision")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "approval_decision_id": self.approval_decision_id,
            "task_id": self.task_id, "run_id": self.run_id, "project": dict(self.project),
            "project_fingerprint": self.project_fingerprint, "contract_digest": self.contract_digest,
            "capability": self.capability, "scope": dict(self.scope), "parameter_envelope": dict(self.parameter_envelope),
            "required_evidence": list(self.required_evidence), "status": self.status, "expires_at": self.expires_at,
            "revocation_epoch": self.revocation_epoch, "human_review": self.human_review, "decision_digest": self.decision_digest,
        }

    def to_envelope(self) -> dict[str, Any]:
        return contract_envelope("ApprovalDecision", self.to_dict())

    @classmethod
    def from_envelope(cls, value: Mapping[str, Any], *, profile: SubAgentProfile | None = None) -> "ApprovalDecision":
        return cls.from_dict(validate_contract_envelope(value, "ApprovalDecision"), profile=profile)

    @classmethod
    def approve(
        cls,
        *,
        approval_decision_id: str,
        task: TaskContract,
        expires_at: str,
        lower: float | None = None,
        upper: float | None = None,
        profile: SubAgentProfile | None = None,
    ) -> "ApprovalDecision":
        selected = profile or profile_for_task(task.to_dict())
        lower_value = selected.approval["default_minimum"] if lower is None else lower
        upper_value = selected.approval["default_maximum"] if upper is None else upper
        value = {
            "schema_version": "1.1", "approval_decision_id": approval_decision_id, "task_id": task.task_id,
            "run_id": task.run_id, "project": dict(task.project), "project_fingerprint": task.project_fingerprint,
            "contract_digest": task.contract_digest, "capability": selected.primary_capability, "scope": dict(task.scope),
            "parameter_envelope": {"min": lower_value, "max": upper_value}, "required_evidence": sorted(selected.required_evidence),
            "status": "active", "expires_at": expires_at, "revocation_epoch": 0, "human_review": "approved",
        }
        value["decision_digest"] = digest_for(value, "decision_digest")
        return cls.from_dict(value, profile=selected)


@dataclass(frozen=True)
class SurfaceGrant:
    schema_version: str
    grant_id: str
    audience: str
    subagent_instance_id: str
    task_id: str
    run_id: str
    project: dict[str, str]
    project_fingerprint: str
    contract_digest: str
    approval_decision_id: str
    approval_digest: str
    capabilities: list[str]
    issued_at: str
    expires_at: str
    revocation_epoch: int
    grant_digest: str

    _required: ClassVar[set[str]] = {
        "schema_version", "grant_id", "audience", "subagent_instance_id", "task_id", "run_id", "project",
        "project_fingerprint", "contract_digest", "approval_decision_id", "approval_digest", "capabilities",
        "issued_at", "expires_at", "revocation_epoch", "grant_digest",
    }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, profile: SubAgentProfile | None = None) -> "SurfaceGrant":
        data = _object(value, name="SurfaceGrant", required=cls._required)
        _version(data["schema_version"])
        capabilities = [_text(item, name="capability") for item in _list(data["capabilities"], name="capabilities", min_items=1)]
        try:
            selected = profile or profile_for_grant(data)
            selected.validate_capabilities(capabilities)
        except ProfileValidationError as exc:
            raise ContractValidationError(f"SurfaceGrant capability set is invalid: {exc}") from exc
        if any(any(token in item.casefold() for token in FORBIDDEN_CAPABILITY_TOKENS) for item in capabilities):
            raise ContractValidationError("SurfaceGrant contains a forbidden capability token")
        if data["audience"] != selected.audience:
            raise ContractValidationError("SurfaceGrant audience is unsupported by the selected SubAgent profile")
        project = _object(data["project"], name="SurfaceGrant.project", required={"root", "name"})
        project = {"root": _text(project["root"], name="project.root"), "name": _text(project["name"], name="project.name")}
        epoch = data["revocation_epoch"]
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
            raise ContractValidationError("grant revocation_epoch must be a non-negative integer")
        result = cls(
            "1.1", _text(data["grant_id"], name="grant_id"), _text(data["audience"], name="audience"),
            _text(data["subagent_instance_id"], name="subagent_instance_id"), _text(data["task_id"], name="task_id"),
            _text(data["run_id"], name="run_id"), project, _digest(data["project_fingerprint"], name="project_fingerprint"),
            _digest(data["contract_digest"], name="contract_digest"), _text(data["approval_decision_id"], name="approval_decision_id"),
            _digest(data["approval_digest"], name="approval_digest"), capabilities, _iso(data["issued_at"], name="issued_at"),
            _iso(data["expires_at"], name="expires_at"), epoch, _digest(data["grant_digest"], name="grant_digest"),
        )
        _digest_match(result.to_dict(), field="grant_digest", name="SurfaceGrant")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "grant_id": self.grant_id, "audience": self.audience,
            "subagent_instance_id": self.subagent_instance_id, "task_id": self.task_id, "run_id": self.run_id,
            "project": dict(self.project), "project_fingerprint": self.project_fingerprint, "contract_digest": self.contract_digest,
            "approval_decision_id": self.approval_decision_id, "approval_digest": self.approval_digest,
            "capabilities": list(self.capabilities), "issued_at": self.issued_at, "expires_at": self.expires_at,
            "revocation_epoch": self.revocation_epoch, "grant_digest": self.grant_digest,
        }

    def to_envelope(self) -> dict[str, Any]:
        return contract_envelope("SurfaceGrant", self.to_dict())

    @classmethod
    def from_envelope(cls, value: Mapping[str, Any], *, profile: SubAgentProfile | None = None) -> "SurfaceGrant":
        return cls.from_dict(validate_contract_envelope(value, "SurfaceGrant"), profile=profile)


@dataclass(frozen=True)
class TypedAction:
    schema_version: str
    action_id: str
    idempotency_key: str
    task_id: str
    run_id: str
    contract_digest: str
    approval_decision_id: str
    approval_digest: str
    grant_id: str
    grant_digest: str
    project: dict[str, str]
    project_fingerprint: str
    capability: str
    target: dict[str, str]
    property_path: str
    mutation_channel: str
    value: float
    value_type: str
    unit: str
    expected_revision: str
    additional_required_evidence: list[str]
    action_digest: str

    _required: ClassVar[set[str]] = {
        "schema_version", "action_id", "idempotency_key", "task_id", "run_id", "contract_digest", "approval_decision_id",
        "approval_digest", "grant_id", "grant_digest", "project", "project_fingerprint", "capability", "target",
        "property_path", "mutation_channel", "value", "value_type", "unit", "expected_revision",
        "additional_required_evidence", "action_digest",
    }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, profile: SubAgentProfile | None = None) -> "TypedAction":
        data = _object(value, name="TypedAction", required=cls._required)
        _version(data["schema_version"])
        target = _object(data["target"], name="target", required={"guid", "component_type"})
        target = {"guid": _text(target["guid"], name="target.guid"), "component_type": _text(target["component_type"], name="target.component_type")}
        try:
            selected = profile or profile_for_capability(data)
            selected.validate_value(_number(data["value"], name="value"))
        except ProfileValidationError as exc:
            raise ContractValidationError(f"TypedAction is outside the SubAgent profile: {exc}") from exc
        if target["component_type"] != selected.scope["component_type"]:
            raise ContractValidationError("TypedAction target component is unsupported by the selected SubAgent profile")
        if data["property_path"] != selected.action_property_path or data["mutation_channel"] != selected.action_mutation_channel:
            raise ContractValidationError("TypedAction property/channel is unsupported by the selected SubAgent profile")
        if data["capability"] != selected.primary_capability:
            raise ContractValidationError("TypedAction capability is unsupported by the selected SubAgent profile")
        if data["value_type"] != selected.value["type"] or data["unit"] != selected.value["unit"]:
            raise ContractValidationError("TypedAction value type/unit is unsupported by the selected SubAgent profile")
        extra = [_text(item, name="additional_required_evidence item") for item in _list(data["additional_required_evidence"], name="additional_required_evidence")]
        if any(item not in selected.required_evidence for item in extra):
            raise ContractValidationError("TypedAction requested evidence is outside the selected SubAgent profile")
        result = cls(
            "1.1", _text(data["action_id"], name="action_id"), _text(data["idempotency_key"], name="idempotency_key"),
            _text(data["task_id"], name="task_id"), _text(data["run_id"], name="run_id"), _digest(data["contract_digest"], name="contract_digest"),
            _text(data["approval_decision_id"], name="approval_decision_id"), _digest(data["approval_digest"], name="approval_digest"),
            _text(data["grant_id"], name="grant_id"), _digest(data["grant_digest"], name="grant_digest"),
            {"root": _text(_object(data["project"], name="project", required={"root", "name"})["root"], name="project.root"), "name": _text(_object(data["project"], name="project", required={"root", "name"})["name"], name="project.name")},
            _digest(data["project_fingerprint"], name="project_fingerprint"), _text(data["capability"], name="capability"), target,
            _text(data["property_path"], name="property_path"), _text(data["mutation_channel"], name="mutation_channel"), _number(data["value"], name="value"), _text(data["value_type"], name="value_type"), _text(data["unit"], name="unit"),
            _text(data["expected_revision"], name="expected_revision"), extra, _digest(data["action_digest"], name="action_digest"),
        )
        _digest_match(result.to_dict(), field="action_digest", name="TypedAction")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "action_id": self.action_id, "idempotency_key": self.idempotency_key,
            "task_id": self.task_id, "run_id": self.run_id, "contract_digest": self.contract_digest,
            "approval_decision_id": self.approval_decision_id, "approval_digest": self.approval_digest,
            "grant_id": self.grant_id, "grant_digest": self.grant_digest, "project": dict(self.project),
            "project_fingerprint": self.project_fingerprint, "capability": self.capability, "target": dict(self.target),
            "property_path": self.property_path, "mutation_channel": self.mutation_channel, "value": self.value,
            "value_type": self.value_type, "unit": self.unit, "expected_revision": self.expected_revision,
            "additional_required_evidence": list(self.additional_required_evidence), "action_digest": self.action_digest,
        }

    def to_envelope(self) -> dict[str, Any]:
        return contract_envelope("TypedAction", self.to_dict())

    @classmethod
    def from_envelope(cls, value: Mapping[str, Any], *, profile: SubAgentProfile | None = None) -> "TypedAction":
        return cls.from_dict(validate_contract_envelope(value, "TypedAction"), profile=profile)

    @classmethod
    def propose(
        cls,
        *,
        action_id: str,
        idempotency_key: str,
        task: TaskContract,
        approval: ApprovalDecision,
        grant: SurfaceGrant,
        value: float,
        expected_revision: str,
        profile: SubAgentProfile | None = None,
    ) -> "TypedAction":
        selected = profile or profile_for_task(task.to_dict())
        value_dict = {
            "schema_version": "1.1", "action_id": action_id, "idempotency_key": idempotency_key,
            "task_id": task.task_id, "run_id": task.run_id, "contract_digest": task.contract_digest,
            "approval_decision_id": approval.approval_decision_id, "approval_digest": approval.decision_digest,
            "grant_id": grant.grant_id, "grant_digest": grant.grant_digest, "project": dict(task.project),
            "project_fingerprint": task.project_fingerprint, "capability": selected.primary_capability,
            "target": {"guid": task.scope["target_guids"][0], "component_type": selected.scope["component_type"]},
            "property_path": selected.action_property_path, "mutation_channel": selected.action_mutation_channel, "value": value,
            "value_type": selected.value["type"], "unit": selected.value["unit"], "expected_revision": expected_revision,
            "additional_required_evidence": [],
        }
        value_dict["action_digest"] = digest_for(value_dict, "action_digest")
        return cls.from_dict(value_dict, profile=selected)


@dataclass(frozen=True)
class ProviderResult:
    schema_version: str
    status: str
    provider_ref: str
    action_id: str
    project: dict[str, str]
    target: dict[str, str]
    property_path: str
    before_value: float
    after_value: float
    observed_revision: str
    exact_diff: dict[str, Any]
    evidence: list[str]
    mutation_count: int
    boundary_violations: list[str]
    failure_class: str | None
    provider_result_digest: str

    _required: ClassVar[set[str]] = {
        "schema_version", "status", "provider_ref", "action_id", "project", "target", "property_path",
        "before_value", "after_value", "observed_revision", "exact_diff", "evidence", "mutation_count",
        "boundary_violations", "failure_class", "provider_result_digest",
    }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProviderResult":
        data = _object(value, name="ProviderResult", required=cls._required)
        _version(data["schema_version"])
        if data["status"] not in {"passed", "failed"}:
            raise ContractValidationError("ProviderResult status is invalid")
        project = _object(data["project"], name="ProviderResult.project", required={"root", "name"})
        project = {"root": _text(project["root"], name="project.root"), "name": _text(project["name"], name="project.name")}
        target = _object(data["target"], name="ProviderResult.target", required={"guid", "component_type"})
        target = {"guid": _text(target["guid"], name="target.guid"), "component_type": _text(target["component_type"], name="target.component_type")}
        evidence = [_text(item, name="evidence item") for item in _list(data["evidence"], name="evidence")]
        violations = [_text(item, name="boundary violation") for item in _list(data["boundary_violations"], name="boundary_violations")]
        count = data["mutation_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ContractValidationError("mutation_count must be a non-negative integer")
        result = cls(
            "1.1", _text(data["status"], name="status"), _text(data["provider_ref"], name="provider_ref"), _text(data["action_id"], name="action_id"),
            project, target, _text(data["property_path"], name="property_path"), _number(data["before_value"], name="before_value"),
            _number(data["after_value"], name="after_value"), _text(data["observed_revision"], name="observed_revision"),
            _object(data["exact_diff"], name="exact_diff", required={"target", "property", "before", "after"}), evidence, count, violations,
            None if data["failure_class"] is None else _text(data["failure_class"], name="failure_class"), _digest(data["provider_result_digest"], name="provider_result_digest"),
        )
        _digest_match(result.to_dict(), field="provider_result_digest", name="ProviderResult")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "status": self.status, "provider_ref": self.provider_ref,
            "action_id": self.action_id, "project": dict(self.project), "target": dict(self.target),
            "property_path": self.property_path, "before_value": self.before_value, "after_value": self.after_value,
            "observed_revision": self.observed_revision, "exact_diff": dict(self.exact_diff), "evidence": list(self.evidence),
            "mutation_count": self.mutation_count, "boundary_violations": list(self.boundary_violations),
            "failure_class": self.failure_class, "provider_result_digest": self.provider_result_digest,
        }

    def to_envelope(self) -> dict[str, Any]:
        return contract_envelope("ProviderResult", self.to_dict())

    @classmethod
    def from_envelope(cls, value: Mapping[str, Any]) -> "ProviderResult":
        return cls.from_dict(validate_contract_envelope(value, "ProviderResult"))


@dataclass(frozen=True)
class EvidenceRecord:
    schema_version: str
    evidence_id: str
    task_id: str
    run_id: str
    action_id: str
    evidence_type: str
    payload: dict[str, Any]
    durability: str
    observation_state: str
    evidence_digest: str

    _required: ClassVar[set[str]] = {
        "schema_version", "evidence_id", "task_id", "run_id", "action_id", "evidence_type", "payload",
        "durability", "observation_state", "evidence_digest",
    }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, profile: SubAgentProfile | None = None) -> "EvidenceRecord":
        data = _object(value, name="EvidenceRecord", required=cls._required)
        _version(data["schema_version"])
        evidence_type = _text(data["evidence_type"], name="evidence_type")
        allowed_evidence = set(profile.required_evidence) if profile is not None else set(KNOWN_EVIDENCE)
        if evidence_type not in allowed_evidence:
            raise ContractValidationError("unsupported evidence_type")
        if not isinstance(data["payload"], Mapping) or not data["payload"]:
            raise ContractValidationError("EvidenceRecord payload must be an object")
        if data["durability"] != "durable" or data["observation_state"] != "observed":
            raise ContractValidationError("EvidenceRecord must be durable and observed")
        result = cls("1.1", _text(data["evidence_id"], name="evidence_id"), _text(data["task_id"], name="task_id"), _text(data["run_id"], name="run_id"), _text(data["action_id"], name="action_id"), evidence_type, dict(data["payload"]), "durable", "observed", _digest(data["evidence_digest"], name="evidence_digest"))
        _digest_match(result.to_dict(), field="evidence_digest", name="EvidenceRecord")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "evidence_id": self.evidence_id, "task_id": self.task_id,
            "run_id": self.run_id, "action_id": self.action_id, "evidence_type": self.evidence_type,
            "payload": dict(self.payload), "durability": self.durability, "observation_state": self.observation_state,
            "evidence_digest": self.evidence_digest,
        }

    def to_envelope(self) -> dict[str, Any]:
        return contract_envelope("EvidenceRecord", self.to_dict())

    @classmethod
    def from_envelope(cls, value: Mapping[str, Any], *, profile: SubAgentProfile | None = None) -> "EvidenceRecord":
        return cls.from_dict(validate_contract_envelope(value, "EvidenceRecord"), profile=profile)

    @classmethod
    def observed(
        cls,
        *,
        evidence_id: str,
        task_id: str,
        run_id: str,
        action_id: str,
        evidence_type: str,
        payload: dict[str, Any],
        profile: SubAgentProfile | None = None,
    ) -> "EvidenceRecord":
        value = {"schema_version": "1.1", "evidence_id": evidence_id, "task_id": task_id, "run_id": run_id, "action_id": action_id, "evidence_type": evidence_type, "payload": payload, "durability": "durable", "observation_state": "observed"}
        value["evidence_digest"] = digest_for(value, "evidence_digest")
        return cls.from_dict(value, profile=profile)


@dataclass(frozen=True)
class CompletionDecision:
    schema_version: str
    task_id: str
    run_id: str
    state: str
    final_revision: str | None
    evidence_ids: list[str]
    committed_action_ids: list[str]
    budget: dict[str, int]
    boundary_violations: list[str]
    reason: str
    decision_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "task_id": self.task_id, "run_id": self.run_id, "state": self.state,
            "final_revision": self.final_revision, "evidence_ids": list(self.evidence_ids), "committed_action_ids": list(self.committed_action_ids),
            "budget": dict(self.budget), "boundary_violations": list(self.boundary_violations), "reason": self.reason,
            "decision_digest": self.decision_digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CompletionDecision":
        data = _object(value, name="CompletionDecision", required={"schema_version", "task_id", "run_id", "state", "final_revision", "evidence_ids", "committed_action_ids", "budget", "boundary_violations", "reason", "decision_digest"})
        _version(data["schema_version"])
        if data["state"] not in {"eligible", "blocked"}:
            raise ContractValidationError("CompletionDecision state is invalid")
        result = cls("1.1", _text(data["task_id"], name="task_id"), _text(data["run_id"], name="run_id"), str(data["state"]), None if data["final_revision"] is None else _text(data["final_revision"], name="final_revision"), _list(data["evidence_ids"], name="evidence_ids"), _list(data["committed_action_ids"], name="committed_action_ids"), dict(data["budget"]), _list(data["boundary_violations"], name="boundary_violations"), _text(data["reason"], name="reason"), _digest(data["decision_digest"], name="decision_digest"))
        _digest_match(result.to_dict(), field="decision_digest", name="CompletionDecision")
        return result

    def to_envelope(self) -> dict[str, Any]:
        return contract_envelope("CompletionDecision", self.to_dict())

    @classmethod
    def from_envelope(cls, value: Mapping[str, Any]) -> "CompletionDecision":
        return cls.from_dict(validate_contract_envelope(value, "CompletionDecision"))

    @classmethod
    def _issue(cls, *, task_id: str, run_id: str, state: str, final_revision: str | None, evidence_ids: list[str], committed_action_ids: list[str], budget: dict[str, int], boundary_violations: list[str], reason: str) -> "CompletionDecision":
        value = {"schema_version": "1.1", "task_id": task_id, "run_id": run_id, "state": state, "final_revision": final_revision, "evidence_ids": evidence_ids, "committed_action_ids": committed_action_ids, "budget": budget, "boundary_violations": boundary_violations, "reason": reason}
        value["decision_digest"] = digest_for(value, "decision_digest")
        return cls("1.1", task_id, run_id, state, final_revision, evidence_ids, committed_action_ids, budget, boundary_violations, reason, value["decision_digest"])


class CompletionProof:
    """Single-use capability issued only after EvidenceCompletionGate checks."""

    def __init__(self, decision: CompletionDecision, token: str, *, issuer: object) -> None:
        if issuer is not _COMPLETION_PROOF_ISSUER:
            raise ContractValidationError("CompletionProof can only be issued by EvidenceCompletionGate")
        if not isinstance(decision, CompletionDecision) or not isinstance(token, str) or not token:
            raise ContractValidationError("CompletionProof is invalid")
        self._decision = decision
        self._token = token

    @classmethod
    def _issue(cls, decision: CompletionDecision) -> "CompletionProof":
        return cls(decision, secrets.token_urlsafe(32), issuer=_COMPLETION_PROOF_ISSUER)

    @property
    def state(self) -> str:
        return self._decision.state

    @property
    def decision_digest(self) -> str:
        return self._decision.decision_digest

    def to_dict(self) -> dict[str, Any]:
        return self._decision.to_dict()

    def consume(self) -> CompletionDecision:
        if not self._token:
            raise ContractValidationError("CompletionProof has already been consumed")
        token = self._token
        self._token = ""
        if not token:
            raise ContractValidationError("CompletionProof is invalid")
        return self._decision
