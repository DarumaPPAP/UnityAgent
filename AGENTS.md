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
6. `Context/Assembly/materialize_context.py` で current-call `MaterializedContextView` を構築し、Context Budgetを評価する。
7. 単純でboundedなTaskは `Policy -> Orchestration Route -> Context -> Runtime -> Verification -> Result` のFast Pathを優先する。
8. semantic coordinationが必要なTaskだけ `Orchestration/Definitions/development-parent-graph.yaml` の ParentGraph/SubGraph/Node/Gate/LocalLoop を使う。
9. OrchestrationがRuntime handoffを作り、actual process/tool execution、hard timeout/cancellation、mutation scope、tool dispatch、health/verification/evidence capture は `Runtime/` が実行する。
10. MCP が必要な場合、Contextは必要Description/Manifestを選択し、Policyが許可条件を定義し、Runtimeが実Tool Groupを公開する。
11. Orchestrationは `Persistence/Contracts/WorkflowState` / `LoopControlState` 互換のstate patchを返すが、durable writeは行わない。
12. `Context/Manifest/` は current-call Context provenanceを記録し、WorkflowState / Checkpoint / Evidence truth / Graph topologyの正本にはしない。
13. 旧Pathを必要とする未移行機能は `Context/Compatibility/legacy-path-map.yaml` の read-only key経由だけで参照する。新規writeは禁止する。

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
| Persistence Contracts | `Persistence/Contracts/` | state/checkpoint/memory/evidence contracts |
| Eval Contracts | `Eval/` | quality measurement / attribution |

## 4. Responsibility guards

- Policy defines; Context materializes; Orchestration decides; Runtime executes; Persistence remembers; Operations observes/controls; Eval measures/proposes.
- ContextはRoute decision authorityではない。Orchestrationが明示したRouteだけをmaterializeする。
- Local LoopはSubGraph内のedge/cycleであり、top-level control planeではない。
- Orchestrationのsemantic continue/replanとRuntimeのhard retry/timeout/process killを混同しない。
- Orchestrationはquota/lease/durable state accountingを所有しない。
- Unknown Project Factや不足Bindingを推測で埋めない。
- `unavailable`を成功扱いしない。CompileだけでRuntime / Visual / Performance / Player / 実機を承認しない。
- EvalのGolden expected contentをProduction Promptへ注入しない。
- RuntimeはAgent品質を採点しない。
- RuntimeのUnity Artifact GraphはAsset dependency graphであり、Agent ParentGraph/SubGraphではない。
- Compatibilityはread-only。旧Sourceの削除はPhase 8の明示Human Gateまで行わない。

## 5. Current compatibility

- Phase 3以降、actual executionはUnityAgent `Runtime/` がcanonical owner。
- Phase 4以降、Route / ParentGraph / SubGraph / Node / Gate / LocalLoop / semantic TODO selection / semantic replanはUnityAgent `Orchestration/` がcanonical owner。
- `DarumaPPAP/Unity-Graph-Engineering` の旧Continuation/ExecutionOrchestratorはPhase 8 Human Gateまで互換・監査用referenceとして残すが、新しいOrchestration authorityではない。
- Durable WorkflowState / Checkpoint / Memory / EvidenceRecord のauthoritative persistenceはPhase 5で確立する。
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
- Golden / Actual Behavior Eval: `Eval/` と既存Tests。Runtime/Orchestrationはgradingしない。

## 7. Completion handoff

OrchestrationからRuntimeへ、適用Policy revision / Route / Context ID / Context Fingerprint / Execution Profile / Task Contract runtime projection / mutation scope / validation requirementsを渡します。RuntimeはExecutionResult / typed RuntimeFailure / MutationEvidence / Evidence refs / Telemetry refsを返します。Orchestrationはそれらの事実からsemantic next actionを決定しますが、durable stateやquality gradeを正本として保持しません。

## 8. Anti-regression

- `AGENTS.md`へ詳細規約本文を戻さない。
- Policy canonical sourceを互換Sourceで上書きしない。
- ContextからRoute/Graph/Retry authorityを新設しない。
- Orchestrationからsubprocess/Unity/tool executionやhard Runtime enforcementを実装しない。
- Orchestrationからdurable Memory/Checkpoint/Evidence storeを書き込まない。
- Runtimeからsemantic Graph/TODO/replan authorityを新設しない。
- RuntimeでAgent qualityをgradeしない。
- 新しい旧Path直参照・writeを追加しない。
- Golden expectationをPromptへ混入させない。
