"""Harness graph projection adapter."""

from graph_builder import AgentGraph, GraphNode


def project_harness(contracts):
    nodes = []
    edges = []
    for contract in contracts:
        contract_id = contract.get("id", "task-contract")
        nodes.append({"id": contract_id, "type": "task_contract", "label": contract_id})
        for gate in contract.get("required_gates", []):
            nodes.append({"id": gate, "type": "quality_gate", "label": gate})
            edges.append({"source": contract_id, "target": gate, "relation": "requires_gate"})
        for rule in contract.get("prohibited_mutations", []):
            nodes.append({"id": rule, "type": "mutation_rule", "label": rule})
            edges.append({"source": contract_id, "target": rule, "relation": "prohibits_mutation"})
    return nodes, edges


def build_harness_graph(source):
    graph = AgentGraph(view="harness")
    items = source if isinstance(source, list) else source.get("contracts", [])
    for item in items:
        contract_id = item.get("id", "task-contract")
        graph.add_node(GraphNode(id=f"task_contract:{contract_id}", type="task_contract", label=contract_id))
    return graph
