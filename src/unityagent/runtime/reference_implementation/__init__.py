"""UnityAgent generic SubAgent Reference Implementation (v1.1 wire compatibility)."""

from .authority import (
    ApprovalDecisionResolver,
    BudgetEnforcer,
    RuntimeBudgetLedger,
    SubAgentTaskPlanner,
    SurfaceGrantProjector,
    TaskContractIssuer,
)
from .contracts import (
    ApprovalDecision,
    CompletionProof,
    CompletionDecision,
    EvidenceRecord,
    ProviderResult,
    SurfaceGrant,
    TaskContract,
    TypedAction,
)
from .golden_task import GoldenTaskRunner, run_golden_task
from .runtime import (
    ActionReservationStore,
    CompletionCoordinator,
    CrossContractValidator,
    EvidenceCompletionGate,
    IdempotencyLedger,
    ProviderPostConditionVerifier,
    RuntimeDispatchGate,
)
from .profiles import (
    CATALOG,
    SubAgentDefinition,
    SubAgentProfile,
    SubAgentProfileCatalog,
    default_profile,
)

__all__ = [
    "ActionReservationStore", "ApprovalDecision", "ApprovalDecisionResolver", "BudgetEnforcer",
    "CompletionCoordinator", "CompletionDecision", "CompletionProof", "CrossContractValidator", "EvidenceCompletionGate",
    "EvidenceRecord", "GoldenTaskRunner", "IdempotencyLedger", "ProviderPostConditionVerifier",
    "ProviderResult", "RuntimeBudgetLedger", "RuntimeDispatchGate", "SubAgentTaskPlanner",
    "SurfaceGrant", "SurfaceGrantProjector", "TaskContract", "TaskContractIssuer", "TypedAction",
    "SubAgentDefinition", "SubAgentProfile", "SubAgentProfileCatalog", "CATALOG", "default_profile", "run_golden_task",
]
