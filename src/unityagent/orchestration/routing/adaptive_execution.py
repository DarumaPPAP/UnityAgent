"""Pure adaptive execution selection. Authority and approvals stay with UnityAgent.

This function decides *coordination cost*, never execution permission or success.
A SubAgent selection is a semantic constraint, not authorization to mutate.
"""
from __future__ import annotations

from typing import Any

PATHS = ("fast", "standard", "orchestrated")
RISK = {"low", "medium", "high", "critical"}
DESIGN = {"not_required", "conditional", "required"}
CONTEXT = {"tight", "standard", "wide"}


def select_execution_path(
    *,
    task_count: int,
    simple_task: bool,
    risk: str,
    design_review: str,
    requires_replan: bool,
    project_bound: bool,
    scope_known: bool,
    requested_subagent: str | None = None,
    required_subagents: tuple[str, ...] = (),
    resource_conflict: bool = False,
    context_profile: str = "tight",
) -> dict[str, Any]:
    """Choose a bounded path without allocating extra agents or worktrees.

    The returned plan is *not* permission to execute. Caller must enforce
    Project binding, existing Policy/Approval/Scope, resource leases, and
    evidence before/after Runtime dispatch. Unknown prerequisites fail closed.
    """
    if isinstance(task_count, bool) or not isinstance(task_count, int) or task_count < 1:
        raise ValueError("task_count must be a positive integer")
    if not all(isinstance(v, bool) for v in
               (simple_task, requires_replan, project_bound, scope_known, resource_conflict)):
        raise ValueError("adaptive execution requires observed boolean facts")
    if risk not in RISK or design_review not in DESIGN or context_profile not in CONTEXT:
        raise ValueError("unknown risk, design review, or context profile")
    if not isinstance(required_subagents, tuple) or any(
            not isinstance(x, str) or not x.endswith("_subagent") for x in required_subagents):
        raise ValueError("required_subagents must contain canonical SubAgent ids")
    if requested_subagent is not None and (
            not isinstance(requested_subagent, str) or not requested_subagent.endswith("_subagent")):
        raise ValueError("invalid explicitly requested SubAgent")
    if not project_bound or not scope_known:
        return {
            "status": "blocked",
            "path": None,
            "reason": "project binding or scope unknown; fail closed",
            "subagent_ids": [],
            "parent_graph_required": False,
            "worktree_required": False,
            "context_profile": context_profile,
            "approval_required": "consult_policy",
            "evidence_required": True,
        }

    selected = tuple(dict.fromkeys(required_subagents +
                    ((requested_subagent,) if requested_subagent else ())))
    # Explicit selection cannot override an incompatible authority decision.
    if requested_subagent is not None and required_subagents and \
            requested_subagent not in required_subagents:
        return {
            "status": "blocked", "path": None,
            "reason": "requested SubAgent is incompatible with resolved task ownership",
            "subagent_ids": list(selected),
            "parent_graph_required": False, "worktree_required": False,
            "context_profile": context_profile,
            "approval_required": "consult_policy", "evidence_required": True,
        }

    multi = task_count > 1 or len(selected) > 1 or resource_conflict
    bounded = (simple_task and risk == "low" and design_review == "not_required" and
               not requires_replan and not selected and not multi and context_profile == "tight")
    path = "orchestrated" if multi else "fast" if bounded else "standard"
    return {
        "status": "planned",
        "path": path,
        "reason": {
            "fast": "bounded direct execution without additional agent/graph/worktree",
            "standard": "single bounded task requires specialist or enhanced verification",
            "orchestrated": "multiple tasks, specialists, or resource conflicts require coordination",
        }[path],
        "subagent_ids": list(selected),
        "parent_graph_required": path == "orchestrated",
        "worktree_required": False,  # Scheduler decides only after resource/path analysis.
        "context_profile": "tight" if path == "fast" else context_profile,
        "approval_required": "consult_policy",
        "evidence_required": True,
    }
