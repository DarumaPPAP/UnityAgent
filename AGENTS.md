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

1. `Policy/User/user-policy.yaml` を読む。
2. Policy Risk / Security / Approval / Evidence は `Policy/` を正本として適用する。
3. Task Fingerprintを構築し、`Orchestration/Routing/task-routes.yaml` でPrimary Routeとsemantic Execution Profileを一つ選ぶ。Technology keywordだけではRouteを決めない。
4. 選択Routeの `required_policy_clauses` は Policy provenance として記録し、Evidence / Eval から追跡可能にする。
5. `Context/Selection/context-catalog.yaml` から選択済み Route の Context Pack、Primary Skill、Task Contract参照を解決する。
6. `Context/Assembly/materialize_context.py` で current-call `MaterializedContextView` を構築し、Context Budgetを評価する。Memory利用時は `Context/Retrieval/Memory/` が `Persistence/Memory` からread-only projectionだけを取得する。
7. 単純でboundedなTaskは `Policy -> Orchestration Route -> Context -> Runtime -> Verification -> Result` のFast Pathを優先する。
8. semantic coordinationが必要なTaskだけ `Orchestration/Definitions/development-parent-graph.yaml` の ParentGraph/SubGraph/Node/Gate/LocalLoop を使う。
9. OrchestrationがRuntime handoffを作り、actual process/tool execution、hard timeout/cancellation、mutation scope、tool dispatch、health/verification/evidence capture は `Runtime/` が実行する。
10. MCP が必要な場合、Contextは必要Description/Manifestを選択し、Policyが許可条件を定義し、Runtimeが実Tool Groupを公開する。
11. Orchestrationは `Persistence/Contracts/WorkflowState` / `LoopControlState` 互換のstate projectionを返すが、durable writeは行わない。Persistenceが `Persistence/persistence-layout.yaml` に従って ExecutionState / WorkflowState / LoopControlState をdurable truthとしてcommitする。
12. RuntimeがcaptureしたExecution Evidenceは `Persistence/Evidence` にappendされて初めてdurable Evidence truthになる。Checkpointはcommitted Stateのimmutable snapshot refsを束ね、Memory/Evidenceそのものにはならない。
13. Resume時は `Persistence/Resume/` が保存済みDefinitionFingerprintと現在定義を比較し、compatible / migration / replan / Human Reviewをfail-closedで決定する。
14. Evalが必要な場合、`Eval/Datasets/` と `Eval/GoldenContracts/` を評価入力の正本とし、Runtime/Persistenceのstructured factsを `Eval/Behavior/` / `Eval/Attribution/` で測定する。`not_observed` infrastructure runはAgent品質denominatorから除外し、Evalは必要ならnon-applying `ChangeProposal`だけを生成する。
15. `Context/Manifest/` は current-call Context provenanceを記録し、WorkflowState / Checkpoint / Evidence truth / Graph topologyの正本にはしない。
16. 旧Pathを必要とする未移行機能は明示された Compatibility boundary 経由だけで参照する。新規writeは禁止する。

## 3. Canonical map

| Area | Canonical Source | Responsibility |
|---|---|---|
| User Policy | `Policy/User/user-policy.yaml` | ユーザー固有の正しさ、Preference、禁止事項 |
| Risk / Security / Approval / Evidence | `Policy/` | Rule / Authority |
| Route / Graph | `Orchestration/Routing/` + `Orchestration/Definitions/` | semantic route/topology/next action |
| Local Loops / Gates / Parallel | `Orchestration/Graph/` | bounded semantic coordination only |
| Orchestrator | `Orchestration/Orchestrator/` | Runtime handoff and graph transition; no execution implementation |
| Prompt / Context Packs / Retrieval | `Context/` | bounded current-call materialization |
| Runtime Contracts | `Runtime/Contracts/` | canonical execution facts |
| Runtime Execution | `Runtime/Runner/` + `Runtime/Dispatcher/` + `Runtime/ExecutionControl/` | actual process/tool execution and hard limits |
| Runtime Guardrails | `Runtime/Sandbox/` + `Runtime/Guardrails/` + `Runtime/Permissions/` | scope / permission enforcement |
| Runtime Harnesses | `Runtime/Harnesses/` + `Runtime/Health/` + `Runtime/Verification/` | Unity/Test/Performance/SCM/tool observation |
| Runtime Evidence / Telemetry | `Runtime/EvidenceCapture/` + `Runtime/Telemetry/` | current-run evidence capture and telemetry production |
| Persistence State | `Persistence/State/` + `Persistence/persistence-layout.yaml` | authoritative current Execution/Workflow/Loop state |
| Persistence Checkpoint / Resume | `Persistence/Checkpoint/` + `Persistence/Resume/` + `Persistence/Migrations/` | immutable state snapshots, integrity, version compatibility and resume |
| Persistence Memory | `Persistence/Memory/` | durable long-term Memory lifecycle and promotion gate |
| Persistence Evidence | `Persistence/Evidence/` | append/immutable-oriented Evidence truth |
| Persistence Session | `Persistence/Session/` | session-to-run/checkpoint durable association |
| Eval Behavior / Golden / Datasets | `Eval/Behavior/` + `Eval/Golden/` + `Eval/Datasets/` | Actual Behavior / Golden grading and regression data |
| Eval Attribution / Replay | `Eval/Attribution/` + `Eval/Replay/` | typed failure attribution, quality denominator, historical replay |
| Eval Change Proposals | `Eval/ChangeProposals/` | non-applying improvement proposals only |

