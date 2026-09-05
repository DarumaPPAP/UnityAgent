# UnityAgent Runtime Bootstrap Contract

UnityAgentのProduction実行、またはそのAuthority境界を変更するときに読む。
通常のRepository文書・Skill保守へ、Runtime起動や全Context読込を追加する手順ではない。
以下は既存Bootstrapの実行契約を移したもので、各Canonical Sourceが正本である。

## 2. Bootstrap sequence
1. `Policy/User/user-policy.yaml` を読み、Risk / Security / Approval / Evidence は `Policy/` を正本として適用する。
2. Task Fingerprintを構築し、`Orchestration/Routing/task-routes.yaml` でPrimary Routeとsemantic Execution Profileを一つ選ぶ。Technology keywordだけではRouteを決めない。
3. 選択Routeの `required_policy_clauses` をPolicy provenanceとして記録し、`Context/Selection/context-catalog.yaml` からContext Pack / Primary Skill / canonical Task Contractを解決する。
4. `Context/Assembly/materialize_context.py` で current-call `MaterializedContextView` を構築しContext Budgetを評価する。Memoryは `Context/Retrieval/Memory/` が `Persistence/Memory` からread-only projectionだけを取得する。
5. bounded Taskは `Policy -> Orchestration Route -> Context -> Runtime -> Verification -> Result` のFast Pathを優先し、semantic coordinationが必要な場合だけ `Orchestration/Definitions/development-parent-graph.yaml` を使う。
6. OrchestrationはRuntime handoffを作る。actual process/tool execution、hard timeout/cancellation、mutation scope、tool dispatch、health/verification/evidence captureは `Runtime/` が実行する。
7. OrchestrationはProvider製品名ではなくCapabilityを要求する。Contextは選択Capabilityの説明だけをmaterializeし、`Runtime/Tooling/tool_broker.py` がEnvironment Discovery / Provider Resolutionを経て `Runtime/Dispatcher/tool_runtime_dispatcher.py` からProduction dispatchする。CLI/MCP/Player ProviderはCapabilityごとのoptional候補でありsemantic authorityではない。
8. OrchestrationはPersistence-compatible state projectionだけを返し、Persistenceが ExecutionState / WorkflowState / LoopControlState をdurable truthとしてcommitする。
9. RuntimeのExecution Evidenceは `Persistence/Evidence` にappendされて初めてdurable Evidence truthになる。CheckpointはState snapshot refsでありMemory/Evidenceではない。
10. Resumeは `Persistence/Resume/` がDefinitionFingerprintを比較し、compatible / migration / replan / Human Reviewをfail-closedで決定する。
11. Evalは `Eval/Datasets/` / `Eval/GoldenContracts/` とRuntime/Persistence structured factsから測定し、`not_observed` をAgent品質denominatorから除外する。改善はnon-applying `ChangeProposal`のみ。
12. Operationsは `Runtime/Telemetry/` とEval structured factsを観測し、Detection / Incident / Runbookを生成する。controlはPolicy/Approval済みapproved commandだけを authority別control APIへ渡す。
13. `Context/Manifest/` は current-call Context provenanceであり、WorkflowState / Checkpoint / Evidence truth / Graph topologyの正本ではない。
14. legacy URI/path fallbackを使用しない。Canonical pathを直接解決し、unknown/removed referenceはfail-closedにする。

