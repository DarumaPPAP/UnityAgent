"""Adapt an authoritative Specialist reasoning handoff to the existing CodexRunner."""
from __future__ import annotations
from unityagent.resources import resource_root

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from unityagent.runtime.contracts.runtime_handoff import validate_runtime_handoff
from unityagent.runtime.contracts.reasoning_output import require_reasoning_output_contract
from unityagent.runtime.runner.codex.codex_runner import CodexRunnerError, _command_prefix, execute

ROOT = resource_root()


class ContextBindingError(ValueError):
    pass


def _repository_file(reference: str, root: Path) -> Path:
    path = (root / reference).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise ValueError(f"reasoning contract source is unavailable: {reference}")
    return path


def build_reasoning_request(handoff: Mapping[str, Any], manifest: Mapping[str, Any], *, original_project: Path, workspace: Path, model: str, model_revision: str | None = None, root: Path = ROOT) -> dict[str, Any]:
    value = validate_runtime_handoff(handoff, root=root)
    action = value["runtime_action"]
    if action["kind"] != "specialist_reasoning":
        raise ValueError("reasoning adapter requires specialist_reasoning action")
    require_reasoning_output_contract(action["output_contract_ref"])
    view = manifest.get("materialized_context")
    if not isinstance(view, dict) or not isinstance(view.get("specialist_context"), dict):
        raise ValueError("materialized Specialist Context is required")
    if (view.get("context_id"), (view.get("context_fingerprint") or {}).get("value")) != (value["context_id"], value["context_fingerprint"]):
        raise ContextBindingError("Context Manifest identity differs from unityagent.runtime Handoff")
    specialist = view["specialist_context"]
    if any(specialist.get(key) != action[key] for key in ("profile_id", "capability", "execution_mode", "provider_resolution")):
        raise ContextBindingError("Specialist Context differs from unityagent.runtime Handoff")
    if not isinstance(model, str) or not model.strip():
        raise CodexRunnerError("host-selected reasoning model is required")
    instructions = _repository_file(action["instructions_ref"], root).read_text(encoding="utf-8")
    schema = json.loads(_repository_file(action["output_contract_ref"], root).read_text(encoding="utf-8"))
    workspace.mkdir(parents=True, exist_ok=False)
    context = {"context_id": value["context_id"], "context_fingerprint": value["context_fingerprint"], "specialist_context": specialist}
    (workspace / "specialist-context.json").write_text(json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (workspace / "specialist-instructions.md").write_text(instructions, encoding="utf-8")
    (workspace / "output-schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prompt = f"{instructions}\n\nMaterialized Specialist src/unityagent/context:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\nStructured output contract:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n"
    return {"schema_version": "1.0", "run_id": value["run_id"], "step_id": value["step_id"], "action_id": value["action_id"], "workspace_root": str(workspace), "original_workspace_root": str(original_project), "prompt": prompt, "execution": {"profile": value["execution_profile"], "work_kind": "analysis", "reasoning": True, "mutation_authorized": False}, "mutation_scope": {}, "output_schema_path": str(workspace / "output-schema.json"), "profile_id": action["profile_id"], "capability": action["capability"], "source_context_id": value["context_id"], "source_context_fingerprint": value["context_fingerprint"], "tool_identity": {"provider": "openai", "model": model, "model_revision": model_revision or "not_observed", "tool_manifest_hash": "not_applicable_reasoning_runtime"}, "definition_fingerprint": value["definition_fingerprint"]}


def execute_reasoning(handoff: Mapping[str, Any], manifest: Mapping[str, Any], *, original_project: Path, output: Path, model: str, model_revision: str | None = None, command_prefix: list[str] | None = None, timeout_seconds: float = 120.0, reasoning_effort: str = "high", root: Path = ROOT) -> tuple[dict[str, Any], dict[str, Any] | None]:
    with tempfile.TemporaryDirectory(prefix="unityagent-reasoning-") as temporary:
        workspace = Path(temporary) / "workspace"
        runtime_output = Path(temporary) / "output"
        request = build_reasoning_request(handoff, manifest, original_project=original_project, workspace=workspace, model=model, model_revision=model_revision, root=root)
        prefix = command_prefix if command_prefix is not None else _command_prefix(None)
        execution = execute(request, runtime_output, command_prefix=prefix, timeout_seconds=timeout_seconds, reasoning_effort=reasoning_effort)
        artifact = json.loads((runtime_output / "response.json").read_text(encoding="utf-8")) if execution["status"] == "passed" else None
        if output.exists():
            raise ValueError("reasoning output directory already exists")
        shutil.copytree(runtime_output, output)
    return execution, artifact
