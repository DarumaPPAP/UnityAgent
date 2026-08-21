"""Golden regression projection adapter."""

from graph_builder import AgentGraph, GraphNode


def project_regression(tasks):
    nodes = []
    edges = []
    for task in tasks:
        task_id = task.get("id", "golden-task")
        grader = task.get("grader", "deterministic-grader")
        nodes.append({"id": task_id, "type": "golden_task", "label": task_id})
        nodes.append({"id": grader, "type": "grader", "label": grader})
        edges.append({"source": task_id, "target": grader, "relation": "evaluated_by"})
    return nodes, edges


def build_regression_graph(source):
    graph = AgentGraph(view="regression")
    items = source if isinstance(source, list) else source.get("tasks", [])
    for item in items:
        task_id = item.get("id", "golden-task")
        graph.add_node(GraphNode(id=f"golden_task:{task_id}", type="golden_task", label=task_id))
    return graph
