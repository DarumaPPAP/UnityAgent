<!-- unityagent-bootstrap-map:v2 -->
# UnityAgent Bootstrap Map
> `bootstrap_map_only: true`
`AGENTS.md` は起動用の地図です。詳細規約を複製せず、各 Authority の Canonical Source へ委譲します。
## 1. Authority
1. 今回のユーザー明示指示
2. `Policy/User/user-policy.yaml`
3. 対象Project固有Policy
4. Unity Domain Standard
5. 外部Reference
6. 一般的Best Practice
ユーザー固有Policyを一般論で上書きしません。Policyの削除・簡略化は `Policy/User/user-policy.yaml` の保護契約に従います。
## 2. Bootstrap sequence
1. `Policy/User/user-policy.yaml` を読み、Risk / Security / Approval / Evidence は `Policy/` を正本として適用する。
2. Task Fingerprintを構築し、`Orchestration/Routing/task-routes.yaml` でPrimary Routeとsemantic Execution Profileを一つ選ぶ。Technology keywordだけではRouteを決めない。
3. 選択Routeの `required_policy_clauses` をPolicy provenanceとして記録し、`Context/Selection/context-catalog.yaml` からContext Pack / Primary Skill / Task Contractを解決する。
4. `Context/Assembly/materialize_context.py` で current-call `MaterializedContextView` を構築しContext Budgetを評価する。Memoryは `Context/Retrieval/Memory/` が `Persistence/Memory` からread-only projectionだけを取得する。
5. bounded Taskは `Policy -> Orchestration Route -> Context -> Runtime -> Verification -> Result` のFast Pathを優先し、semantic coordinationが必要な場合だけ `Orchestration/Definitions/development-parent-graph.yaml` を使う。
6. OrchestrationはRuntime handoffを作る。actual process/tool execution、hard timeout/cancellation、mutation scope、tool dispatch、health/verification/evidence captureは `Runtime/` が実行する。
7. MCPではContextがDescription/Manifestを選択し、Policyが許可条件を定義し、Runtimeが実Tool Groupを公開する。
8. OrchestrationはPersistence互換state projectionだけを返し、Persistenceが ExecutionState / WorkflowState / LoopControlState をdurable truthとしてcommitする。
9. RuntimeのExecution Evidenceは `Persistence/Evidence` にappendされて初めてdurable Evidence truthになる。CheckpointはState snapshot refsでありMemory/Evidenceではない。
10. Resumeは `Persistence/Resume/` がDefinitionFingerprintを比較し、compatible / migration / replan / Human Reviewをfail-closedで決定する。
11. Evalは `Eval/Datasets/` / `Eval/GoldenContracts/` とRuntime/Persistence structured factsから測定し、`not_observed` をAgent品質denominatorから除外する。改善はnon-applying `ChangeProposal`のみ。
12. Operationsは `Runtime/Telemetry/` とEval structured factsを観測し、Detection / Incident / Runbookを生成する。controlはPolicy/Approval済みapproved commandだけを authority別control APIへ渡す。
13. `Context/Manifest/` は current-call Context provenanceであり、WorkflowState / Checkpoint / Evidence truth / Graph topologyの正本ではない。
14. 旧Pathは `Context/Compatibility/legacy-path-map.yaml` のread-only resolver経由だけで参照し、新規writeは禁止する。
## 3. Canonical map
| Area | Canonical Source | Responsibility |
|---|---|---|
| User Policy | `Policy/User/user-policy.yaml` | ユーザー固有Policy |
| Risk / Security / Approval / Evidence | `Policy/` | Rule / Authority |
| Route / Graph | `Orchestration/Routing/` + `Orchestration/Definitions/` | semantic route/topology/next action |
| Local Loops / Gates / Parallel | `Orchestration/Graph/` | bounded semantic coordination |
| Orchestrator | `Orchestration/Orchestrator/` | Runtime handoff; no execution implementation |
| Prompt / Context / Retrieval | `Context/` | bounded current-call materialization |
| Runtime Contracts / Execution | `Runtime/Contracts/` + `Runtime/Runner/` + `Runtime/Dispatcher/` + `Runtime/ExecutionControl/` | canonical execution facts / actual execution / hard limits |
| Runtime Guardrails / Harnesses | `Runtime/Sandbox/` + `Runtime/Guardrails/` + `Runtime/Permissions/` + `Runtime/Harnesses/` + `Runtime/Health/` | scope / permission / Unity/Test/Performance/SCM observation |
| Runtime Evidence / Telemetry | `Runtime/EvidenceCapture/` + `Runtime/Telemetry/` | current-run capture / telemetry production |
| Persistence | `Persistence/State/` + `Persistence/Checkpoint/` + `Persistence/Resume/` + `Persistence/Memory/` + `Persistence/Evidence/` + `Persistence/Session/` | durable State / Checkpoint / Memory / Evidence / Session |
| Operations Observability | `Operations/Observability/` + `Operations/Detection/` + `Operations/Incidents/` | backend/search/dashboard / detection / incident / runbook |
| Operations Runtime Control | `Operations/RuntimeControl/` + `Runtime/Control/` + `Orchestration/Control/` | external Policy/Approval-gated control |
| Operations ChangeManagement | `Operations/ChangeManagement/` | VersionManifest / rollout / rollback / config change |
| Eval | `Eval/Behavior/` + `Eval/Golden/` + `Eval/Datasets/` + `Eval/Attribution/` + `Eval/Replay/` + `Eval/ChangeProposals/` | grading / attribution / replay / proposals |
## 4. Responsibility guards
- Policy defines; Context materializes; Orchestration decides; Runtime executes; Persistence remembers; Operations observes/controls; Eval measures/proposes.
- ContextはRoute authorityでもdurable Memory/Checkpoint/Evidence storeでもない。
- Local LoopはSubGraph内edge/cycleでありtop-level control planeではない。
- Orchestrationのsemantic continue/replanとRuntimeのhard retry/timeout/process killを混同しない。Orchestrationはdurable Stateを書かない。
- RuntimeはAgent品質を採点せず、semantic Graph/TODO/replan authorityやdurable Evidence/Memory/Checkpoint truthを持たない。
- `Checkpoint != Memory != Evidence`。Checkpoint restoreはStateだけを復元しMemory/Evidenceを巻き戻さない。
- Runtime Evidence captureはPersistence append後にのみhistorical Evidenceとなり、EvidenceはResume都合で書き換えない。
- Operations observability recordはPersistence Evidence/ExecutionStateの代替truthではない。
- `Operations/RuntimeControl` は外部運用control、`Runtime/ExecutionControl` はhard execution safetyであり別責務。
- Operationsはraw control requestをdispatchせず、Policy decision + Approval decision済みapproved commandだけを明示control APIへ渡す。Policyのrisk/approval判断を上書きしない。
- checkpoint replayは `Persistence/Resume` compatibility decision ref無しで実行しない。Detection / Incident / Dashboard / SearchはRuntime/Evalを直接変更しない。
- EvalはRuntime/Codex/Unity/process executionを実装せず、structured factsをlossy text/diffから再構築しない。`not_observed`を品質denominatorへ入れず、production definitionを直接変更しない。
- Golden expected contentをProduction Prompt / Contextへ注入しない。Unknown Project Factや不足Bindingを推測で埋めない。
- `unavailable`を成功扱いしない。CompileだけでRuntime / Visual / Performance / Player / 実機を承認しない。
- RuntimeのUnity Artifact GraphはAsset dependency graphでありAgent ParentGraph/SubGraphではない。
- Compatibilityはread-only。旧Sourceの削除はPhase 8の明示Human Gateまで行わない。
## 5. Current compatibility
- Phase 3以降 actual execution=`Runtime/`、Phase 4以降 semantic Graph/Route=`Orchestration/`、Phase 5以降 durable truth=`Persistence/`、Phase 6以降 grading/replay=`Eval/`、Phase 7以降 observability/control/change management=`Operations/` がcanonical owner。
- `Tools/BehaviorEval/` と `Tools/GoldenEval/` はPhase 8までEval compatibility shim。旧subprocess-capable runnerは `Eval/Compatibility/BehaviorEval/` の監査用reference。
- `DarumaPPAP/Unity-Graph-Engineering` の旧BehaviorEvalAdapter / State / Continuation / ExecutionOrchestrator / LayeredMemoryはPhase 8 Human Gateまで互換・監査用referenceで、canonical authorityではない。
- Legacy state/memory/evidence/eval artifactはexplicit compatibility loader/replay経由のみ。ambiguous mappingはfail closed。
- `DarumaPPAP/MyUnityMCP` はMCP manifest / tool schema / package implementationの外部owner。
## 6. User-specific entrypoints
- Comments: `Policy/User/user-policy.yaml#comment_system`
- C# / Formatting: `.agents/skills/` + `SkillReferences/CODING_STANDARDS.md`
- Architecture / ECS: `.agents/skills/unity-architecture-design/` + 対応 `SkillReferences/`
- Rendering / Shader: `.agents/skills/unity-rendering/` + Context Pack / Knowledge
- Runtime / Performance: `.agents/skills/unity-runtime-evidence/`
- Route / Graph: `Orchestration/Routing/task-routes.yaml` + `Orchestration/Definitions/development-parent-graph.yaml`
- Context Budget / Prompt: `Context/Budget/context-budget.yaml` + `Context/Prompt/Templates/`
- Runtime Execution: `Runtime/Runner/` + `Runtime/Harnesses/`
- Persistence: `Persistence/persistence-layout.yaml` + `Persistence/State/` + `Persistence/Checkpoint/` + `Persistence/Resume/` + `Persistence/Memory/` + `Persistence/Evidence/`
- Operations: `Operations/Observability/` + `Operations/Detection/` + `Operations/Incidents/` + `Operations/RuntimeControl/` + `Operations/ChangeManagement/`
- Eval: `Eval/Golden/` + `Eval/Behavior/` + `Eval/Datasets/` + `Eval/Attribution/` + `Eval/Replay/`
## 7. Completion handoff
Orchestration→Runtime: Policy revision / Route / Context ID/Fingerprint / Execution Profile / runtime projection / mutation scope / validation requirements。Runtime→Persistence: ExecutionResult / RuntimeFailure / MutationEvidence / captured Evidence / Telemetryのうちdurable truth。Evalはstructured factsとGoldenContract/Datasetからmeasurement / attribution / regression report / ChangeProposalを生成する。Operationsはtelemetryを観測してDetection / Incident / Runbookを生成し、必要な運用actionだけをPolicy/Approval済みapproved commandとしてcontrol APIへ渡す。rollout/rollbackはVersionManifest付きChangeManagementで管理する。
## 8. Anti-regression
- `AGENTS.md`へ詳細規約本文を戻さない。Policy canonical sourceを互換Sourceで上書きしない。
- ContextからRoute/Graph/Retry authorityやdurable storeを新設しない。
- Orchestrationからsubprocess/Unity/tool execution、hard Runtime enforcement、durable State storeを実装しない。
- Runtimeからsemantic Graph/TODO/replan authority、durable Evidence/Memory/Checkpoint truth、Agent quality gradingを新設しない。
- PersistenceからRoute/semantic decision/Runtime execution/Eval grading authorityを新設しない。
- Operationsから`Runtime/ExecutionControl`内部control、Policy/Approval bypass、Detection/Incident/Runbook直結production mutationを実装しない。
- EvalからRuntime/process/tool/Unity executionやproduction definition変更を実装しない。
- `not_observed`をAgent品質regressionとして数えず、Runtime structured factsをdiff/text parserで再構築しない。
- Checkpoint/Memory/Evidenceを同じrecordとして扱わず、Resume migrationでoriginal checkpoint/evidenceを上書きしない。
- 新しい旧Path直参照/writeを追加せず、Golden expectationをPromptへ混入させない。
