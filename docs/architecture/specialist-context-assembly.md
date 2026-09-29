# Specialist Context Assembly

Status: **Current Architecture Guide**

この文書は、UnityAgentがOptional Specialistへ渡すContext、Observation、Reasoning Handoff、Evidence境界の現在仕様を説明します。過去のPilot比較や移行作業は `docs/superpowers/` と `docs/migration/` に残し、Current Contractとしては扱いません。

## 1. Authority

Specialistは第二のControl Planeではありません。

```text
Entry
  ↓
UnityAgent Control Plane
  ↓
Orchestration
  ↓
Context Assembly
  ↓
Runtime Handoff
  ├─ Tool Capability → ToolBroker → Provider
  └─ Specialist Reasoning → CodexRunner
  ↓
Persistence / Evidence
```

- Policy: Risk / Approval / Evidence requirementを定義する
- Orchestration: Route、Specialist selection、Capability、Reasoning phaseを決める
- Context: 必要なFact / Decision / Skill / Observationだけを選別しFingerprintする
- Runtime: Tool ProviderまたはCodexRunnerを実行する
- Persistence: Run state、Observation、Reasoning Artifact、Evidenceをdurableに保存する
- Eval: 品質とRegressionを測定する

Entry、SubAgent、ProviderはこのAuthorityを迂回しません。

## 2. Production Specialist

現行Consumer Catalogは `Runtime/ReferenceImplementation/subagent-catalog.yaml`、Hub側の静的正本はUnitySubAgentHubの `SubAgents/<id>/manifest.yaml` です。

| Specialist | Execution | Semantic capability | Required observations |
|---|---|---|---|
| `artist_subagent` | provider-backed | `artist.camera.inspect`, `artist.camera.refine`, `visual.capture` | Artist backend activation facts |
| `graphics_subagent` | reasoning | `graphics.inspect`, `graphics.diagnose`, `graphics.validate` | `project.inspect`, `source.read` |
| `world_creator_subagent` | reasoning | `world.plan` | none |
| `performance_subagent` | reasoning | `performance.analyze` | `profiler.observe` |

Graphics / WorldCreator / PerformanceはConsumer Catalog v3へ登録済みです。Hub Manifest v5 / Snapshot v3との整合は固定fixtureで検証します。

**登録済み != Live Production Verified** です。Repository fixtureやSchema PASSだけでEditor / Player / Target Device / Visual / Performance成功を主張しません。

## 3. ReasoningとProvider-backedの違い

Provider-backed CapabilityはToolBrokerがEnvironment、Policy、Capability、Provider Registryを使って実行Backendを解決します。

Reasoning Capabilityは `Runtime/Contracts/runtime-handoff.schema.yaml` の `specialist_reasoning` を使い、Provider IDを付けません。CodexRunnerがMaterialized ContextからSchema付きArtifactを生成し、次を検証した後にPersistenceへ記録します。

- profile / capability identity
- source `context_id`
- source `context_fingerprint`
- output schema
- domain-specific semantic contract
- read-only / planning-only境界
- original Projectへの変更有無
- Evidence level

「Providerless」はTool Providerが不要という意味であり、Model Runtimeが不要という意味ではありません。

## 4. Context selection

Specialist Contextは既存Materialized Contextの一部です。第二のContext Engineを作りません。

主な型:

- `project_fact`
- `project_decision`
- `platform_fact`
- `platform_decision`
- `task_fact`
- verified observation fact

Factは観測Source、Revision、Freshnessを持ちます。DecisionはユーザーまたはProject Policyに由来する明示Decisionだけを採用します。unknown / stale / 別attemptの値をcurrent Factへ昇格しません。

選択したContextはBudgetへ全量算入し、必要項目を削って通しません。Budget超過は停止条件です。

## 5. Observation gate

`execution.required_observation_capabilities` があるReasoning Specialistは、Reasoningより先に既存CapabilityRequest / ToolBroker経路でObservationを取得します。

```text
activate
  ↓
dispatch required observations
  ↓
durable Evidence validation
  ↓
Observation → typed Fact
  ↓
re-materialize Context
  ↓
select
  ↓
specialist_reasoning
```

Observationは未信頼データとして扱い、InstructionやPolicyとして解釈しません。EvidenceStoreはRun、Project、Capability、durability、verification、payload digest、definition fingerprintを照合します。

GraphicsではRender Pipelineや対象Sourceが不明なら `required_context_missing` で停止します。Performanceでは単一Editor snapshotを `limited` とし、比較・回帰判定へ昇格しません。

## 6. WorldCreator planning boundary

`world.plan` はplanning-onlyです。

- Provider resolution: not required
- direct Unity mutation: prohibited
- automatic visual acceptance: prohibited
- source Context binding: required
- Human Review: required

World Plan内の `domain_hint` はRoute決定ではありません。Plan生成後、UnityAgentが後続Route、Policy、Approval、Capabilityを改めて解決します。

## 7. Entry v2 boundary

Production Control Planeは `Runtime/Contracts/entry-request.v2.schema.yaml` を入口にします。

Entryは次を所有しません。

- Route
- Provider
- CapabilityRequest
- Mutation Scope
- Context ID / Fingerprint
- Runtime Handoff

Typed IntentからOrchestrationがTask Fingerprint、Route、CapabilityRequest、必要なMutation Scopeを生成し、Context AssemblyがContext identityを生成します。v1 EntryはValidation互換のため保持しますが、caller-owned Context / Route / CapabilityをProduction executionへ持ち込みません。

## 8. Hub snapshot boundary

UnitySubAgentHubはconsumer-neutralなManifest Snapshot v3を出力します。Snapshotは現在のProject状態、Runtime Profile値、選択済みProvider、Task Routeを所有しません。

```text
Hub Manifest v5
  ↓
Hub Snapshot v3
  ↓
UnityAgent Offline Import Adapter
  ↓
Consumer Catalog v3
```

Import AdapterはSnapshotを検証し、UnityAgent所有のProfile値と照合します。Artifact公開だけでRuntime Catalogを自動更新しません。Hub SnapshotとConsumer Catalogの差分は通常のGit変更としてレビューします。

Candidate用 `Runtime/ReferenceImplementation/candidate-specialists.yaml` と各 `*-pilot-profile.yaml` は過去のPilot / Evaluation baselineとして残っています。Current Production selectionの正本は `subagent-catalog.yaml` です。

## 9. Supported baseline

Current Production baseline:

- Unity 6.x+ / Built-in
- Unity 6.x+ / URP
- Unity 6.x+ / HDRP

Unity 2022.3のbounded fallback / compatibility記録はHistorical Evidenceです。現行Production Supportへ読み替えません。

## 10. Verification rule

検証状態を混同しません。

```text
Static PASS
!= Repository fixture PASS
!= Live Reasoning PASS
!= Editor PASS
!= Player PASS
!= Target Device PASS
!= Performance PASS
!= Visual PASS
```

未観測は `not_observed`、利用不可は `unavailable`、一部だけ成立した場合は `partial_verified` として残します。

Canonical references:

- `AGENTS.md`
- `Orchestration/Routing/task-routes.yaml`
- `Context/Selection/context-catalog.yaml`
- `Context/Assembly/materialize_context.py`
- `Runtime/ReferenceImplementation/subagent-catalog.yaml`
- `Runtime/Handoff/reasoning_runtime.py`
- `Runtime/Runner/Codex/codex_runner.py`
- `Runtime/Contracts/runtime-handoff.schema.yaml`
- `Persistence/`
- `docs/architecture/architecture.md`
