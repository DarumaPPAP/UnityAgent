"""Runtime mutation enforcement; classification quality remains Eval-owned."""
from __future__ import annotations
from Runtime.Sandbox.workspace_guard import normalize_relative_path


def _matches(path: str, scope: str) -> bool:
    return path == scope or path.startswith(scope + "/")


def evaluate_mutation_scope(*, work_kind: str, changed_paths: list[str], allowed_paths: list[str] | None = None, prohibited_paths: list[str] | None = None) -> dict:
    changed = [normalize_relative_path(path) for path in changed_paths]
    allowed = [normalize_relative_path(path) for path in (allowed_paths or [])]
    prohibited = [normalize_relative_path(path) for path in (prohibited_paths or [])]

    if work_kind in {"analysis", "verification"} and changed:
        return {"status": "failed", "reason": "non_mutating_work_changed_workspace", "scope_status": "escaped"}
    prohibited_hits = [path for path in changed if any(_matches(path, scope) for scope in prohibited)]
    if prohibited_hits:
        return {"status": "failed", "reason": "prohibited_path_mutated", "paths": prohibited_hits, "scope_status": "escaped"}
    if allowed:
        outside = [path for path in changed if not any(_matches(path, scope) for scope in allowed)]
        if outside:
            return {"status": "failed", "reason": "mutation_escaped_allowed_scope", "paths": outside, "scope_status": "escaped"}
    return {"status": "passed", "reason": None, "scope_status": "within_scope"}
