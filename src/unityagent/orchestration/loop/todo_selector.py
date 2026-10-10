"""Select the next semantic TODO without owning execution or durable scheduling."""
from __future__ import annotations

from typing import Any


def select_todo(todos: list[dict[str, Any]]) -> dict[str, Any] | None:
    ids = [str(todo.get("id") or "") for todo in todos]
    if any(not item for item in ids):
        raise ValueError("semantic TODO id must not be empty")
    if len(set(ids)) != len(ids):
        raise ValueError("semantic TODO ids must be unique")

    known = set(ids)
    completed = {
        str(todo["id"])
        for todo in todos
        if todo.get("status") == "completed"
    }
    ready: list[dict[str, Any]] = []

    for todo in todos:
        if todo.get("status", "ready") != "ready":
            continue
        dependencies = [str(item) for item in (todo.get("depends_on") or [])]
        unknown = sorted(set(dependencies) - known)
        if unknown:
            raise ValueError(
                f"semantic TODO {todo['id']} references unknown dependencies: {unknown}"
            )
        if all(item in completed for item in dependencies):
            ready.append(todo)

    if not ready:
        return None

    ready.sort(key=lambda item: (-int(item.get("priority", 0)), str(item["id"])))
    return ready[0]