## 4. Responsibility guards

- Policy defines; Context materializes; Orchestration decides; Runtime executes; Persistence remembers; Operations observes/controls; Eval measures/proposes.
- ContextはRoute decision authorityではない。Orchestrationが明示したRouteだけをmaterializeする。
- Local LoopはSubGraph内のedge/cycleであり、top-level control planeではない。
- Orchestrationのsemantic continue/replanとRuntimeのhard retry/timeout/process killを混同しない。
- Orchestrationはdurable State / Checkpoint / Memory / Evidenceを書き込まない。
- PersistenceはRouteを選ばず、Tool/Subprocess/Unityを実行せず、Agent品質をgradeしない。
- `Checkpoint != Memory != Evidence`。Checkpoint restoreはStateだけを復元し、Memory/Evidenceを巻き戻さない。
- Context Memory Projectionはmodel inputでありdurable Memory truthではない。
- Runtime Evidence captureはdurable truthではなく、Persistence Evidenceへのappend後にのみhistorical Evidenceとなる。
- Evidenceはhistorical factとしてimmutable-orientedに扱い、Resumeの都合で元record/payload/hash/provenanceを書き換えない。
- EvalはRuntime/Codex/Unity/process executionを実装しない。既に観測されたstructured factsを測定する。
- Evalはtyped failureをresponse/stderr proseから推測しない。`changed_paths`をdiffから再構築せずRuntimeのstructured factを保持する。
- Evalの`not_observed` infrastructure/evaluator/fixture/unavailable-evidence runをAgent品質denominatorへ入れない。
- EvalのGolden expected contentをProduction Prompt / Contextへ注入しない。
- Evalはproduction definitionを直接変更せず、`applies_change: false` のChangeProposalだけを出せる。
- Unknown Project Factや不足Bindingを推測で埋めない。
- `unavailable`を成功扱いしない。CompileだけでRuntime / Visual / Performance / Player / 実機を承認しない。
- RuntimeはAgent品質を採点しない。
- RuntimeのUnity Artifact GraphはAsset dependency graphであり、Agent ParentGraph/SubGraphではない。
- Compatibilityはread-only。旧Sourceの削除はPhase 8の明示Human Gateまで行わない。

## 5. Current compatibility

- Phase 3以降、actual executionはUnityAgent `Runtime/` がcanonical owner。
- Phase 4以降、Route / ParentGraph / SubGraph / Node / Gate / LocalLoop / semantic TODO selection / semantic replanはUnityAgent `Orchestration/` がcanonical owner。
- Phase 5以降、ExecutionState / WorkflowState / LoopControlState / RunCheckpoint / SessionRecord / MemoryRecord / EvidenceRecord のdurable truthはUnityAgent `Persistence/` がcanonical owner。
- Phase 6以降、Behavior Eval / Golden Eval / datasets / graders / failure attribution / historical replay / evaluation reportsはUnityAgent `Eval/` がcanonical owner。
- `Tools/BehaviorEval/` と `Tools/GoldenEval/` はPhase 8までcanonical Evalへのcompatibility shimとして残す。旧subprocess-capable Behavior runnerは `Eval/Compatibility/BehaviorEval/` の監査用referenceでありcanonical execution pathではない。
- Unity-Graph-Engineering `BehaviorEvalAdapter` のexecution bridgeはcanonical authorityではない。Runtime factsの評価変換だけがUnityAgent Evalへ取り込まれる。
- `DarumaPPAP/Unity-Graph-Engineering` の旧State/Continuation/ExecutionOrchestrator/LayeredMemory実装はPhase 8 Human Gateまで互換・監査用referenceとして残す。
- Legacy state/memory/evidence/eval artifactはexplicit compatibility loader/replay経由でのみ取り込み、ambiguous mappingはfail closedにする。
- `DarumaPPAP/MyUnityMCP` はMCP manifest / tool schema / package implementationの外部ownerのままとする。

