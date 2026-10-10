"""Runtime validation for the immutable InstallReceipt boundary."""
from __future__ import annotations
from unityagent.resources import resource_root

from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = resource_root()
SCHEMA_PATH = Path("src/unityagent/runtime/contracts/install-receipt.schema.yaml")


def validate_install_receipt(value: dict[str, Any], *, root: Path = ROOT) -> None:
    schema = yaml.safe_load((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)
