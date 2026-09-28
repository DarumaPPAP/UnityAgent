"""Output-contract based semantic validation for model reasoning artifacts."""
from __future__ import annotations

from typing import Any, Mapping

from Runtime.ReferenceImplementation.world_planning import WorldPlanContextError, WorldPlanContractError, verify_world_plan
from Runtime.ReferenceImplementation.analysis_reasoning import AnalysisContextError, AnalysisContractError, verify_graphics_analysis, verify_performance_analysis

VALIDATORS = {"Runtime/Contracts/world-plan-result.schema.json": verify_world_plan, "Runtime/Contracts/graphics-analysis-result.schema.json": verify_graphics_analysis, "Runtime/Contracts/performance-analysis-result.schema.json": verify_performance_analysis}


class ReasoningOutputError(ValueError):
    def __init__(self, message: str, *, failure_class: str = "runtime_protocol_failure") -> None:
        self.failure_class = failure_class
        super().__init__(message)


class ReasoningOutputContractError(ReasoningOutputError):
    pass


def require_reasoning_output_contract(output_contract_ref: str) -> None:
    if output_contract_ref not in VALIDATORS:
        raise ReasoningOutputContractError(f"no semantic validator for reasoning output contract: {output_contract_ref}")


def verify_reasoning_artifact(output_contract_ref: str, manifest: Mapping[str, Any], artifact: Mapping[str, Any]) -> dict[str, Any]:
    require_reasoning_output_contract(output_contract_ref)
    try:
        return VALIDATORS[output_contract_ref](manifest, artifact, runtime_observed=True)
    except (WorldPlanContextError, AnalysisContextError) as exc:
        raise ReasoningOutputError(str(exc), failure_class="context_binding_failed") from exc
    except WorldPlanContractError as exc:
        raise ReasoningOutputError(str(exc), failure_class="world_plan_contract_failed") from exc
    except AnalysisContractError as exc:
        raise ReasoningOutputError(str(exc)) from exc