## 3. Canonical map
| Area | Canonical Source | Responsibility |
|---|---|---|
| User Policy | `Policy/User/user-policy.yaml` | ユーザー固有Policy |
| Risk / Security / Approval / Evidence | `Policy/` | Rule / Authority |
| Route / Graph / Task Contract | `Orchestration/Routing/` + `Orchestration/Definitions/` + `Orchestration/Contracts/TaskContracts/` | semantic route/topology/next action/task boundary |
| Local Loops / Gates / Parallel | `Orchestration/Graph/` | bounded semantic coordination |
| Orchestrator | `Orchestration/Orchestrator/` | Runtime handoff; no execution implementation |
| Prompt / Context / Retrieval | `Context/` | bounded current-call materialization |
| Runtime Contracts / Execution | `Runtime/Contracts/` + `Runtime/Runner/` + `Runtime/Dispatcher/` + `Runtime/Tooling/` + `Runtime/ExecutionControl/` | canonical execution facts / Tool Broker resolution / actual execution / hard limits |
| Runtime Guardrails / Harnesses | `Runtime/Sandbox/` + `Runtime/Guardrails/` + `Runtime/Permissions/` + `Runtime/Harnesses/` + `Runtime/Health/` | scope / permission / Unity/Test/Performance/SCM observation |
| Runtime Evidence / Telemetry | `Runtime/EvidenceCapture/` + `Runtime/Telemetry/` | current-run capture / telemetry production |
| Persistence | `Persistence/State/` + `Persistence/Checkpoint/` + `Persistence/Resume/` + `Persistence/Memory/` + `Persistence/Evidence/` + `Persistence/Session/` | durable State / Checkpoint / Memory / Evidence / Session |
| Operations Observability | `Operations/Observability/` + `Operations/Detection/` + `Operations/Incidents/` | backend/search/dashboard / detection / incident / runbook |
| Operations Runtime Control | `Operations/RuntimeControl/` + `Runtime/Control/` + `Orchestration/Control/` | external Policy/Approval-gated control |
| Operations ChangeManagement | `Operations/ChangeManagement/` | VersionManifest / rollout / rollback / config change |
| Eval | `Eval/Behavior/` + `Eval/Golden/` + `Eval/Datasets/` + `Eval/Attribution/` + `Eval/Replay/` + `Eval/ChangeProposals/` | grading / attribution / historical replay / proposals |
| Unity Tool Runtime | `Specs/UnityToolRuntime.md` + `Runtime/Tooling/` + `Runtime/Dispatcher/` | Capability / Provider / Transport分離とProduction Tool Broker execution |

## 4. Responsibility guards
- Policy defines; Context materializes; Orchestration decides; Runtime executes; Persistence remembers; Operations observes/controls; Eval measures/proposes.
- ContextはRoute authorityでもdurable Memory/Checkpoint/Evidence storeでもない。
- Local LoopはSubGraph内edge/cycleでありtop-level control planeではない。
- Orchestrationのsemantic continue/replanとRuntimeのhard retry/timeout/process killを混同しない。Orchestrationはdurable Stateを書かない。
- Orchestrationは`MyUnityMCPを使う`、`Unity CLIを使う`等のProvider製品選択をsemantic Goalとして固定しない。Taskが必要とするCapabilityを表現し、Provider / Transportの実行解決はRuntime側へ委譲する。
- RuntimeはAgent品質を採点せず、semantic Graph/TODO/replan authorityやdurable Evidence/Memory/Checkpoint truthを持たない。
- RuntimeがProviderを変更する場合もPolicy / Approval / Mutation Scope / Evidence Contractを維持する。Provider unavailableを理由にSafety Contractを下げるsilent semantic fallbackを行わない。
- MyUnityMCPの承認付きMutationが必要なTaskを、接続失敗だけを理由にraw `eval`やgeneric mutationへ迂回しない。
- `Checkpoint != Memory != Evidence`。Checkpoint restoreはStateだけを復元しMemory/Evidenceを巻き戻さない。
- Runtime Evidence captureはPersistence append後にのみhistorical Evidenceとなり、EvidenceはResume都合で書き換えない。
- Operations observability recordはPersistence Evidence/ExecutionStateの代替truthではない。
- `Operations/RuntimeControl` は外部運用control、`Runtime/ExecutionControl` はhard execution safetyであり別責務。
- Operationsはraw control requestをdispatchせず、Policy decision + Approval decision済みapproved commandだけを明示control APIへ渡す。Policyのrisk/approval判断を上書きしない。
- checkpoint replayは `Persistence/Resume` decision ref無しで実行しない。Detection / Incident / Dashboard / SearchはRuntime/Evalを直接変更しない。
- EvalはRuntime/Codex/Unity/process executionを実装せず、structured factsをlossy text/diffから再構築しない。`not_observed`を品質denominatorへ入れず、production definitionを直接変更しない。
- Golden expected contentをProduction Prompt / Contextへ注入しない。Unknown Project Factや不足Bindingを推測で埋めない。
- `unavailable`を成功扱いしない。CompileだけでRuntime / Visual / Performance / Player / 実機を承認しない。
- RuntimeのUnity Artifact GraphはAsset dependency graphでありAgent ParentGraph/SubGraphではない。
- historical migration/Eval provenanceは `docs/migration/` と `Eval/Datasets/` / `Eval/Replay/` に監査用として残せるが、production authorityとして解決しない。

