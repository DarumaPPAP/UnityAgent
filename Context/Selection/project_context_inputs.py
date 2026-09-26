"""Project observations and explicit task inputs for the existing Context Manifest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from Runtime.Tooling.Environment.project_identity import read_project_version, same_project_root


def derive_context_inputs(project_root: str, snapshot: dict[str, Any], intent: dict[str, Any], *, attempt: int = 1) -> dict[str, Any]:
    observed = snapshot.get("project") or {}
    if observed.get("identity_status") != "bound" or not same_project_root(project_root, str(observed.get("root") or "")):
        raise ValueError("EnvironmentSnapshot is not bound to the requested project")
    source = Path(project_root) / "ProjectSettings/ProjectVersion.txt"
    version = read_project_version(project_root)
    if not version or version != observed.get("unity_version"):
        raise ValueError("Project version is missing or differs from EnvironmentSnapshot")
    revision = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    freshness = {"status": "current", "checked_at_attempt": attempt}
    fact = {"key": "unity_version", "value": version, "source_kind": "detected_project",
            "source_path": str(source), "revision": revision, "observed_at_attempt": attempt,
            "freshness": freshness, "reason": "reobserved ProjectVersion.txt and matched bound EnvironmentSnapshot"}
    specialist_tag = "rendering" if intent.get("kind") == "rendering_diagnosis" else "camera"
    items = [{"category": "project_fact", "key": "unity_version", "value": version, "source": str(source),
              "revision": revision, "freshness": freshness, "observed_at_attempt": attempt,
              "tags": [specialist_tag], "required": True}]
    environment_revision = "sha256:" + hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()
    request_revision = "sha256:" + hashlib.sha256(json.dumps(intent, sort_keys=True, default=str).encode()).hexdigest()
    platform = (snapshot.get("build") or {}).get("requested_target")
    if isinstance(platform, str) and platform and platform != "unknown":
        items.append({"category": "platform_fact", "key": "requested_target", "value": platform,
                      "source": "EnvironmentSnapshot.build.requested_target", "revision": environment_revision,
                      "freshness": freshness, "observed_at_attempt": attempt, "tags": [specialist_tag]})
    scope = intent.get("target_scope") if specialist_tag == "rendering" else intent.get("exact_scene_or_asset_scope")
    if isinstance(scope, str) and scope:
        items.append({"category": "task_fact", "key": "requested_scope", "value": scope,
                      "source": "user:request.intent.target_scope" if specialist_tag == "rendering" else "user:request.intent.exact_scene_or_asset_scope", "revision": request_revision,
                      "freshness": freshness, "observed_at_attempt": attempt, "tags": [specialist_tag], "required": True})
    if specialist_tag == "rendering":
        items.append({"category": "task_fact", "key": "rendering_symptom", "value": intent["symptom"], "source": "user:request.intent.symptom", "revision": request_revision, "freshness": freshness, "observed_at_attempt": attempt, "tags": [specialist_tag], "required": True})
    bindings: dict[str, Any] = {"project_root": {"value": str(observed["root"]), "source_kind": "environment_snapshot",
        "revision": environment_revision, "freshness": freshness}}
    if isinstance(intent.get("kind"), str) and intent["kind"]:
        bindings["goal"] = {"value": intent["kind"], "source_kind": "user_request",
                            "revision": request_revision, "freshness": freshness}
    for key in ("visual_intent", "exact_scene_or_asset_scope", "reference_or_visual_definition"):
        value = intent.get(key)
        if isinstance(value, str) and value:
            bindings[key] = {"value": value, "source_kind": "user_request", "revision": request_revision,
                             "freshness": freshness}
    required_keys = {"project_fact:unity_version", "task_fact:requested_scope"}
    if specialist_tag == "rendering":
        required_keys.add("task_fact:rendering_symptom")
    return {"project_facts": [fact], "specialist_items": items, "bindings": bindings,
            "specialist_tags": {specialist_tag}, "required_specialist_keys": required_keys}
