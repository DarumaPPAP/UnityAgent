"""Runtime profile/approval enforcement. Route selection is intentionally absent."""
from __future__ import annotations


class RuntimePermissionError(PermissionError):
    pass


def enforce_permission(*, profile: dict, work_kind: str, mutation_authorized: bool, human_approval_required: bool = False, human_approval_granted: bool = False) -> None:
    allowed = set(profile.get("allowed_work_kinds", []) or [])
    if work_kind not in allowed:
        raise RuntimePermissionError(f"work kind is not permitted by runtime profile: {work_kind}")
    if work_kind in {"mutation", "portable_import"}:
        if not mutation_authorized:
            raise RuntimePermissionError("mutation is not authorized")
        if human_approval_required and not human_approval_granted:
            raise RuntimePermissionError("required human approval is not satisfied")
