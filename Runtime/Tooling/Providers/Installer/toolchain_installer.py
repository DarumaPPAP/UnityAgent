"""Composite installer backend for approved UnityAgent toolchain plans."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Mapping

from Runtime.Tooling.Providers.Installer.codex_plugin_installer import (
    CommandRunner,
    CodexPluginInstallError,
    ensure_codex_plugin,
    run_command,
)
from Runtime.Tooling.Providers.Installer.release_installer import (
    ReleaseInstallError,
    install_plan as install_release_plan,
)

CHANNEL = "0.0.4-beta"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def install_toolchain_plan(
    plan: Mapping[str, object],
    *,
    which_fn: Callable[[str], str | None],
    command_runner: CommandRunner = run_command,
) -> dict[str, object]:
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ReleaseInstallError("approved setup plan has no actions")

    release_actions: list[Mapping[str, object]] = []
    codex_actions: list[Mapping[str, object]] = []
    for action in actions:
        if not isinstance(action, Mapping):
            raise ReleaseInstallError("approved setup plan contains a malformed action")
        product = str(action.get("product") or "")
        if product in {"official_unity_cli", "unity_artist_cli"}:
            release_actions.append(action)
        elif product in {"codex_cli", "unity_agent_codex_plugin"}:
            codex_actions.append(action)
        else:
            raise ReleaseInstallError(f"unsupported install product: {product}")

    entries: list[dict[str, object]] = []
    if release_actions:
        release_result = install_release_plan({**dict(plan), "actions": release_actions})
        entries.extend(dict(entry) for entry in release_result.get("entries", []))

    codex_path = which_fn("codex")
    for action in codex_actions:
        hinted = action.get("codex_cli_path") or (action.get("location") if action.get("product") == "codex_cli" else None)
        if hinted:
            codex_path = str(hinted)

    for action in codex_actions:
        product = str(action.get("product") or "")
        action_name = str(action.get("action") or "")
        if product == "codex_cli":
            entries.append({
                "product": product,
                "status": "verified" if codex_path else "unavailable",
                "version": action.get("version"),
                "location": codex_path,
                "source": action.get("source") or "PATH",
                "sha256": None,
            })
            continue
        if action_name == "verify":
            entries.append({
                "product": product,
                "status": "verified",
                "version": action.get("version"),
                "location": action.get("location"),
                "source": action.get("source"),
                "sha256": None,
            })
            continue
        if action_name in {"manual_required", "blocked_by_dependency", "blocked_by_observation"}:
            entries.append({
                "product": product,
                "status": "unavailable",
                "version": action.get("version"),
                "location": action.get("location"),
                "source": action.get("source"),
                "sha256": None,
            })
            continue
        if action_name != "install_then_verify":
            raise ReleaseInstallError(f"unsupported installer action: {action_name}")
        try:
            entries.append(ensure_codex_plugin(codex_path, runner=command_runner))
        except CodexPluginInstallError as exc:
            raise ReleaseInstallError(str(exc)) from exc

    status = "passed" if entries and all(
        str(entry.get("status")) in {"installed", "verified"} for entry in entries
    ) else "unavailable"
    channel = str(plan.get("channel") or CHANNEL)
    return {
        "schema_version": "1.0",
        "operation": "apply",
        "status": status,
        "project_root": str(plan.get("project_root") or ""),
        "channel": channel,
        "plan_id": plan.get("plan_id"),
        "entries": entries,
        "install_receipt": {
            "schema_version": "1.0",
            "receipt_id": f"receipt-{plan.get('plan_id') or 'unknown'}",
            "run_id": "pending",
            "project_root": str(plan.get("project_root") or ""),
            "channel": channel,
            "entries": entries,
            "verified_at": _now(),
            "evidence_refs": [],
        },
    }
