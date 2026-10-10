"""Project already-selected Task Contract into Runtime-enforceable fields only."""
from __future__ import annotations


def runtime_enforcement_from_task_contract(contract: dict) -> dict:
    if not isinstance(contract, dict) or not contract.get("id"):
        raise ValueError("selected task contract is required")
    return {"task_contract_id": str(contract["id"]), "default_execution_profile": contract.get("default_execution_profile"), "risk_level": contract.get("risk_level"), "allowed_mutations": list(contract.get("allowed_mutations", []) or []), "prohibited_mutations": list(contract.get("prohibited_mutations", []) or []), "mutation_channels": list(contract.get("mutation_channels", []) or []), "mutation_channel_binding": contract.get("mutation_channel_binding"), "required_quality_gates": list(contract.get("required_quality_gates", []) or []), "conditional_quality_gates": list(contract.get("conditional_quality_gates", []) or []), "stop_conditions": list(contract.get("stop_conditions", []) or [])}
