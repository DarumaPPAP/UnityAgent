"""Generate Graph Observatory nodes from canonical readers."""

from graph_builder import AgentGraph, GraphNode


def add_node(graph: AgentGraph, node_id: str, node_type: str, label: str, **metadata) -> None:
    graph.add_node(GraphNode(id=node_id, type=node_type, label=label, metadata=metadata))


def build_architecture_graph(graph: AgentGraph, context: dict, harness: dict) -> None:
    add_node(graph, "unityagent-context-system", "context_system", "Context System")
    add_node(graph, "unityagent-harness-system", "harness_system", "Harness System")

    if context:
        add_node(
            graph,
            "context-pack-index",
            "context_pack",
            "Context Packs",
            source="context-index.yaml",
        )

    if harness:
        add_node(
            graph,
            "task-contract-index",
            "task_contract",
            "Task Contracts",
            source="harness",
        )


def build_regression_graph(graph: AgentGraph, golden_tasks: list[dict]) -> None:
    for task in golden_tasks:
        task_id = task.get("id", "unknown-golden-task")
        add_node(
            graph,
            task_id,
            "golden_task",
            task_id,
        )