## 6. User-specific entrypoints

- Comments: `Policy/User/user-policy.yaml#comment_system`
- C# / Formatting: `.agents/skills/` と `SkillReferences/CODING_STANDARDS.md`
- Architecture / ECS: `.agents/skills/unity-architecture-design/` と対応 `SkillReferences/`
- Rendering / Shader: `.agents/skills/unity-rendering/` + 選択 Context Pack / Knowledge
- Runtime / Performance: `.agents/skills/unity-runtime-evidence/`
- Orchestration Route: `Orchestration/Routing/task-routes.yaml`
- Development Graph: `Orchestration/Definitions/development-parent-graph.yaml`
- Context Budget: `Context/Budget/context-budget.yaml`
- Prompt Templates: `Context/Prompt/Templates/`
- Runtime Execution: `Runtime/Runner/` + `Runtime/Harnesses/`
- Persistence Layout: `Persistence/persistence-layout.yaml`
- State / Checkpoint / Resume: `Persistence/State/` + `Persistence/Checkpoint/` + `Persistence/Resume/`
- Durable Memory / Evidence: `Persistence/Memory/` + `Persistence/Evidence/`
- Golden / Actual Behavior Eval: `Eval/Golden/` + `Eval/Behavior/` + `Eval/Datasets/`
- Eval Attribution / Replay: `Eval/Attribution/` + `Eval/Replay/`

## 7. Completion handoff

OrchestrationからRuntimeへ、適用Policy revision / Route / Context ID / Context Fingerprint / Execution Profile / Task Contract runtime projection / mutation scope / validation requirementsを渡します。RuntimeはExecutionResult / typed RuntimeFailure / MutationEvidence / captured Evidence / Telemetryを返します。Persistenceはそのうちdurableに保持すべきState/Evidence/Memory/Checkpoint/Sessionをcanonical contractsに従って保存します。EvalはRuntime/Persistenceのstructured factsとcanonical GoldenContract/Datasetを読み、quality measurement / failure attribution / regression reportを生成します。必要な改善はChangeProposalとして提案しますが、production authorityを直接書き換えません。

## 8. Anti-regression

- `AGENTS.md`へ詳細規約本文を戻さない。
- Policy canonical sourceを互換Sourceで上書きしない。
- ContextからRoute/Graph/Retry authorityを新設しない。
- Contextからdurable Memory/Checkpoint/Evidence storeを書き込まない。
- Orchestrationからsubprocess/Unity/tool executionやhard Runtime enforcementを実装しない。
- Orchestrationからdurable State/Memory/Checkpoint/Evidence storeを書き込まない。
- Runtimeからsemantic Graph/TODO/replan authorityを新設しない。
- Runtimeからdurable Evidence/Memory/Checkpoint truthを書き込まない。
- PersistenceからRoute/semantic decision/Runtime execution/Eval grading authorityを新設しない。
- EvalからRuntime/process/tool/Unity executionを実装しない。
- EvalからPolicy/Context/Orchestration/Runtime/Persistence/Operationsのproduction definitionを直接変更しない。
- `not_observed` runをAgent品質regressionとして数えない。
- Runtime structured factsをEval側のdiff/text parserで再構築しない。
- Checkpoint/Memory/Evidenceを同じrecordとして扱わない。
- Resume migrationでoriginal checkpoint/evidenceを上書きしない。
- RuntimeでAgent qualityをgradeしない。
- 新しい旧Path直参照・writeを追加しない。
- Golden expectationをPromptへ混入させない。
