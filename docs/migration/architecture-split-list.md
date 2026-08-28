# Architecture v3.1 SPLIT List

Status: Phase 0. These files/modules must not be moved intact because their current behavior crosses canonical authority boundaries.

| source | split destination | reason | cutover test |
|---|---|---|---|
| `UnityAgent/.ai/harness/mcp-activation.yaml` | Policy/Security + Runtime/Dispatcher + Runtime/Permissions | policy/permission requirements and actual tool exposure are mixed | tool-exposure contract + approval/permission integration |
| `UnityAgent/.ai/harness/task-contracts/*` | Policy clauses + Orchestration routing/gate refs + Runtime Mutation/Verification | catch-all task contract currently spans rule, decision and enforcement | route boundary pairs + mutation/gate contract tests |
| `UnityAgent/.ai/execution-profiles.yaml` | Orchestration routing + Runtime execution profile/control | semantic mode/profile selection and hard execution behavior must differ | semantic route != hard retry/timeout tests |
| `UnityAgent/.ai/context-index.yaml` | Context Selection + Orchestration Routing | current-call selection and next-action routing are different authorities | deterministic routing/context selection tests |
| `UnityAgent/.ai/knowledge/*` | Context/Retrieval/Knowledge + Persistence/Memory/Knowledge only for learned durable records | authored context source != mutable long-term memory truth | provenance + no durable write from Context |
| `UnityAgent/.ai/eval/failure-taxonomy.yaml` | Runtime typed failure emission + Eval Attribution | observed Runtime failure and Agent-quality attribution are different | denominator/failure attribution replay |
| `UnityAgent/Tools/ContextManifest/context_manifest_runtime.py` | Context/Assembly + Orchestration/Routing + Runtime/Verification | loads/builds Context but also projects route, mutation and gate/execution status | split unit tests + end-to-end manifest replay |
| `UnityAgent/Tools/ContextManifest/record_manifest_evidence.py` | Runtime/EvidenceCapture + Persistence/Evidence | capture and durable truth must be separate | append/provenance round-trip |
| `UnityAgent/Tools/GraphObservatory/*` | Orchestration graph builder + Context/Runtime/Eval projections + Operations dashboard | read model mixes multiple projections and UI | projection fidelity per owner |
| `UnityAgent/Tools/BehaviorEval/*` | Eval/Behavior + Graders + Attribution + ProductionSmoke | normalization/grading/smoke validation are currently bundled | historical artifact replay |
| `UnityAgent/Tools/GoldenEval/*` | Eval/GoldenContracts + Graders + Regression | dataset/contract/grading/regression concerns are bundled | Golden regression suite |
| `UnityAgent/Tools/ContractValidator/*` | each owning module Validators | root catch-all validator hides contract owner | validator parity + forbidden-dependency check |
| `UnityAgent/Tests/GoldenTasks/*` | Eval/Datasets + GoldenContracts + Tests | fixtures/contracts/tests require separate ownership but remain Eval-only | exact suite parity |
| `UnityAgent/Tests/BehaviorEval/*` | Eval/Behavior + ProductionSmoke + Tests | protocol fixtures and smoke cases are bundled | artifact replay + controlled smoke |
| `Graph/Tools/ContinuationController/continuation_controller.py` | Orchestration/Graph/LocalLoops+Routing + Runtime/ExecutionControl + Persistence/State | semantic TODO selection is mixed with health/human gate handling, lease, quota/budget and quota accounting | semantic retry vs runtime retry; state authority tests |
| `Graph/Tools/ExecutionOrchestrator/execution_orchestrator.py` | Orchestration/Orchestrator + Runtime/Dispatcher/Verification/ExecutionControl + Context/Retrieval/Memory + Persistence/State/Memory/Evidence | semantic coordination, process invocation, path/scope enforcement, Memory/Ix, evidence and state patches are mixed | cross-module integration + production artifact replay |
| `Graph/Tools/CodexProductionAgent/codex_production_agent*.py` | Runtime/Runner/Codex + Runtime/Verification/Mutation + typed failure/evidence contract consumed by Eval | model execution currently also loads task contracts, aggregates gates and assigns some failure classes | controlled production smoke + no Golden leak |
| `Graph/Tools/BehaviorEvalAdapter/behavior_eval_adapter*.py` | canonical Runtime contracts + Eval/Attribution, then adapter deletion | duplicate translation exists because execution/eval contracts differ | ARCH/NAMING/MUTATION/EVIDENCE parity before deletion |
| `Graph/Tools/BehaviorEvalAdapter/run_production_smoke.py` | Eval/ProductionSmoke case launcher + Runtime Runner call | case/grading ownership differs from actual execution | controlled smoke |
| `Graph/Tools/IxAdapter/ix_adapter.py` | Context/Retrieval/Repository + Runtime/Dispatcher/ExecutionControl | retrieval semantics and subprocess/timeout execution are mixed | unavailable/timeout/low-confidence tests |
| `Graph/Tools/LayeredMemoryController/layered_memory_controller.py` | Persistence/Memory + Persistence/Evidence + Context/Retrieval/Memory + Runtime/EvidenceCapture/Permissions | durable Memory, raw Evidence, projection and enforcement coexist | evidence immutability, memory promotion, projection scope tests |
| `Graph/Tools/ExecutionPolicyValidator/*` | Policy/Validators + owning Runtime/Orchestration validators | legacy validator spans multiple authorities | validator parity |
| `Graph/policies/continuation-control.yaml` | Orchestration LocalLoops/Routing + Runtime/ExecutionControl | semantic continuation and execution limits are mixed | loop/retry boundary tests |
| `Graph/policies/execution-*.yaml`, `contract-routing.yaml`, `mode-escalation.yaml` | Orchestration definitions + referenced Policy constraints | declarative route topology must not redefine Policy enforcement | route/profile contract tests |
| `Graph/policies/evidence-admission.yaml` | Policy/Evidence + Runtime/Verification | evidence requirement != evidence enforcement | evidence sufficiency tests |
| `Graph/policies/memory-layering.yaml` | Persistence/Memory + referenced Policy clauses | lifecycle/promotion ownership differs from cross-cutting restrictions | promotion/retention tests |
| `Graph/policies/unity-editor-first-verification.yaml` | Policy/Evidence + Runtime/Harnesses/Unity/Verification | when verification is required != how Unity verification executes | Unity availability/evidence tests |
| `Graph/schemas/execution-*.yaml` | Runtime/Contracts + Orchestration/Graph/Contracts according to semantic field | root schema family contains both execution and orchestration concepts | schema compatibility tests |
| `Graph/schemas/continuation-state.schema.yaml`, `run-state.schema.json` | Persistence/Contracts + Orchestration/Graph/StateMapping | durable state truth and graph mapping must differ | resume/state scope tests |
| `Graph/schemas/evidence.schema.yaml`, `verification-evidence.schema.json` | Persistence EvidenceRecord + Runtime ExecutionEvidence | storage record and execution emission need explicit boundary | canonical evidence round-trip |
| `Graph/packages/.../UnityArtifactGraphScanner.cs` | Runtime/Harnesses/Unity/Editor + Context/Retrieval/Repository output contract | Unity `AssetDatabase` execution produces dependency context data; not control-plane Graph | Unity EditMode + context consumption |
| `Graph/packages/.../UnityArtifactGraphExporter.cs` | Runtime Unity Harness + Persistence artifact/evidence handoff | execution/export differs from durable artifact record | export/provenance tests |
| `Graph/packages/.../UnityArtifactImpactAnalyzer.cs` | Context/Retrieval/Repository contract + Runtime Unity invocation | analysis semantics differ from Unity execution mechanism | analyzer tests |

## Split rules

- First create new boundary contracts and tests; do not begin by deleting the old file.
- Move pure functions/definitions before stateful mutation/execution code when possible.
- Preserve legacy compatibility reads until the new path is proven, but make old paths read-only after canonical switch.
- A split is incomplete if two new modules both believe they own the same authoritative state or rule.
- Every split that changes Runtime/Eval boundaries requires production artifact replay, not only fake fixtures.
