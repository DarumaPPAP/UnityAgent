"""Execution trace projection adapter."""

from graph_builder import AgentGraph, GraphNode


def project_execution(manifests):
    nodes = []
    edges = []
    for manifest in manifests:
        task_id = manifest.get("task", {}).get("id", "task")
        attempt_id = manifest.get("execution", {}).get("attempt", "attempt")
        nodes.extend([
            {"id": task_id, "type": "task", "label": task_id},
            {"id": attempt_id, "type": "attempt", "label": attempt_id},
        ])
        edges.append({"source": task_id, "target": attempt_id, "relation": "produces_attempt"})
        for evidence in manifest.get("execution", {}).get("evidence", []):
            evidence_id = evidence.get("id", "evidence")
            nodes.append({"id": evidence_id, "type": "evidence", "label": evidence_id})
            edges.append({"source": attempt_id, "target": evidence_id, "relation": "produces_evidence"})
    return nodes, edges


def build_execution_graph(source):
    graph = AgentGraph(view="execution")
    items = source if isinstance(source, list) else source.get("manifests", [])
    for item in items:
        task_id = item.get("task", {}).get("id", "task")
        graph.add_node(GraphNode(id=f"task:{task_id}", type="task", label=task_id))
    return graph
