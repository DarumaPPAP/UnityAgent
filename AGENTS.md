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
14. `Context/Manifest/` は current-call Context provenanceを記録し、WorkflowState / Checkpoint / Evidence truth / Graph topologyの正本にはしない。
15. 旧Pathを必要とする未移行機能は `Context/Compatibility/legacy-path-map.yaml` の read-only key経由だけで参照する。新規writeは禁止する。

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
| Eval Contracts | `Eval/` | quality measurement / attribution |

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
- Unknown Project Factや不足Bindingを推測で埋めない。
- `unavailable`を成功扱いしない。CompileだけでRuntime / Visual / Performance / Player / 実機を承認しない。
- EvalのGolden expected contentをProduction Promptへ注入しない。
- RuntimeはAgent品質を採点しない。
- RuntimeのUnity Artifact GraphはAsset dependency graphであり、Agent ParentGraph/SubGraphではない。
- Compatibilityはread-only。旧Sourceの削除はPhase 8の明示Human Gateまで行わない。

## 5. Current compatibility

- Phase 3以降、actual executionはUnityAgent `Runtime/` がcanonical owner。
- Phase 4以降、Route / ParentGraph / SubGraph / Node / Gate / LocalLoop / semantic TODO selection / semantic replanはUnityAgent `Orchestration/` がcanonical owner。
- Phase 5以降、ExecutionState / WorkflowState / LoopControlState / RunCheckpoint / SessionRecord / MemoryRecord / EvidenceRecord のdurable truthはUnityAgent `Persistence/` がcanonical owner。
- `DarumaPPAP/Unity-Graph-Engineering` の旧State/Continuation/ExecutionOrchestrator/LayeredMemory実装はPhase 8 Human Gateまで互換・監査用referenceとして残すが、新しいPersistence authorityではない。
- Legacy state/memory/evidenceはexplicit compatibility loader/migration経由でのみ取り込み、ambiguous mappingはfail closedにする。
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
- Golden / Actual Behavior Eval: `Eval/` と既存Tests。Runtime/Orchestration/Persistenceはgradingしない。

## 7. Completion handoff

OrchestrationからRuntimeへ、適用Policy revision / Route / Context ID / Context Fingerprint / Execution Profile / Task Contract runtime projection / mutation scope / validation requirementsを渡します。RuntimeはExecutionResult / typed RuntimeFailure / MutationEvidence / captured Evidence / Telemetryを返します。Persistenceはそのうちdurableに保持すべきState/Evidence/Memory/Checkpoint/Sessionをcanonical contractsに従って保存し、Orchestration/Contextへread-onlyな事実・projectionを返します。Evalは保存済み事実を測定しますが、Persistenceを書き換えません。

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
- Checkpoint/Memory/Evidenceを同じrecordとして扱わない。
- Resume migrationでoriginal checkpoint/evidenceを上書きしない。
- RuntimeでAgent qualityをgradeしない。
- 新しい旧Path直参照・writeを追加しない。
- Golden expectationをPromptへ混入させない。
