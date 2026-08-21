"""Harness graph projection adapter."""


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
