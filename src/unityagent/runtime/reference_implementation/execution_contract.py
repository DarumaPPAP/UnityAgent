"""Production Profile v3 の実行方式と観測・Context境界を検証する。"""
from __future__ import annotations

import re
from typing import Any, Mapping


CAPABILITY = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


def validate_execution_contract(value: Any, capabilities: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("execution must be an object")
    execution = dict(value)
    if execution == {"kind": "provider_backed"}:
        # Providerの選択と適格性は既存Runtime契約が所有する。
        return execution
    required = {"kind", "reasoning_runtime", "execution_mode", "instructions_ref", "output_contract_ref", "source_context_binding", "required_observation_capabilities", "hub_contract_refs"}
    if set(execution) != required or execution.get("kind") != "reasoning":
        raise ValueError("execution fields do not match a supported production contract")
    if execution["reasoning_runtime"] != "codex_runner" or execution["execution_mode"] not in {"planning_only", "read_only_analysis"} or execution["source_context_binding"] != "required":
        raise ValueError("reasoning execution requires bounded read-only CodexRuntime and Context binding")
    for name, pattern in (("instructions_ref", r"\.agents/skills/[a-z0-9-]+/SKILL\.md"), ("output_contract_ref", r"src/unityagent/runtime/contracts/[a-z0-9-]+\.schema\.json")):
        if not isinstance(execution[name], str) or re.fullmatch(pattern, execution[name]) is None:
            raise ValueError(f"invalid execution.{name}")
    observations = execution["required_observation_capabilities"]
    if not isinstance(observations, list) or any(not isinstance(item, str) or CAPABILITY.fullmatch(item) is None for item in observations) or len(set(observations)) != len(observations):
        raise ValueError("observation capabilities must be unique capability ids")
    if set(observations) & set(capabilities):
        raise ValueError("semantic reasoning capability cannot be dispatched as an observation tool")
    references = execution["hub_contract_refs"]
    if not isinstance(references, dict) or set(references) != {"instructions_ref", "output_contract_ref"} or any(not isinstance(item, str) or not item.startswith("SubAgents/") or ".." in item or "\\" in item for item in references.values()):
        raise ValueError("Hub instruction/output references must be explicit repository-relative contracts")
    return execution
