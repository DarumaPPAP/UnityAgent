"""Resolved Native Unity Editor capability を既存 Runtime harness へ接続する adapter。"""
from __future__ import annotations

import threading
from typing import Any

from Runtime.Tooling.Providers.NativeUnityEditor.native_unity_editor_provider import NativeUnityEditorProvider


def run_native_editor_capability(
    provider: NativeUnityEditorProvider,
    capability_request: dict[str, Any],
    *,
    run_id: str,
    timeout_seconds: float,
    policy_allowed: bool,
    approval_required: bool = False,
    approval_complete: bool = False,
    cancel_event: threading.Event | None = None,
    test_platform: str = "EditMode",
    build_output_relative_path: str | None = None,
    active_build_profile: str | None = None,
) -> dict[str, Any]:
    capability = str(capability_request.get("capability") or "")
    common = {
        "run_id": run_id,
        "timeout_seconds": timeout_seconds,
        "policy_allowed": policy_allowed,
        "approval_required": approval_required,
        "approval_complete": approval_complete,
        "cancel_event": cancel_event,
    }
    if capability == "compile.observe":
        return provider.run_compile(capability_request, **common)
    if capability == "project.test":
        return provider.run_tests(capability_request, test_platform=test_platform, **common)
    if capability == "project.build":
        if not build_output_relative_path:
            return {"status": "failed", "failure_class": "precondition_failed", "reason": "build_output_relative_path is required for project.build", "provider_ref": "native_unity_editor", "evidence": []}
        return provider.run_build(capability_request, build_output_relative_path=build_output_relative_path, active_build_profile=active_build_profile, **common)
    return {"status": "failed", "failure_class": "unsupported", "reason": f"Native Unity Editor adapter does not execute capability: {capability}", "provider_ref": "native_unity_editor", "evidence": []}
