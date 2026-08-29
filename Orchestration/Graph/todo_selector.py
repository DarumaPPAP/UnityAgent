"""Semantic TODO selection only. No quota, lease, timeout, process or durable-state accounting."""
from __future__ import annotations
from typing import Any


def select_todo(todos: list[dict[str, Any]]) -> dict[str, Any] | None:
    completed = {str(todo.get("id")) for todo in todos if todo.get("status") == "completed"}
    ready: list[dict[str, Any]] = []
    for todo in todos:
        if todo.get("status", "ready") != "ready":
            continue
        dependencies = [str(item) for item in (todo.get("depends_on") or [])]
        if all(item in completed for item in dependencies):
            ready.append(todo)
    if not ready:
        return None
    ready.sort(key=lambda item: (-int(item.get("priority", 0)), str(item.get("id", ""))))
    return ready[0]
