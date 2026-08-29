"""Create non-applying Eval ChangeProposal records."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

AUTHORITIES = {"Policy", "Context", "Orchestration", "Runtime", "Persistence", "Operations", "Eval"}


class ChangeProposalError(ValueError):
    pass


def build_change_proposal(
    *,
    proposal_id: str,
    source_eval_refs: list[str],
    target_authority: str,
    proposed_change: str,
    rationale: str,
    evidence_refs: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if target_authority not in AUTHORITIES:
        raise ChangeProposalError(f"unknown target_authority: {target_authority}")
    refs = list(dict.fromkeys(str(item) for item in source_eval_refs if str(item)))
    if not proposal_id or not refs or not proposed_change.strip() or not rationale.strip():
        raise ChangeProposalError("proposal_id, source_eval_refs, proposed_change and rationale are required")
    return {
        "schema_version": "1.0",
        "proposal_id": proposal_id,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "source_eval_refs": refs,
        "target_authority": target_authority,
        "proposed_change": proposed_change.strip(),
        "rationale": rationale.strip(),
        "evidence_refs": list(dict.fromkeys(str(item) for item in (evidence_refs or []) if str(item))),
        "status": "proposed",
        "applies_change": False,
        "requires_human_review": True,
    }
