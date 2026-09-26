"""Validate the Orchestration-to-Runtime handoff without selecting a Specialist."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator, ValidationError

from Persistence.Contracts.definition_fingerprint import validate_definition_fingerprint

ROOT = Path(__file__).resolve().parents[2]


def validate_runtime_handoff(handoff: Mapping[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    schema = yaml.safe_load((root / "Runtime/Contracts/runtime-handoff.schema.yaml").read_text(encoding="utf-8"))
    value = dict(handoff)
    try:
        Draft202012Validator(schema).validate(value)
    except ValidationError as exc:
        raise ValueError(f"Runtime Handoff contract invalid: {exc.message}") from exc
    action = value["runtime_action"]
    if action["kind"] == "specialist_reasoning":
        validate_definition_fingerprint(value["definition_fingerprint"])
        if value["execution_profile"] != "generic_planning":
            raise ValueError("reasoning handoff requires generic_planning")
        if any(request.get("capability") == action["capability"] for request in value["capability_requests"]):
            raise ValueError("reasoning handoff cannot dispatch its own capability through ToolBroker")
    for request in value["capability_requests"]:
        if not isinstance(request, dict) or any(key in request for key in ("provider", "provider_ref", "provider_id")):
            raise ValueError("handoff CapabilityRequests must not contain Provider identity")
    return value
