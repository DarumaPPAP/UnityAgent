"""Golden regression projection adapter."""


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
