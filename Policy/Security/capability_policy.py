"""Read-only access to the canonical capability safety policy."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = Path("Policy/Security/tool-capability-policy.yaml")


def _load(root: Path) -> dict[str, Any]:
    value = yaml.safe_load((root / POLICY_PATH).read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError("tool capability policy must be a mapping")
    return value


def policy_for_capability(capability: str, *, root: Path = ROOT) -> dict[str, Any]:
    policy = _load(root)
    capabilities = policy.get("capabilities") or {}
    capability_policy = capabilities.get(capability)
    if not isinstance(capability_policy, dict):
        raise ValueError(f"unknown capability: {capability}")

    operation_kind = str(capability_policy.get("operation_kind") or "")
    operation_policy = (policy.get("operation_kinds") or {}).get(operation_kind)
    if not isinstance(operation_policy, dict):
        raise ValueError(f"unknown operation kind for capability {capability}: {operation_kind}")

    required_evidence = capability_policy.get("minimum_required_evidence") or []
    if not isinstance(required_evidence, list) or not required_evidence:
        raise ValueError(f"capability must define minimum evidence: {capability}")

    return {
        "capability": capability,
        "operation_kind": operation_kind,
        "risk_level": str(operation_policy["risk_level"]),
        "approval_requirement": str(operation_policy["approval_requirement"]),
        "requires_mutation_scope": operation_policy.get("requires_mutation_scope") is True,
        "default_permission": str(operation_policy["default_permission"]),
        "minimum_required_evidence": [str(item) for item in required_evidence],
    }
