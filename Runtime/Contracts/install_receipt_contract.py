"""Runtime validation for the immutable InstallReceipt boundary."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path("Runtime/Contracts/install-receipt.schema.yaml")


def validate_install_receipt(value: dict[str, Any], *, root: Path = ROOT) -> None:
    schema = yaml.safe_load((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)
