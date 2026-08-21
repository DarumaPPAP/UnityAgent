"""Validation helpers for Graph Observatory generated artifacts."""


def validate_graph(graph):
    errors = []

    node_ids = set()
    for node in graph.get("nodes", []):
        node_id = node.get("id")
        if not node_id:
            errors.append("node id is required")
        elif node_id in node_ids:
            errors.append(f"duplicate node id: {node_id}")
        else:
            node_ids.add(node_id)

    for edge in graph.get("edges", []):
        if edge.get("source") not in node_ids:
            errors.append("edge source does not exist")
        if edge.get("target") not in node_ids:
            errors.append("edge target does not exist")
        if not edge.get("relation"):
            errors.append("edge relation is required")

    return errors
