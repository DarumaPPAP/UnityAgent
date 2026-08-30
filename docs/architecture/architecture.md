# UnityAgent Architecture v3.1

Status: **Canonical Architecture Contract / Phase 10 operational**

## Canonical repository

```text
UnityAgent/
├─ AGENTS.md
├─ Policy/
├─ Context/
├─ Orchestration/
├─ Runtime/
├─ Persistence/
├─ Operations/
├─ Eval/
├─ .agents/
├─ SkillReferences/
├─ Specs/
├─ Tools/
└─ docs/
```

`DarumaPPAP/UnityAgent` が Production execution を含む canonical single-repository authority です。

Phase 8 cutover は完了済みです。legacy `.ai/` authority、Context/Eval/Persistence compatibility layer、old Eval / Loop shims、`DarumaPPAP/Unity-Graph-Engineering` への Production execution dependency を active authority として復活させません。

Migration時点の旧構造は `docs/migration/` や Historical Eval Dataset / Replay に監査証跡として残せますが、current Production bootstrap では解決しません。

## Authority contract

```text
Policy defines
Orchestration decides
Context materializes
Runtime executes
Persistence remembers
Operations observes and controls
Eval measures and proposes
```

近くのComponentで実装できることと、そのComponentがAuthorityを所有することは同義ではありません。

### Policy

`Policy/` は user/security/approval/evidence/risk rules を所有します。ユーザー固有Policyの正本は `Policy/User/user-policy.yaml` です。

Policy は execution state、tool call、graph scheduling、quality grading を所有しません。

### Orchestration

`Orchestration/` は semantic decision plane です。

- Primary Route selection
- ParentGraph / SubGraph / Node / Edge
- Branch / Join / Parallel
- Local semantic loop
- semantic continue / replan
- Task Contract
- Runtime handoff

Primary Route の正本は `Orchestration/Routing/task-routes.yaml`、canonical Task Contract は `Orchestration/Contracts/TaskContracts/` にあります。

```text
Parent Graph
  -> SubGraph
      -> Node / Edge / Gate
          -> Local Loop when needed
```

Local Loopを独立したtop-level control planeとしてGraphの横へ置きません。

### Context

`Context/` は current-call の model input を bounded に materialize します。

- Context selection catalog
- Context Pack
- Retrieval
- Knowledge selection
- Context Budget / Compression
- Prompt materialization
- current-call Context provenance

Route selection は Orchestration が先に行います。Context selection の正本は `Context/Selection/context-catalog.yaml`、materialization は `Context/Assembly/materialize_context.py`、Context Budget は `Context/Budget/context-budget.yaml` です。

Context は durable State / Memory / Checkpoint / Evidence truth ではありません。

### Runtime / Execution Harness Plane

`Runtime/` は実行可能な処理とhard safetyを所有します。

- model / Codex runner
- dispatcher / tool execution
- timeout / cancellation / hard retry ceiling / max turns / cost ceiling
- sandbox / mutation scope
- permission / guardrail enforcement
- Unity / Test / Performance / SCM harness
- current-run verification / evidence capture / telemetry

```text
Runtime/Harnesses/
├─ Unity/
├─ Tests/
├─ Performance/
└─ SCM/
```

Semantic Route / Graph / replan は Runtime のAuthorityではありません。

### Persistence

`Persistence/` は durable truth layer です。

- ExecutionState / WorkflowState / LoopControlState
- Checkpoint / Resume
- Session
- Memory
- durable Evidence

```text
Checkpoint != Memory != Evidence
```

RuntimeでcaptureされたEvidenceは、`Persistence/Evidence/` へappendされて初めてhistorical durable Evidenceになります。Resume都合でoriginal Evidenceを上書きしません。

### Operations

`Operations/` は production observability、detection、incident/runbook、approved runtime control、rollout/rollback/configuration change managementを所有します。

`Operations/RuntimeControl` と `Runtime/ExecutionControl` は別責務です。OperationsはPolicy/Approval済みcommandだけをauthority別control APIへ渡します。

### Eval

`Eval/` は datasets、Golden Contracts、Behavior grading、Attribution、Historical Replay、Rebaseline、Regression、ChangeProposalを所有します。

EvalはRuntime/Codex/Unity/process executionを実装せず、Production definitionを直接変更しません。canonical structured factが存在する場合、弱いprose/diffからauthority factを再構築しません。

## Default execution flow

bounded TaskではFast Pathを優先します。

