#!/usr/bin/env python3
"""Validate the canonical user policy after Phase 8 cutover.

This replaces migration-source byte-equivalence checks. The migration source is intentionally
removed at cutover; the canonical policy remains protected and authoritative.
"""
from __future__ import annotations
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "Policy/User/user-policy.yaml"
RISK = ROOT / "Policy/Risk/risk-levels.yaml"

REQUIRED_CORE = {
    "engineering_principles",
    "single_purpose_change",
    "no_unrequested_implementation",
    "preserve_existing_structure",
    "preserve_current_naming_convention",
    "semantic_type_naming",
    "evidence_scoped_claims",
    "performance_requires_measurement",
}


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    policy_path = root / "Policy/User/user-policy.yaml"
    risk_path = root / "Policy/Risk/risk-levels.yaml"
    if not policy_path.is_file():
        return ["missing canonical user policy"]
    if not risk_path.is_file():
        errors.append("missing canonical risk policy")
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    if policy.get("policy_owner") != "user":
        errors.append("canonical policy_owner must be user")
    if policy.get("status") != "authoritative":
        errors.append("canonical user policy must remain authoritative")
    rules = policy.get("rules") or {}
    for key in (
        "generic_best_practice_must_not_override_user_policy",
        "external_reference_must_not_override_user_policy",
        "older_policy_must_not_overwrite_current_policy",
        "policy_deletion_requires_explicit_user_approval",
        "policy_simplification_requires_no_policy_loss_review",
    ):
        if rules.get(key) is not True:
            errors.append(f"protected user policy rule missing or weakened: {key}")
    core = policy.get("core_user_policies") or {}
    for key in sorted(REQUIRED_CORE):
        item = core.get(key)
        if not isinstance(item, dict) or not str(item.get("rule") or "").strip():
            errors.append(f"protected core user policy missing: {key}")
    if not isinstance(policy.get("comment_system"), dict):
        errors.append("protected comment_system is missing")
    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Canonical user policy integrity: OK")
