"""Validation for Control Plane toolchain setup operations."""
from __future__ import annotations
from unityagent.resources import resource_root

from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = resource_root()
SCHEMA_PATH = Path("src/unityagent/runtime/contracts/toolchain-setup-request.schema.yaml")


def validate_toolchain_setup_request(value: dict[str, Any], *, root: Path = ROOT) -> None:
    schema = yaml.safe_load((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)
    if value["operation"] == "apply" and not value.get("expected_plan_id"):
        raise ValueError("apply requires expected_plan_id")
    if value["operation"] == "apply" and not value.get("approval_ref"):
        raise ValueError("apply requires approval_ref")
