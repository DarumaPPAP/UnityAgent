#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import importlib.util
from pathlib import Path
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG = Path("Context/Selection/context-catalog.yaml")

def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

resolver = _load_module("context_path_resolver", ROOT / "Context/Selection/path_resolver.py")
budget = _load_module("context_budget_runtime", ROOT / "Context/Budget/budget_runtime.py")

def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return value

def _revision(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return f"sha256:{hashlib.sha256(data).hexdigest()}", len(data)

def _selected_ref(logical_ref: str, role: str, root: Path) -> dict[str, Any]:
    path = resolver.resolve_for_read(logical_ref, root)
    if not path.is_file():
        raise FileNotFoundError(f"selected context source does not exist: {logical_ref} -> {path}")
    revision, size = _revision(path)
    return {
        "logical_ref": logical_ref,
        "resolved_path": path.relative_to(root.resolve()).as_posix(),
        "revision": revision,
        "selected_utf8_bytes": size,
        "role": role,
    }

def _append_unique(items: list[dict[str, Any]], value: dict[str, Any]) -> None:
    key = value["resolved_path"]
    if all(item["resolved_path"] != key for item in items):
        items.append(value)

def _process_entry(entry: Any, *, requirement: str, condition: str | None, root: Path, bindings: dict[str, Any], required_context: list[dict[str, Any]], conditional_context: list[dict[str, Any]], context_includes: list[dict[str, Any]], external_references: list[dict[str, Any]], unresolved: list[str], missing_observations: list[str]) -> None:
    if not isinstance(entry, dict):
        raise ValueError("Context Pack typed entries must be mappings")
    kind = str(entry.get("type", "")).strip()
    if kind == "binding":
        name = str(entry.get("name", "")).strip()
        if not name:
            raise ValueError("binding entry requires name")
        if name not in bindings:
            if requirement == "required":
                unresolved.append(f"binding:{name}")
                missing_observations.append(f"binding:{name}")
        else:
            value = bindings[name]
            if isinstance(value, str) and value:
                candidate = Path(value)
                if candidate.is_absolute():
                    missing_observations.append(f"project:{name}")
                else:
                    local = (root / candidate).resolve()
                    if local.is_file() and (local == root or root in local.parents):
                        target = _selected_ref(candidate.as_posix(), "target_source", root)
                        bucket = required_context if requirement == "required" else conditional_context
                        _append_unique(bucket, target)
                    else:
                        missing_observations.append(f"project:{name}")
        return
    if kind == "repository_reference":
        logical = str(entry.get("path", "")).strip()
        if not logical:
            raise ValueError("repository_reference requires path")
        role = "required_context" if requirement == "required" else "conditional_context"
        selected = _selected_ref(logical, role, root)
        bucket = required_context if requirement == "required" else conditional_context
        _append_unique(bucket, selected)
        return
    if kind == "external_reference":
        repository = str(entry.get("repository", "")).strip()
        path = str(entry.get("path", "")).strip()
        if not repository or not path:
            raise ValueError("external_reference requires repository and path")
        external_references.append({"repository": repository, "path": path, "requirement": requirement, "condition": condition})
        if requirement == "required":
            missing_observations.append(f"external:{repository}:{path}")
        return
    if kind == "context_include":
        context_id = str(entry.get("context_id", "")).strip()
        if not context_id:
            raise ValueError("context_include requires context_id")
        logical = f"Context/Packs/{context_id}.yaml"
        path = root / logical
        if path.is_file():
            _append_unique(context_includes, _selected_ref(logical, "context_include", root))
        elif requirement == "required":
            unresolved.append(f"context_include:{context_id}")
            missing_observations.append(f"context_include:{context_id}")
        return
    if kind == "route_handoff":
        route_id = str(entry.get("route_id", "")).strip()
        if not route_id:
            raise ValueError("route_handoff requires route_id")
        if requirement == "required":
            unresolved.append(f"route_handoff:{route_id}")
        return
    raise ValueError(f"Unsupported Context Pack entry type: {kind}")

def _policy_revision(policy_refs: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for item in sorted(policy_refs, key=lambda x: x["resolved_path"]):
        h.update(item["resolved_path"].encode())
        h.update(item["revision"].encode())
    return f"sha256:{h.hexdigest()}"

def materialize_context(run_id: str, route_id: str, prompt_spec_ref: str | None = None, bindings: dict[str, Any] | None = None, active_conditions: set[str] | None = None, knowledge_refs: list[str] | None = None, memory_projection_refs: list[str] | None = None, tool_schema_refs: list[str] | None = None, root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    bindings = dict(bindings or {})
    conditions = set(active_conditions or set())
    catalog = _yaml(root / CATALOG)
    routes = catalog.get("routes") or {}
    if route_id not in routes:
        raise ValueError(f"Unknown route id: {route_id}")
    route = routes[route_id]
    if not isinstance(route, dict):
        raise ValueError(f"Invalid route materialization entry: {route_id}")
    policy_refs = [_selected_ref(str(catalog["user_policy"]), "user_policy", root)]
    pack = _selected_ref(str(route["context_pack"]), "context_pack", root)
    skill = _selected_ref(str(route["primary_skill"]), "primary_skill", root)
    task = _selected_ref(str(route["task_contract"]), "task_contract", root)
    pack_document = _yaml(root / pack["resolved_path"])
    prompt_ref = None
    prompt_revision = "unbound"
    if prompt_spec_ref:
        prompt_ref = _selected_ref(prompt_spec_ref, "prompt_spec", root)
        prompt_revision = prompt_ref["revision"]
    required_context: list[dict[str, Any]] = []
    conditional_context: list[dict[str, Any]] = []
    context_includes: list[dict[str, Any]] = []
    external_references: list[dict[str, Any]] = []
    unresolved: list[str] = []
    missing_observations: list[str] = []
    for entry in pack_document.get("required", []) or []:
        _process_entry(entry, requirement="required", condition=None, root=root, bindings=bindings, required_context=required_context, conditional_context=conditional_context, context_includes=context_includes, external_references=external_references, unresolved=unresolved, missing_observations=missing_observations)
    conditional = pack_document.get("conditional", {}) or {}
    if not isinstance(conditional, dict):
        raise ValueError("Context Pack conditional section must be a mapping")
    for condition in sorted(conditions):
        entries = conditional.get(condition, []) or []
        if not isinstance(entries, list):
            raise ValueError(f"Context Pack condition must contain a list: {condition}")
        for entry in entries:
            _process_entry(entry, requirement="conditional", condition=condition, root=root, bindings=bindings, required_context=required_context, conditional_context=conditional_context, context_includes=context_includes, external_references=external_references, unresolved=unresolved, missing_observations=missing_observations)
    knowledge: list[dict[str, Any]] = []
    for logical in knowledge_refs or []:
        _append_unique(knowledge, _selected_ref(logical, "knowledge", root))
    if route.get("knowledge_selection") == "required_when_domain_matches" and not knowledge:
        unresolved.append("knowledge_selection")
        missing_observations.append("knowledge_selection")
    if route.get("mcp_selection") == "required" and not (tool_schema_refs or []):
        unresolved.append("mcp_selection")
        missing_observations.append("mcp_selection")
    selected_tool_refs: list[str] = []
    for logical in tool_schema_refs or []:
        path = resolver.resolve_for_read(logical, root)
        if not path.is_file():
            unresolved.append(f"tool_schema:{logical}")
            missing_observations.append(f"tool_schema:{logical}")
        else:
            selected_tool_refs.append(path.relative_to(root).as_posix())
    local_refs: list[dict[str, Any]] = [*policy_refs, pack, skill, task, *required_context, *conditional_context, *context_includes, *knowledge]
    if prompt_ref is not None:
        local_refs.append(prompt_ref)
    expansion_hops = int((pack_document.get("limits") or {}).get("context_expansion_hops", 0) or 0)
    budget_report = budget.evaluate(route_id, [int(item["selected_utf8_bytes"]) for item in local_refs], missing_observations=missing_observations, external_fetches=len(external_references), context_includes=len(context_includes), expansion_hops=expansion_hops, root=root)
    if budget_report["decision"] == "blocked":
        raise ValueError(f"Context budget blocked materialization for {route_id}")
    source_revisions = [{"ref": item["resolved_path"], "revision": item["revision"]} for item in local_refs]
    state_payload = {"route_id": route_id, "resolved_bindings": bindings, "unresolved_bindings": sorted(set(unresolved)), "active_conditions": sorted(conditions), "external_references": external_references, "memory_projection_refs": sorted(set(memory_projection_refs or [])), "tool_schema_refs": sorted(set(selected_tool_refs))}
    hash_lines = [f'{x["ref"]}:{x["revision"]}' for x in sorted(source_revisions, key=lambda x: x["ref"])]
    hash_lines.append(yaml.safe_dump(state_payload, sort_keys=True, allow_unicode=True))
    context_hash = f"sha256:{hashlib.sha256(chr(10).join(hash_lines).encode()).hexdigest()}"
    context_id = f"ctx-{context_hash.split(':', 1)[1][:16]}"
    return {"schema_version": "1.0", "context_id": context_id, "run_id": run_id, "route_id": route_id, "prompt_spec_ref": prompt_spec_ref, "selected_refs": {"policy": policy_refs, "prompt_spec": prompt_ref, "context_pack": pack, "primary_skill": skill, "task_contract": task, "required_context": required_context, "conditional_context": conditional_context, "context_includes": context_includes, "external_references": external_references, "knowledge": knowledge, "memory_projections": sorted(set(memory_projection_refs or [])), "tool_schema_refs": sorted(set(selected_tool_refs))}, "resolved_bindings": bindings, "unresolved_bindings": sorted(set(unresolved)), "active_conditions": sorted(conditions), "budget_report": budget_report, "context_fingerprint": {"schema_version": "1.0", "algorithm": "sha256", "value": context_hash, "selected_source_revisions": sorted(source_revisions, key=lambda x: x["ref"])}, "definition_fingerprint": {"schema_version": "1.0", "architecture_version": "v3.1", "policy_revision": _policy_revision(policy_refs), "prompt_revision": prompt_revision, "context_revision": context_hash, "graph_revision": "orchestration-phase4-canonical", "runtime_profile_revision": "runtime-phase3-canonical", "tool_schema_revision": "unbound-runtime", "checkpoint_schema_revision": "1.1", "evidence_schema_revision": "1.1", "eval_contract_revision": "eval-phase6-canonical"}}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--route", required=True)
    parser.add_argument("--prompt-spec-ref")
    parser.add_argument("--binding", action="append", default=[], help="name=value")
    parser.add_argument("--condition", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    bindings: dict[str, str] = {}
    for raw in args.binding:
        if "=" not in raw:
            raise SystemExit(f"invalid --binding (expected name=value): {raw}")
        name, value = raw.split("=", 1)
        bindings[name] = value
    view = materialize_context(args.run_id, args.route, args.prompt_spec_ref, bindings=bindings, active_conditions=set(args.condition))
    text = yaml.safe_dump(view, sort_keys=False, allow_unicode=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
