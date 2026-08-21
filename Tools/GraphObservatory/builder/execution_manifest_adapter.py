"""Context Manifest -> Execution Graph adapter.

Graph output is derived data. Canonical manifests remain the source of truth.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ExecutionGraphData:
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)


def manifest_to_execution_graph(manifest: Dict[str, Any]) -> ExecutionGraphData:
    graph = ExecutionGraphData()

    task_id = manifest.get("task", {}).get("id", "task:unknown")
    attempt_id = manifest.get("execution", {}).get("attempt", "attempt:unknown")

    graph.nodes.append({"id": task_id, "type": "task"})
    graph.nodes.append({"id": attempt_id, "type": "attempt"})
    graph.edges.append({
        "source": task_id,
        "target": attempt_id,
        "relation": "produces_attempt"
    })

    for evidence in manifest.get("execution", {}).get("evidence", []):
        evidence_id = evidence.get("id", "evidence:unknown")
        graph.nodes.append({"id": evidence_id, "type": "evidence"})
        graph.edges.append({
            "source": attempt_id,
            "target": evidence_id,
            "relation": "produces_evidence"
        })

    return graph
