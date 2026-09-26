"""Output-contract based semantic validation for model reasoning artifacts."""
from __future__ import annotations

from typing import Any, Mapping

from Runtime.ReferenceImplementation.world_planning import verify_world_plan

VALIDATORS = {"Runtime/Contracts/world-plan-result.schema.json": verify_world_plan}


class ReasoningOutputContractError(ValueError):
    pass


def require_reasoning_output_contract(output_contract_ref: str) -> None:
    if output_contract_ref not in VALIDATORS:
        raise ReasoningOutputContractError(f"no semantic validator for reasoning output contract: {output_contract_ref}")


def verify_reasoning_artifact(output_contract_ref: str, manifest: Mapping[str, Any], artifact: Mapping[str, Any]) -> dict[str, Any]:
    require_reasoning_output_contract(output_contract_ref)
    return VALIDATORS[output_contract_ref](manifest, artifact, runtime_observed=True)
