"""Semantic orchestration for one graph transition. It never launches tools or writes durable state."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml

from Orchestration.Graph.state_mapping import workflow_state_patch

RUNTIME_NODE_KINDS = {"runtime_action", "health_check", "verification"}
DESIGN_REVIEW_REQUIREMENTS = {"required", "conditional", "not_required"}


def load_graph(path: Path) -> dict[str, Any]:
    graph = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if graph.get("parent_graph_id") != "development":
        raise ValueError("unsupported ParentGraph")
    return graph


def _node_index(graph: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    output: dict[str, tuple[str, dict[str, Any]]] = {}
    for subgraph in graph.get("subgraphs") or []:
        for node in subgraph.get("nodes") or []:
            node_id = str(node["id"])
            if node_id in output:
                raise ValueError(f"duplicate node id: {node_id}")
            output[node_id] = (str(subgraph["id"]), node)
    return output


def next_node(graph: dict[str, Any], current_node_id: str, signal: str) -> tuple[str, str, dict[str, Any]]:
    matches = [edge for edge in (graph.get("edges") or []) if edge.get("from") == current_node_id and edge.get("on") == signal]
    if len(matches) != 1:
        raise ValueError(f"expected one edge from {current_node_id} on {signal}, got {len(matches)}")
    target_id = str(matches[0]["to"])
    index = _node_index(graph)
    if target_id not in index:
        raise ValueError(f"edge target is unknown: {target_id}")
    subgraph_id, node = index[target_id]
    return subgraph_id, target_id, node


def runtime_handoff(*, run_id: str, node_id: str, route_id: str, execution_profile: str, context_id: str, context_fingerprint: str, task_contract_runtime_projection: dict[str, Any], mutation_scope: dict[str, Any], validation_requirements: list[str]) -> dict[str, Any]:
    return {"run_id": run_id, "step_id": node_id, "action_id": f"{route_id}:{node_id}", "route_id": route_id, "execution_profile": execution_profile, "context_id": context_id, "context_fingerprint": context_fingerprint, "task_contract_runtime_projection": task_contract_runtime_projection, "mutation_scope": mutation_scope, "validation_requirements": validation_requirements}


def transition(*, graph: dict[str, Any], run_id: str, current_node_id: str, signal: str, route_id: str, execution_profile: str, context_id: str, context_fingerprint: str, task_contract_runtime_projection: dict[str, Any] | None = None, mutation_scope: dict[str, Any] | None = None, validation_requirements: list[str] | None = None) -> dict[str, Any]:
    subgraph_id, node_id, node = next_node(graph, current_node_id, signal)
    handoff = None
    decision = "continue"
    if node.get("kind") in RUNTIME_NODE_KINDS:
        decision = "run_runtime"
        handoff = runtime_handoff(run_id=run_id, node_id=node_id, route_id=route_id, execution_profile=execution_profile, context_id=context_id, context_fingerprint=context_fingerprint, task_contract_runtime_projection=task_contract_runtime_projection or {}, mutation_scope=mutation_scope or {}, validation_requirements=validation_requirements or [])
    elif node_id == "complete":
        decision = "complete"
    patch = workflow_state_patch(run_id=run_id, parent_graph_id=str(graph["parent_graph_id"]), active_subgraph_id=subgraph_id, active_node_id=node_id)
    return {"schema_version": "1.0", "decision": decision, "route_id": route_id, "subgraph_id": subgraph_id, "node_id": node_id, "reason": f"edge {current_node_id} --{signal}--> {node_id}", "runtime_handoff": handoff, "state_patch": patch}


def fast_path(*, run_id: str, route_id: str, execution_profile: str, context_id: str, context_fingerprint: str, simple_task: bool, requires_semantic_replan: bool, runtime_action_id: str, design_review_requirement: str = "not_required", task_contract_runtime_projection: dict[str, Any] | None = None, mutation_scope: dict[str, Any] | None = None, validation_requirements: list[str] | None = None) -> dict[str, Any] | None:
    if design_review_requirement not in DESIGN_REVIEW_REQUIREMENTS:
        raise ValueError("invalid design_review_requirement")
    if not simple_task or requires_semantic_replan or design_review_requirement != "not_required":
        return None
    handoff = runtime_handoff(run_id=run_id, node_id=runtime_action_id, route_id=route_id, execution_profile=execution_profile, context_id=context_id, context_fingerprint=context_fingerprint, task_contract_runtime_projection=task_contract_runtime_projection or {}, mutation_scope=mutation_scope or {}, validation_requirements=validation_requirements or [])
    return {"schema_version": "1.0", "decision": "fast_path", "route_id": route_id, "subgraph_id": None, "node_id": runtime_action_id, "reason": "simple bounded task does not require ParentGraph coordination", "runtime_handoff": handoff, "state_patch": {}}
