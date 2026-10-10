# Architecture v3.1 SPLIT List

Status: Phase 0. These files/modules must not be moved intact because their current behavior crosses canonical authority boundaries.

| source | split destination | reason | cutover test |
|---|---|---|---|
| `UnityAgent/.ai/harness/mcp-activation.yaml` | src/unityagent/policy/security + src/unityagent/runtime/dispatcher + src/unityagent/runtime/permissions | policy/permission requirements and actual tool exposure are mixed | tool-exposure contract + approval/permission integration |
| `UnityAgent/.ai/harness/task-contracts/*` | Policy clauses + Orchestration routing/gate refs + Runtime Mutation/Verification | catch-all task contract currently spans rule, decision and enforcement | route boundary pairs + mutation/gate contract tests |
| `UnityAgent/.ai/execution-profiles.yaml` | Orchestration routing + Runtime execution profile/control | semantic mode/profile selection and hard execution behavior must differ | semantic route != hard retry/timeout tests |
| `UnityAgent/.ai/context-index.yaml` | Context Selection + Orchestration Routing | current-call selection and next-action routing are different authorities | deterministic routing/context selection tests |
| `UnityAgent/.ai/knowledge/*` | src/unityagent/context/retrieval/knowledge + src/unityagent/persistence/memory/knowledge only for learned durable records | authored context source != mutable long-term memory truth | provenance + no durable write from unityagent.context |
| `UnityAgent/.ai/eval/failure-taxonomy.yaml` | Runtime typed failure emission + eval Attribution | observed Runtime failure and Agent-quality attribution are different | denominator/failure attribution replay |
| `UnityAgent/Tools/ContextManifest/context_manifest_runtime.py` | src/unityagent/context/assembly + src/unityagent/orchestration/routing + src/unityagent/runtime/verification | loads/builds Context but also projects route, mutation and gate/execution status | split unit tests + end-to-end manifest replay |
| `UnityAgent/Tools/ContextManifest/record_manifest_evidence.py` | src/unityagent/runtime/evidence_capture + src/unityagent/persistence/evidence | capture and durable truth must be separate | append/provenance round-trip |
| `UnityAgent/Tools/GraphObservatory/*` | Orchestration graph builder + src/unityagent/context/runtime/eval projections + Operations dashboard | read model mixes multiple projections and UI | projection fidelity per owner |
| `UnityAgent/Tools/BehaviorEval/*` | eval/behavior + Graders + Attribution + ProductionSmoke | normalization/grading/smoke validation are currently bundled | historical artifact replay |
| `UnityAgent/Tools/GoldenEval/*` | eval/golden_contracts + Graders + Regression | dataset/contract/grading/regression concerns are bundled | Golden regression suite |
| `UnityAgent/Tools/ContractValidator/*` | each owning module Validators | root catch-all validator hides contract owner | validator parity + forbidden-dependency check |
| `UnityAgent/Tests/GoldenTasks/*` | eval/datasets + GoldenContracts + tests | fixtures/contracts/tests require separate ownership but remain Eval-only | exact suite parity |
| `UnityAgent/Tests/BehaviorEval/*` | eval/behavior + ProductionSmoke + tests | protocol fixtures and smoke cases are bundled | artifact replay + controlled smoke |
| `Graph/Tools/ContinuationController/continuation_controller.py` | src/unityagent/orchestration/graph/local_loops+Routing + src/unityagent/runtime/execution_control + src/unityagent/persistence/state | semantic TODO selection is mixed with health/human gate handling, lease, quota/budget and quota accounting | semantic retry vs runtime retry; state authority tests |
| `Graph/Tools/ExecutionOrchestrator/execution_orchestrator.py` | src/unityagent/orchestration/orchestrator + src/unityagent/runtime/dispatcher/verification/execution_control + src/unityagent/context/retrieval/memory + src/unityagent/persistence/state/memory/evidence | semantic coordination, process invocation, path/scope enforcement, Memory/Ix, evidence and state patches are mixed | cross-module integration + production artifact replay |
| `Graph/Tools/CodexProductionAgent/codex_production_agent*.py` | src/unityagent/runtime/runner/codex + src/unityagent/runtime/verification/mutation + typed failure/evidence contract consumed by eval | model execution currently also loads task contracts, aggregates gates and assigns some failure classes | controlled production smoke + no Golden leak |
| `Graph/Tools/BehaviorEvalAdapter/behavior_eval_adapter*.py` | canonical Runtime contracts + eval/attribution, then adapter deletion | duplicate translation exists because execution/eval contracts differ | ARCH/NAMING/MUTATION/EVIDENCE parity before deletion |
| `Graph/Tools/BehaviorEvalAdapter/run_production_smoke.py` | eval/production_smoke case launcher + Runtime Runner call | case/grading ownership differs from actual execution | controlled smoke |
| `Graph/Tools/IxAdapter/ix_adapter.py` | src/unityagent/context/retrieval/repository + src/unityagent/runtime/dispatcher/execution_control | retrieval semantics and subprocess/timeout execution are mixed | unavailable/timeout/low-confidence tests |
| `Graph/Tools/LayeredMemoryController/layered_memory_controller.py` | src/unityagent/persistence/memory + src/unityagent/persistence/evidence + src/unityagent/context/retrieval/memory + src/unityagent/runtime/evidence_capture/permissions | durable Memory, raw Evidence, projection and enforcement coexist | evidence immutability, memory promotion, projection scope tests |
| `Graph/Tools/ExecutionPolicyValidator/*` | src/unityagent/policy/validators + owning src/unityagent/runtime/orchestration validators | legacy validator spans multiple authorities | validator parity |
| `Graph/policies/continuation-control.yaml` | Orchestration LocalLoops/Routing + src/unityagent/runtime/execution_control | semantic continuation and execution limits are mixed | loop/retry boundary tests |
| `Graph/policies/execution-*.yaml`, `contract-routing.yaml`, `mode-escalation.yaml` | Orchestration definitions + referenced Policy constraints | declarative route topology must not redefine Policy enforcement | route/profile contract tests |
| `Graph/policies/evidence-admission.yaml` | src/unityagent/policy/evidence + src/unityagent/runtime/verification | evidence requirement != evidence enforcement | evidence sufficiency tests |
| `Graph/policies/memory-layering.yaml` | src/unityagent/persistence/memory + referenced Policy clauses | lifecycle/promotion ownership differs from cross-cutting restrictions | promotion/retention tests |
| `Graph/policies/unity-editor-first-verification.yaml` | src/unityagent/policy/evidence + src/unityagent/runtime/harnesses/unity/verification | when verification is required != how Unity verification executes | Unity availability/evidence tests |
| `Graph/schemas/execution-*.yaml` | src/unityagent/runtime/contracts + src/unityagent/orchestration/graph/contracts according to semantic field | root schema family contains both execution and orchestration concepts | schema compatibility tests |
| `Graph/schemas/continuation-state.schema.yaml`, `run-state.schema.json` | src/unityagent/persistence/contracts + src/unityagent/orchestration/graph/state_mapping | durable state truth and graph mapping must differ | resume/state scope tests |
| `Graph/schemas/evidence.schema.yaml`, `verification-evidence.schema.json` | Persistence EvidenceRecord + Runtime ExecutionEvidence | storage record and execution emission need explicit boundary | canonical evidence round-trip |
| `Graph/packages/.../UnityArtifactGraphScanner.cs` | src/unityagent/runtime/harnesses/unity/editor + src/unityagent/context/retrieval/repository output contract | Unity `AssetDatabase` execution produces dependency context data; not control-plane Graph | Unity EditMode + context consumption |
| `Graph/packages/.../UnityArtifactGraphExporter.cs` | Runtime Unity Harness + Persistence artifact/evidence handoff | execution/export differs from durable artifact record | export/provenance tests |
| `Graph/packages/.../UnityArtifactImpactAnalyzer.cs` | src/unityagent/context/retrieval/repository contract + Runtime Unity invocation | analysis semantics differ from Unity execution mechanism | analyzer tests |

## Split rules

- First create new boundary contracts and tests; do not begin by deleting the old file.
- Move pure functions/definitions before stateful mutation/execution code when possible.
- Preserve legacy compatibility reads until the new path is proven, but make old paths read-only after canonical switch.
- A split is incomplete if two new modules both believe they own the same authoritative state or rule.
- Every split that changes src/unityagent/runtime/eval boundaries requires production artifact replay, not only fake fixtures.
