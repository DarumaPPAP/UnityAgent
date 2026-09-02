# UnityAgent Architecture

Status: **Canonical Architecture Contract / Production Tool Runtime integrated**

この文書はUnityAgentの**現在Architecture**を人間向けに説明します。

過去のPhase移行記録は `docs/migration/` に残しますが、current Production Authorityとしては使用しません。

---

## 1. Canonical Repository

```text
UnityAgent/
├─ AGENTS.md
├─ Policy/
├─ Orchestration/
├─ Context/
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

`DarumaPPAP/UnityAgent` がProduction executionを含むcanonical single-repository authorityです。

`DarumaPPAP/Unity-Graph-Engineering`はProduction execution dependencyではありません。過去Migration provenanceとして参照できても、current bootstrapの正本には戻しません。

---

## 2. Authority Contract

```mermaid
flowchart LR
    P[Policy<br/>defines] --> O[Orchestration<br/>decides]
    O --> C[Context<br/>materializes]
    C --> R[Runtime<br/>executes]
    R --> S[Persistence<br/>remembers]
    S --> OP[Operations<br/>observes / controls]
    S --> E[Eval<br/>measures / proposes]
```

```text
Policy defines
Orchestration decides
Context materializes
Runtime executes
Persistence remembers
Operations observes / controls
Eval measures / proposes
```

近くに実装できることと、そのAreaがAuthorityを持つことは同義ではありません。

### Policy

所有:

- User Policy
- Risk
- Security
- Approval requirement
- Evidence requirement

所有しない:

- Provider selection
- Tool dispatch
- Graph scheduling
- quality grading

### Orchestration

所有:

- Primary Route
- ParentGraph / SubGraph
- semantic Node / Edge / Gate
- semantic continue / replan
- Task Contract
- Runtime handoff
- Design Review placement

所有しない:

- subprocess execution
- Unity CLI / MCP Tool dispatch
- hard timeout / process kill
- durable State write

### Context

所有:

- Context selection
- Context Pack
- Retrieval
- Knowledge
- Context Budget
- current-call Materialization

所有しない:

- Route selection
- Provider selection
- durable Memory / Evidence / Checkpoint

### Runtime

所有:

- process / tool execution
- Environment discovery
- Provider resolution
- Production dispatch
- timeout / cancellation
- bounded infrastructure retry
- Mutation Scope enforcement
- verification / current-run Evidence capture

所有しない:

- semantic replan
- durable Evidence truth
- Agent quality grading

### Persistence

所有:

- ExecutionState
- WorkflowState
- LoopControlState
- Checkpoint / Resume
- Session
- Memory
- durable Evidence

```text
Checkpoint != Memory != Evidence
```

### Operations

所有:

- Observability
- Detection
- Incident / Runbook
- approved Runtime Control
- Change Management / rollout / rollback

### Eval

所有:

- Golden / Behavior Eval
- Attribution
- Historical Replay
- Rebaseline
- Regression comparison
- ChangeProposal

EvalはProduction executionやProduction definitionの直接変更を行いません。

---

## 3. Default Execution Flow

bounded TaskではFast Pathを優先します。

```mermaid
flowchart TD
    U[User Request] --> P[Policy]
    P --> T[Task Fingerprint]
    T --> R[Primary Route]
    R --> C[Context Materialization]
    C --> D{Design Review needed?}
    D -->|yes| H[Human Review]
    H -->|approve| X[Runtime Handoff]
    H -->|revise| C
    H -->|reject| O[Result]
    D -->|no| X
    X --> V[Verification / Evidence]
    V --> S[Persistence]
    S --> E[Eval when required]
    E --> O
```

Semantic coordinationが必要な場合だけ `Orchestration/Definitions/development-parent-graph.yaml` を使います。

Local Loopは独立したtop-level control planeではなく、SubGraph内部の限定されたcycleです。

---

## 4. Production Tool Runtime

Production Cutover後、Unity Editor / Build / Test / MCP / Player等の具体的実行先はRuntime Toolingへ集約します。

OrchestrationはProvider固有Tool名ではなくCapabilityを要求します。

```text
Skill      = どう作業するか
Capability = 何を実現したいか
Provider   = 誰が実行できるか
Transport  = どう接続するか
Evidence   = 実際に何を観測したか
```

### Runtime内部

```mermaid
flowchart TD
    H[Runtime Handoff<br/>CapabilityRequest] --> G[Last-mile Guard]
    G --> B[ToolBroker]
    B --> R[Capability Resolver]
    R --> E[Environment Snapshot]
    E --> PR[Provider Registry]
    PR --> D[Production Dispatcher]
    D --> P[Concrete Provider Adapter]
    P --> X[Structured ProviderResult]
    X --> F{Infrastructure failure?}
    F -->|yes| FB[Same Capability Fallback]
    FB --> B
    F -->|no| N[Evidence Normalizer]