```text
User Request
  ↓
Policy
  ↓
Task Fingerprint
  ↓
Orchestration Route
  ↓
Context materialization
  ↓
Runtime handoff / execution
  ↓
Verification / Evidence capture
  ↓
Persistence append
  ↓
Eval measurement when required
  ↓
Result
```

Semantic coordinationが必要な場合だけ `Orchestration/Definitions/development-parent-graph.yaml` を使用します。

## Recovery ownership

```text
Semantic Recovery    -> Orchestration
Execution Recovery   -> Runtime
Operational Recovery -> Operations
```

Semantic retry/replan と transient process/tool retry、timeout、process cleanup、hard retry ceiling を混同しません。

## Approval contract

```text
Policy / Approval requirement
        ↓
Orchestration gate placement
        ↓
Runtime enforcement
        ↓
approve / edit / reject
        ↓
continue / replan / stop
```

PolicyがRequirementを定義し、Orchestrationがsemantic stop pointを決め、Runtimeが実行境界をenforceします。

## Evidence contract

Compile / Runtime / Editor / Player / Target Device / Performance / Visual は別Evidence stateとして扱います。

- `unavailable` を成功扱いしない
- `not_observed` をAgent品質denominatorへ入れない
- CompileだけでRuntime / Player / Visual / Performanceを保証しない
- Golden expected contentをProduction Prompt / Contextへ注入しない

Runtime EvidenceはPersistence append後にdurable truthとなります。

## Evaluation and regression contract

Canonical Production qualityは4 caseで観測します。

- `GOLDEN-ARCH-001`
- `GOLDEN-NAMING-001`
- `GOLDEN-MUTATION-001`
- `GOLDEN-EVIDENCE-001`

Phase 9 Frozen Baseline:

`Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml`

Frozen state:

- 4/4 observed
- 4/4 quality-passed
- `regression_pass_rate = 1.0`
- canonical failure taxonomy clean
- DefinitionFingerprint 4/4
- Historical Replay namespace coverage passed

Phase 10 comparatorはcandidateをこのBaselineと比較し、次を返します。

- `PASS`
- `BLOCK_REGRESSION`
- `BLOCK_INCONCLUSIVE`
- `REBASELINE_REQUIRED`

PASS後もBaselineは自動更新しません。

## Production Smoke

Canonical Production path:

```text
.github/ProductionSmoke/run_one_repo_smoke.py
        ↓
Orchestration / Context materialization
        ↓
Runtime/Runner/Codex
        ↓
Persistence/Evidence
        ↓
Eval/Behavior/grade_production_smoke.py
        ↓
Eval/Rebaseline/build_rebaseline_summary.py
        ↓
Eval/Regression/compare_baseline.py
```

Phase 10の標準運用は `Tools/Phase10/run_local_regression_gate.py` です。ローカルの認証済みCodex CLI sessionを使用し、Frozen Baselineと同じ `gpt-5.6-luna / xhigh` を既定比較identityとします。

GitHub-hosted Regression Gateはoptional CI pathです。

## Versioning / DefinitionFingerprint

比較・Resume・Rebaselineで少なくとも次を追跡します。

- architecture version
- policy revision
- prompt revision
- context revision
- graph revision
- runtime profile revision
- tool schema revision
- checkpoint schema revision
- evidence schema revision
- eval contract revision

Source revision、Runtime identity、Codex versionもprovenanceとして保持します。

## Migration state

```text
Phase 0   Architecture contract                       complete
Phase 1   Canonical contracts                         complete
Phase 2   Policy + Context                            complete
Phase 3   Runtime / Harness                           complete
Phase 4   Orchestration                               complete
Phase 5   Persistence                                 complete
Phase 6   Eval consolidation                          complete
Phase 7   Operations                                  complete
Phase 8   Single-repo cutover / legacy removal        complete
Phase 9   Production re-baseline / baseline freeze    complete
Phase 10  Baseline comparator / regression gate       complete
```

過去Phaseの詳細は `docs/migration/` に残します。Migration文書のhistorical pathをcurrent authorityとして読み替えません。

## Protected user-specific behavior

Architecture変更は、現在のユーザー固有Policyを保持します。

- minimum cohesive solution first
- no premature abstraction / generalization
- exact evidence honesty
- mutation safety
- approval boundaries
- existing comment policy
- naming policy
- no unrequested implementation

詳細なBootstrap Mapと責務境界は `AGENTS.md` を参照してください。
