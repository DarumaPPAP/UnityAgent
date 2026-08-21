"""Context graph projection adapter.

Converts canonical context information into Graph Observatory nodes and edges.
Graph output is derived only; canonical files remain the source of truth.
"""

from graph_builder import AgentGraph, GraphEdge, GraphNode


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


def build_context_graph(source):
    graph = AgentGraph(view="context")
    items = source if isinstance(source, list) else source.get("contexts", [])
    for item in items:
        context_id = item.get("id", "context")
        graph.add_node(GraphNode(id=f"context:{context_id}", type="context", label=context_id))
    return graph
