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
src/unityagent/orchestration
  ↓
Context Assembly
  ↓
Runtime Handoff
  ├─ Tool Capability → ToolBroker → Provider
  └─ Specialist Reasoning → CodexRunner
  ↓
Persistence / Evidence
```

- src/unityagent/policy: Risk / Approval / Evidence requirementを定義する
- src/unityagent/orchestration: Route、Specialist selection、Capability、Reasoning phaseを決める
- src/unityagent/context: 必要なFact / Decision / Skill / Observationだけを選別しFingerprintする
- src/unityagent/runtime: Tool ProviderまたはCodexRunnerを実行する
- src/unityagent/persistence: Run state、Observation、Reasoning Artifact、Evidenceをdurableに保存する
- eval: 品質とRegressionを測定する

Entry、SubAgent、ProviderはこのAuthorityを迂回しません。

## 2. Production Specialist

同居SubAgentの正本は `subagent/<id>/manifest.yaml` とその参照先です。UnityAgentが所有するRuntime Profile・Activation・Contextは `src/unityagent/runtime/reference_implementation/subagent-catalog.yaml` を参照します。外部UnitySubAgentHubの履歴やSource Lockを、現在の同居定義の正本として扱いません。

| Specialist | Execution | Semantic capability | Required observations |
|---|---|---|---|
| `artist_subagent` | provider-backed | `artist.camera.inspect`, `artist.camera.refine`, `visual.capture` | Artist backend activation facts |
| `graphics_subagent` | reasoning | `graphics.inspect`, `graphics.diagnose`, `graphics.validate` | `project.inspect`, `source.read` |
| `world_creator_subagent` | reasoning | `world.plan` | none |
| `qa_subagent` | reasoning | `performance.analyze` | `profiler.observe` |

Graphics / WorldCreator / QAの性能分析はConsumer Catalog v3へ登録済みです。説明上のPerformanceはQASubAgentの性能分析責務を指し、正本IDは `qa_subagent`、Capabilityは `performance.analyze` です。別の専門Agent IDは追加しません。同居ManifestからのSnapshotがConsumer Catalogと一致することをread-onlyのImport Gateで検証します。

**登録済み != Live Production Verified** です。Repository fixtureやSchema PASSだけでEditor / Player / Target Device / Visual / Performance成功を主張しません。

## 3. ReasoningとProvider-backedの違い

Provider-backed CapabilityはToolBrokerがEnvironment、Policy、Capability、Provider Registryを使って実行Backendを解決します。

Reasoning Capabilityは `src/unityagent/runtime/contracts/runtime-handoff.schema.yaml` の `specialist_reasoning` を使い、Provider IDを付けません。CodexRunnerがMaterialized ContextからSchema付きArtifactを生成し、次を検証した後にPersistenceへ記録します。

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
re-materialize src/unityagent/context
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

Production Control Planeは `src/unityagent/runtime/contracts/entry-request.v2.schema.yaml` を入口にします。

Entryは次を所有しません。

- Route
- Provider
- CapabilityRequest
- Mutation Scope
- Context ID / Fingerprint
- Runtime Handoff

Typed IntentからOrchestrationがTask Fingerprint、Route、CapabilityRequest、必要なMutation Scopeを生成し、Context AssemblyがContext identityを生成します。v1 EntryはValidation互換のため保持しますが、caller-owned Context / Route / CapabilityをProduction executionへ持ち込みません。

## 8. 同居定義とSnapshotの境界

`subagent/registry.yaml` が同居Manifestの索引です。Manifest v5からconsumer-neutralなSnapshot v3を生成し、UnityAgent所有のConsumer Catalog v3と照合します。Snapshotは現在のProject状態、Runtime Profile、Provider、Task Route、インストール済み状態を決定しません。外部Hubの公開や登録を理由にRuntime Catalogを自動更新しません。

同居定義の検証に外部Hub checkoutは不要です。互換用の外部Hub Source Lock／Import CLIは残りますが、同居定義の更新とは別の境界です。Candidate用 `candidate-specialists.yaml` と各 `*-pilot-profile.yaml` は過去の評価資料であり、現在の選出へ注入しません。

戦略観測はSpecialist向けの検証済みObservationやAcceptance Evidenceとは別です。結果確定後に `strategy_observation_refs` へ記録し、Reasoning Contextや必須Gateを変更しません。詳細は[適応実行方針](adaptive-subagent-execution.md)を参照してください。

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
- `src/unityagent/orchestration/routing/task-routes.yaml`
- `src/unityagent/context/selection/context-catalog.yaml`
- `src/unityagent/context/assembly/materialize_context.py`
- `src/unityagent/runtime/reference_implementation/subagent-catalog.yaml`
- `src/unityagent/runtime/handoff/reasoning_runtime.py`
- `src/unityagent/runtime/runner/codex/codex_runner.py`
- `src/unityagent/runtime/contracts/runtime-handoff.schema.yaml`
- `src/unityagent/persistence/`
- `docs/architecture/architecture.md`