```

重要:

- Orchestrationは`provider` / `provider_ref`を指定しない。
- ContextはProviderを選ばない。
- Provider RegistryはPotential capabilityを記述する。
- 実行可能性はConcrete adapter + Environment + live discoveryで再確認する。
- executor未登録は`backend_not_implemented`であり成功ではない。
- Fallbackは同一CapabilityかつSafety / Evidenceが同等以上の場合だけ。

詳細は [Production Tool Runtime](production-tool-runtime.md) を参照してください。

---

## 5. Capability Contract

Canonical Capabilityは15個です。

```text
project.inspect
source.read
source.patch
static.review
git.diff
compile.observe
project.test
project.build
scene.inspect
scene.mutate
profiler.observe
visual.capture
domain.workflow
player.observe
player.mutate
```

Capability Request / ResolutionのSchemaは `Runtime/Contracts/` が正本です。

Semantic capability requirementは `Orchestration/ToolRouting/capability-routing.yaml`、説明用Contextは `Context/Selection/tool-capability-catalog.yaml` が担当します。

---

## 6. Provider Resolution Boundary

```mermaid
flowchart TD
    A[CapabilityRequest] --> B{Policy allowed?}
    B -->|no| BP[blocked_by_policy]
    B -->|yes| C{Approval / Scope OK?}
    C -->|no| BA[blocked_by_approval / scope_violation]
    C -->|yes| D[Environment / Project Binding]
    D --> E[Safety / Evidence floors]
    E --> F[Candidate ranking]
    F --> G{Unique winner?}
    G -->|no| AM[ambiguous_binding / unavailable / unknown]
    G -->|yes| R[resolved Provider]
```

Provider availabilityはEnvironment Factです。

```text
Unity CLIなし
MCPなし
Playerなし
```

のどれか1つだけでAgent全体を停止しません。

ただし必要Evidenceを取得できない場合は、その不足を明示します。

---

## 7. Safety / Recovery Ownership

```text
Semantic Recovery    -> Orchestration
Execution Recovery   -> Runtime
Operational Recovery -> Operations
```

### Runtime fallbackで変えてはいけないもの

- Capability
- Project Root
- operation kind
- Required Evidence
- Mutation Scope
- Approval provenance

MyUnityMCP Mutationが利用不能でも、raw Scene YAMLやarbitrary `eval`へsilent downgradeしません。

### Safe Mode

Safe ModeではSource recoveryとScene mutationを分離します。

```mermaid
flowchart TD
    S[Safe Mode] --> D[Compiler Diagnosticを限定取得]
    D --> P[許可されたSourceのみPatch]
    P --> R[Environment再観測]
    R --> N{Editor正常?}
    N -->|yes| T[通常Tool Runtimeへ復帰]
    N -->|no| B[blocked / partial]
```

---

## 8. Evidence Contract

Evidence stateは分離します。

```text
Compile
Editor
Test
Player
Target Device
Performance
Visual
```

```text
Compile PASS
!= Runtime PASS
!= Player PASS
!= Performance PASS
```

RuntimeでcaptureしたEvidenceは `Persistence/Evidence/` にappendされて初めてhistorical durable Evidenceになります。

`not_observed`をAgent品質denominatorへ入れません。

---

## 9. DefinitionFingerprint / Regression

比較・Resume・Rebaselineでは少なくとも次を追跡します。

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

Production Tool Runtime Cutoverでblocking fieldが変わった場合、既存Frozen Baselineとの比較は `REBASELINE_REQUIRED` になるのが正常です。

Baselineを自動更新してdriftを隠しません。

Regression decision:

- `PASS`
- `BLOCK_REGRESSION`
- `BLOCK_INCONCLUSIVE`
- `REBASELINE_REQUIRED`

---

## 10. Canonical Source Map

| Area | Canonical Source |
| --- | --- |
| User Policy | `Policy/User/user-policy.yaml` |
| Capability Policy | `Policy/Security/tool-capability-policy.yaml` |
| Route | `Orchestration/Routing/task-routes.yaml` |
| Capability routing | `Orchestration/ToolRouting/capability-routing.yaml` |
| Context catalog | `Context/Selection/context-catalog.yaml` |
| Capability descriptions | `Context/Selection/tool-capability-catalog.yaml` |
| Runtime contracts | `Runtime/Contracts/` |
| Environment discovery | `Runtime/Tooling/Environment/` |
| Provider Registry | `Runtime/Tooling/provider_registry.yaml` |
| Resolver | `Runtime/Tooling/capability_resolver.py` |
| Tool Broker | `Runtime/Tooling/tool_broker.py` |
| Production Dispatcher | `Runtime/Dispatcher/tool_runtime_dispatcher.py` |
| Runtime Guard | `Runtime/Guardrails/tool_runtime_guard.py` |
| Fallback | `Runtime/Tooling/fallback_policy.py` |
| Providers | `Runtime/Tooling/Providers/` |
| Evidence normalization | `Runtime/EvidenceCapture/provider_evidence.py` |
| Durable Evidence | `Persistence/Evidence/` |
| Regression | `Eval/Regression/` |
| Production Runtime validator | `Tools/ProductionToolRuntime/validate_production_tool_runtime.py` |

---

## 11. Historical Migration

`docs/migration/`はMigration時点の判断・旧Path・削除対象・互換性判断を保存するHistorical recordです。

Historical文書に現れる旧PathやPhase名をcurrent Production contractとして読み替えません。

現在Architectureを理解する場合は次を優先します。

1. `AGENTS.md`
2. Canonical source files
3. この文書
4. `docs/architecture/production-tool-runtime.md`
5. Supporting `Specs/`
