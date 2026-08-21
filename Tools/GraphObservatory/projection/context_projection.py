"""Context graph projection adapter.

Converts canonical context information into Graph Observatory nodes and edges.
Graph output is derived only; canonical files remain the source of truth.
"""


def project_context(context_items):
    nodes = []
    edges = []
    for item in context_items:
        context_id = item.get("id", "context")
        nodes.append({"id": context_id, "type": "context_pack", "label": context_id})
        for source in item.get("sources", []):
            source_id = source.get("id", source)
            nodes.append({"id": source_id, "type": "source", "label": source_id})
            edges.append({"source": context_id, "target": source_id, "relation": "reads_source"})
    return nodes, edges
