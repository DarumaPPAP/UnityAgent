"""Pure task DAG and resource-conflict planner.

This is a proposal only. Runtime Resource Lease / Unity Editor / Policy enforce
access; a 'parallel' result never grants write rights or starts processes.
"""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any


def _normalize_resource(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("resource identifier must be a non-empty string")
    value = value.strip().replace("\\", "/").casefold().rstrip("/")
    if ".." in value.split("/") or "\x00" in value:
        raise ValueError("resource identifier is not confined")
    return value


def _overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _conflicts(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    if set(a["resource_claims"]) & set(b["resource_claims"]):
        return True
    # Main Editor & asset workspace mutation is serialized even with disjoint files.
    same = a["workspace"] == b["workspace"]
    if same and (a["write_set"] or b["write_set"]):
        return True
    if not same:
        return False
    return any(_overlap(x, y) for x in a["write_set"] for y in b["write_set"])


def plan_task_batches(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """DAG waves, deterministic ordering and conservative resource claims.

    Worktrees are not created here: task.workspace is a verified, distinct
    Unity Project identity supplied by Runtime. Empty identity never schedules.
    """
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("at least one task is required")
    by_id: dict[str, dict[str, Any]] = {}
    for item in tasks:
        if not isinstance(item, dict):
            raise ValueError("task must be an object")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in by_id:
            raise ValueError("missing or duplicate task id")
        workspace = item.get("workspace")
        if not isinstance(workspace, str) or not workspace.strip():
            raise ValueError("each task needs a bound workspace identity")
        deps = item.get("depends_on", [])
        writes = item.get("write_set", [])
        claims = item.get("resource_claims", [])
        if any(not isinstance(x, list) for x in (deps, writes, claims)):
            raise ValueError("dependencies/write_set/resource_claims must be lists")
        if not all(isinstance(x, str) and x for x in deps):
            raise ValueError("invalid dependency")
        if len(set(deps)) != len(deps) or identifier in deps:
            raise ValueError("duplicate or self dependency")
        by_id[identifier] = {
            "depends_on": set(deps),
            "workspace": _normalize_resource(workspace),
            "write_set": tuple(_normalize_resource(x) for x in writes),
            "resource_claims": tuple(_normalize_resource(x) for x in claims),
            "parallel_safe": item.get("parallel_safe") is True,
        }
    for identifier, task in by_id.items():
        if task["depends_on"] - by_id.keys():
            raise ValueError("unknown dependency for task: " + identifier)

    pending = set(by_id)
    complete: set[str] = set()
    batches: list[dict[str, Any]] = []
    while pending:
        ready = sorted(x for x in pending if by_id[x]["depends_on"] <= complete)
        if not ready:
            raise ValueError("cyclic task dependencies; refuse execution")
        selected: list[str] = []
        for identifier in ready:
            candidate = by_id[identifier]
            if not selected or (
                    candidate["parallel_safe"] and all(
                    by_id[x]["parallel_safe"] and not _conflicts(candidate, by_id[x])
                    for x in selected)):
                selected.append(identifier)
        batches.append({
            "task_ids": selected,
            "execution": "parallel" if len(selected) > 1 else "serial",
            "resource_claims": sorted({claim for x in selected for claim in by_id[x]["resource_claims"]}),
            "runtime_lease_required": True,
        })
        pending.difference_update(selected)
        complete.update(selected)
    return {"schema_version": "1.0", "status": "planned", "batches": batches,
            "execution_owner": "UnityAgent Runtime", "approval_required": "consult_policy"}


def plan_ready_batch(tasks, *, verified_task_ids, parallel_enabled, workspace_status, pending_task_ids=None):
    """現行Planの成功依存だけを開き、実行提案を最大2件に制限する。"""
    plan_task_batches(tasks)
    if not isinstance(parallel_enabled, bool):
        raise ValueError('Parallel execution mode must be boolean')
    by_id = {task['id']: task for task in tasks}
    if set(verified_task_ids) - by_id.keys():
        raise ValueError('Verified Task set differs from the current Plan')
    pending = set(by_id) - set(verified_task_ids) if pending_task_ids is None else set(pending_task_ids)
    if pending - by_id.keys() or pending & set(verified_task_ids):
        raise ValueError('Pending Task set differs from the current Plan')
    ready = sorted(name for name, task in by_id.items() if name in pending
                   and set(task.get('depends_on', [])) <= set(verified_task_ids))
    if not ready:
        return []
    if not parallel_enabled or workspace_status != 'verified':
        return ready[:1]
    candidates = [{**by_id[name], 'depends_on': []} for name in ready]
    selected = plan_task_batches(candidates)['batches'][0]['task_ids'][:2]
    if len(selected) == 2:
        # 同じ元Projectへ統合する変更候補の競合も、worker起動前に直列化する。
        left, right = (by_id[name] for name in selected)
        if any(_overlap(_normalize_resource(a), _normalize_resource(b))
               for a in left.get('write_set', []) for b in right.get('write_set', [])):
            return selected[:1]
    return selected
