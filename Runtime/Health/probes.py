"""Read-only Runtime health probes. No repair and no hidden fallback."""
from __future__ import annotations
import shutil
from datetime import datetime, timezone
from pathlib import Path

from Runtime.Dispatcher.subprocess_dispatcher import DispatchRequest, dispatch


def _result(*, check_id: str, run_id: str, step_id: str, kind: str, target: str, status: str, details: dict, runtime_profile_revision: str, tool_schema_revision: str, evidence_refs: list[str] | None = None) -> dict:
    return {"schema_version": "1.0", "check_id": check_id, "run_id": run_id, "step_id": step_id, "kind": kind, "target": target, "status": status, "observed_at": datetime.now(timezone.utc).isoformat(), "evidence_refs": list(evidence_refs or []), "details": details, "runtime_profile_revision": runtime_profile_revision, "tool_schema_revision": tool_schema_revision}


def probe_environment(*, check_id: str, run_id: str, step_id: str, workspace: str, runtime_profile_revision: str, tool_schema_revision: str) -> dict:
    path = Path(workspace).expanduser().resolve()
    status = "healthy" if path.is_dir() else "unavailable"
    return _result(check_id=check_id, run_id=run_id, step_id=step_id, kind="environment", target=str(path), status=status, details={"workspace_exists": path.is_dir()}, runtime_profile_revision=runtime_profile_revision, tool_schema_revision=tool_schema_revision)


def probe_environment_snapshot(*, check_id: str, run_id: str, step_id: str, snapshot: dict, runtime_profile_revision: str, tool_schema_revision: str) -> dict:
    """Adapt Environment Snapshot facts into Health without making provider absence a global failure."""
    project = snapshot.get("project") or {}
    filesystem = snapshot.get("filesystem") or {}
    project_exists = project.get("exists")
    readable = filesystem.get("readable")
    if project_exists is True and readable is True:
        status = "healthy"
    elif project_exists is False or readable is False:
        status = "unavailable"
    else:
        status = "degraded"
    provider_summary = {
        "unity_cli": (snapshot.get("unity_cli") or {}).get("available", "unknown"),
        "myunitymcp": (snapshot.get("myunitymcp") or {}).get("available", "unknown"),
        "coplay_mcp": (snapshot.get("coplay_mcp") or {}).get("available", "unknown"),
        "native_unity_editor": (snapshot.get("unity_editor") or {}).get("installed", "unknown"),
        "player_runtime": (snapshot.get("player_runtime") or {}).get("reachable", "unknown"),
    }
    return _result(
        check_id=check_id,
        run_id=run_id,
        step_id=step_id,
        kind="environment_snapshot",
        target=str(project.get("root") or "unknown"),
        status=status,
        details={
            "profile_hint": snapshot.get("profile_hint"),
            "binding_fingerprint": snapshot.get("binding_fingerprint"),
            "provider_availability": provider_summary,
        },
        runtime_profile_revision=runtime_profile_revision,
        tool_schema_revision=tool_schema_revision,
    )


def probe_tool(*, check_id: str, run_id: str, step_id: str, executable: str, runtime_profile_revision: str, tool_schema_revision: str, cwd: str | None = None, health_args: list[str] | None = None, timeout_seconds: float = 10.0) -> dict:
    resolved = shutil.which(executable)
    if resolved is None:
        return _result(check_id=check_id, run_id=run_id, step_id=step_id, kind="tool_health", target=executable, status="unavailable", details={"executable_found": False}, runtime_profile_revision=runtime_profile_revision, tool_schema_revision=tool_schema_revision)
    details = {"executable_found": True, "resolved_path": resolved}
    status = "healthy"
    if health_args is not None:
        working = Path(cwd or ".").resolve()
        outcome = dispatch(DispatchRequest([resolved, *health_args], working, timeout_seconds))
        details["health_exit_code"] = outcome["result"].returncode
        status = "healthy" if outcome["status"] == "passed" else "degraded"
    return _result(check_id=check_id, run_id=run_id, step_id=step_id, kind="tool_health", target=executable, status=status, details=details, runtime_profile_revision=runtime_profile_revision, tool_schema_revision=tool_schema_revision)


def probe_unity(*, check_id: str, run_id: str, step_id: str, unity_executable: str | None, project_path: str | None, runtime_profile_revision: str, tool_schema_revision: str) -> dict:
    executable_ok = bool(unity_executable and Path(unity_executable).expanduser().is_file())
    project_ok = bool(project_path and Path(project_path).expanduser().is_dir())
    if executable_ok and project_ok:
        status = "healthy"
    elif executable_ok or project_ok:
        status = "degraded"
    else:
        status = "unavailable"
    return _result(check_id=check_id, run_id=run_id, step_id=step_id, kind="unity_availability", target=unity_executable or "Unity", status=status, details={"unity_executable_observed": executable_ok, "project_path_observed": project_ok}, runtime_profile_revision=runtime_profile_revision, tool_schema_revision=tool_schema_revision)