## 5. Cutover state
- actual execution=`Runtime/`、semantic Graph/Route/Task Contract=`Orchestration/`、durable truth=`Persistence/`、grading/replay=`Eval/`、observability/control/change management=`Operations/` がcanonical owner。
- Production Tool Runtimeは `Orchestration CapabilityRequest -> Runtime ToolBroker -> Provider Resolution -> Runtime Dispatcher -> structured ProviderResult -> Runtime Evidence` がcanonical path。
- legacy `.ai` authority、Context/Eval/Persistence compatibility layer、old Eval shims、old LoopIntegration control plane、旧MCP Context selectionをproduction bootstrapへ戻さない。
- `DarumaPPAP/Unity-Graph-Engineering` はUnityAgent production execution dependencyではない。過去migration provenanceのみ保持できる。
- `DarumaPPAP/MyUnityMCP` はMCP manifest / tool schema / package implementationの外部owner。UnityAgentのPolicy / Orchestration authorityではない。
- Unity公式CLI / `com.unity.pipeline` はProject / Editor / Build / Test / Player transportの外部Provider候補であり、UnityAgentのsemantic authorityではない。

## 6. User-specific entrypoints
- Comments: `Policy/User/user-policy.yaml#comment_system`
- C# / Formatting: `.agents/skills/` + `SkillReferences/CODING_STANDARDS.md`
- Architecture / ECS: `.agents/skills/unity-architecture-design/` + 対応 `SkillReferences/`
- Rendering / Shader: `.agents/skills/unity-rendering/` + Context Pack / Knowledge
- Runtime / Performance: `.agents/skills/unity-runtime-evidence/`
- Route / Graph: `Orchestration/Routing/task-routes.yaml` + `Orchestration/Definitions/development-parent-graph.yaml`
- Context Budget / Prompt: `Context/Budget/context-budget.yaml` + `Context/Prompt/Templates/`
- Runtime Execution: `Runtime/Runner/` + `Runtime/Tooling/` + `Runtime/Dispatcher/` + `Runtime/Harnesses/`
- Unity Tool Runtime: `Specs/UnityToolRuntime.md`
- Local Unity Project usage: `docs/local-project-development.md` + `Templates/DevelopmentRequest.md`
- Persistence: `Persistence/persistence-layout.yaml` + `Persistence/State/` + `Persistence/Checkpoint/` + `Persistence/Resume/` + `Persistence/Memory/` + `Persistence/Evidence/`
- Operations: `Operations/Observability/` + `Operations/Detection/` + `Operations/Incidents/` + `Operations/RuntimeControl/` + `Operations/ChangeManagement/`
- Eval: `Eval/Golden/` + `Eval/Behavior/` + `Eval/Datasets/` + `Eval/Attribution/` + `Eval/Replay/`

## 7. Completion handoff
Orchestration→Runtime: Policy revision / Route / Context ID/Fingerprint / Execution Profile / runtime projection / mutation scope / validation requirements / requested Capability。Runtime→Persistence: ExecutionResult / RuntimeFailure / MutationEvidence / captured Evidence / Telemetryのうちdurable truth。Evalはstructured factsとGoldenContract/Datasetからmeasurement / attribution / regression report / ChangeProposalを生成する。Operationsはtelemetryを観測してDetection / Incident / Runbookを生成し、必要な運用actionだけをPolicy/Approval済みapproved commandとしてcontrol APIへ渡す。rollout/rollbackはVersionManifest付きChangeManagementで管理する。

## 8. Anti-regression
- `AGENTS.md`へ詳細規約本文を戻さない。Policy canonical sourceを旧Sourceで上書きしない。
- ContextからRoute/Graph/Retry authorityやdurable storeを新設しない。
- Orchestrationからsubprocess/Unity/tool execution、hard Runtime enforcement、durable State storeを実装しない。
- Orchestration Graphへ特定Provider / Transport製品名を恒久的なsemantic authorityとして埋め込まない。
- Runtimeからsemantic Graph/TODO/replan authority、durable Evidence/Memory/Checkpoint truth、Agent quality gradingを新設しない。
- Provider fallbackでApproval / Revision / Exact Diff / Mutation Scope等のSafety Contractを弱めない。
- PersistenceからRoute/semantic decision/Runtime execution/Eval grading authorityを新設しない。
- Operationsから`Runtime/ExecutionControl`内部control、Policy/Approval bypass、Detection/Incident/Runbook直結production mutationを実装しない。
- EvalからRuntime/process/tool/Unity executionやproduction definition変更を実装しない。
- `not_observed`をAgent品質regressionとして数えず、Runtime structured factsをdiff/text parserで再構築しない。
- Checkpoint/Memory/Evidenceを同じrecordとして扱わず、Resume migrationでoriginal checkpoint/evidenceを上書きしない。
- legacy fallback/shim/旧MCP Context selectionを復活させず、Golden expectationをPromptへ混入させない。
- Production Tool Brokerを迂回するProvider direct dispatchを新設しない。Capability RequestへProvider identityを逆流させない。