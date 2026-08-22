# Context Manifest Runtime

Context Manifest Runtimeは、1回のUnityAgent Task Attemptで実際に選択されたTyped Context / Budget / Harness / Project Fact / Evidenceを記録するための実行トレースです。

## Source of truth

- Policy / Context / Harnessの正本は`.ai/`配下のCanonical YAMLです。
- Context PackはTyped Context v3を使用します。
- Context Budgetの正本は`.ai/context-budget.yaml`です。
- Context Manifest v3.1 + Context Budget extension v1.0は正本を置き換えません。
- Execution GraphはContext Manifestから生成されるDerived Viewです。
- Generated Manifest / Budget Report / GraphからCanonical PolicyやHarnessを逆更新しません。

既定出力先は`.gitignore`対象の`Artifacts/ContextManifests/`です。

## Runtime flow

```text
Task Fingerprint
  ↓
Primary Route
  ↓
Typed Context Manifest Builder
  ├─ bindingを解決
  ├─ repository_referenceを選択
  ├─ external_referenceを分離
  ├─ context_includeを記録
  ├─ route_handoffを分離
  ├─ Project Fact provenance / freshnessを記録
  ├─ Primary Skill / Task Contract / Risk / Mutation Ruleを解決
  ├─ Required / Conditional Quality Gateを解決
  └─ unresolved bindingを明示
  ↓
Context Budget Engine
  ├─ Local Repository Contextを自動計測
  ├─ Project / External Observationを検証
  ├─ Retrieval Budgetを計算
  ├─ estimated_tokensを計算
  ├─ Compression結果を再計測
  └─ within_budget / compression_required / unmeasured / blocked
  ↓
Worker / Tool execution
  ↓
Evidence Recorder
  ↓
passed / failed / unavailable
  ↓
Execution Graph Projection
```

Mutation TaskはContext Budgetが`within_budget`になるまでWorker executionへ進みません。

## Typed Context v3

Context Packの`required` / `conditional`は次の5種類です。

| type | 意味 | Primary Route変更 |
| --- | --- | --- |
| `binding` | Task実行時に解決する値・Source | しない |
| `repository_reference` | UnityAgent内Artifact | しない |
| `external_reference` | 別Repository内Artifact | しない |
| `context_include` | 同一Primary Routeへ別Contextを追加 | しない |
| `route_handoff` | 別Routeへ責務移譲 | する |

`context_include`はInclude先を再帰展開しません。Context Expansionは1 hopまでです。

## Build

```bash
python Tools/ContextManifest/build_context_manifest.py \
  --request Tests/ContextManifest/requests/csharp-local-fix.yaml
```

Canonical BuilderはManifestへBudget Reportを付与し、Mutation Taskが`within_budget`でない場合は失敗します。

Graphも同時に生成する場合:

```bash
python Tools/ContextManifest/build_context_manifest.py \
  --request Tests/ContextManifest/requests/csharp-local-fix.yaml \
  --graph-output Artifacts/ContextManifests/golden-csharp-local-fix-a1.graph.yaml
```

## Runtime request

Builderへ渡すRequestはManifest全体ではなく、Task固有の確定情報と、UnityAgent Repository外SourceのRetrieval Observationだけを持ちます。

```yaml
task:
  id: camera-far-clip-fix
  route: csharp-local-fix
  fingerprint:
    intent: fix
    artifact: csharp
    scope: local
    failure_mode: compile
    architecture_state: decided
    mutation_target: source
    evidence_state: known
    project_access: authorized

bindings:
  target_source:
    kind: source
    values:
      - Assets/Settings/Debug/EnvironmentDebugWindow.cs
    reason: mutation_target

  direct_callers_or_interfaces:
    kind: source
    values:
      - Assets/Settings/Debug/CameraDebugWindow.cs
    reason: direct_dependency

unresolved_bindings:
  - unity_version_when_api_sensitive

project_facts:
  - key: unity.version
    value: 6000.3.0f1
    source_kind: detected_project
    source_path: ProjectSettings/ProjectVersion.txt
    revision: sha256:example
    observed_at_attempt: 1
    freshness:
      status: current
      checked_at_attempt: 1
    reason: project_fact

retrieval_observations:
  - source_id: project:Assets/Settings/Debug/EnvironmentDebugWindow.cs
    role: target_source
    source_revision: sha256:target-source-revision
    original_utf8_bytes: 12000
    selected_utf8_bytes: 12000
    compression:
      mode: none

  - source_id: project:Assets/Settings/Debug/CameraDebugWindow.cs
    role: direct_dependency
    source_revision: sha256:dependency-revision
    original_utf8_bytes: 8000
    selected_utf8_bytes: 4200
    compression:
      mode: lossless_excerpt
      selected_ranges:
        - L1-L110
```

`Context Pack / Task Contract / Risk / Gate / Primary Skill`はRequestへ複製せず、Canonical YAMLからBuilderが解決します。

UnityAgent Repository内のPolicy、Context Pack、Skill、Task Contract、Repository ReferenceはBudget Engineが実ファイルから自動計測します。

Project SourceとExternal Referenceは実行環境依存のため、Request側でSource Revision付きObservationを渡します。Observationが無い場合は`0 byte`ではなく`unmeasured`です。

## Context Budget

Budget Contract:

```text
.ai/context-budget.yaml
```

Budget ReportはContext Manifestの`budget`へ入ります。

```yaml
budget:
  contract: .ai/context-budget.yaml
  profile: tight
  estimator:
    id: utf8-bytes-conservative-v1
    exact_model_tokenizer: false
  retrieval:
    selected_utf8_bytes: 42000
  context:
    estimated_tokens: 14000
    soft_estimated_tokens: 24000
    hard_estimated_tokens: 32768
  compression:
    applied: false
    saved_utf8_bytes: 0
  decision: within_budget
  blocking_reasons: []
```

`estimated_tokens`はModel Providerの正確なToken数ではありません。

```text
estimated_tokens = ceil(selected_utf8_bytes / 3)
```

Provider Tokenizerで正確な数を取得した場合は別Evidenceとして追加できますが、Tokenizer名なしで`exact`と呼びません。

### Budget decision

- `within_budget`: 必要Sourceが計測済みでSoft Limit以下
- `compression_required`: Hard Limit内だがSoft Limit超過
- `unmeasured`: 必須Project / External Observation不足
- `blocked`: Hard Limit、Artifact数、External Fetch数、Expansion Hop等を超過

Mutation Taskでは`within_budget`以外を許可しません。

## Context Compression

CompressionはCanonical Sourceを書き換えません。今回のSelected Contextだけを縮小します。

### `lossless_excerpt`

Source本文は変えず、必要Rangeだけ選択します。

```yaml
compression:
  mode: lossless_excerpt
  selected_ranges:
    - L120-L260
```

Target Source、Direct Dependency、Required / Conditional Contextなどに使用できます。Source RevisionとRangeを必ず残します。

### `semantic_summary`

Knowledge / Background Reference / Previous Failure summaryだけに使用します。

```yaml
compression:
  mode: semantic_summary
  summary_revision: sha256:summary-result
```

User Policy、Context Pack、Primary Skill、Task Contract、Project FactへSemantic Summaryを適用しません。

Soft Limit超過時はBudget Reportの`compression.candidates`を使って縮小候補を確認し、圧縮後に必ず再計測します。

Hard Limitを満たせない場合、Required Contextを黙って削除せず`blocked`として停止します。

## Project Fact freshness

Project Factは値だけでは不十分です。`source_kind`、`source_path`、`revision`、観測Attempt、Freshnessを必ず持たせます。

`freshness.status`:

- `current`: 現Attemptで現在性を確認済み
- `stale`: 過去の観測値。現在値としては使用しない
- `unknown`: 現在性を確認できない

`current`の場合、`freshness.checked_at_attempt`は現在のManifest Attemptと一致する必要があります。

## Evidence

```bash
python Tools/ContextManifest/record_manifest_evidence.py \
  --manifest Artifacts/ContextManifests/camera-far-clip-fix-a1.yaml \
  --gate compile \
  --status passed \
  --evidence-id compile-a1 \
  --reason runtime_evidence \
  --source-path ValidationResults/compile-a1.txt
```

`unavailable`の場合は残検証を必ず記録します。

```bash
python Tools/ContextManifest/record_manifest_evidence.py \
  --manifest Artifacts/ContextManifests/camera-far-clip-fix-a1.yaml \
  --gate compile \
  --status unavailable \
  --evidence-id compile-a1 \
  --reason runtime_evidence \
  --remaining-validation "Run Unity compile when the environment becomes available."
```

`unavailable`はPASSでもFAILでもありません。

## Retry

Retryするかどうかの判断は`DarumaPPAP/Unity-Graph-Engineering`が所有します。

UnityAgentはPrevious Manifestを受け取った場合だけ、次AttemptのManifestを生成します。

```bash
python Tools/ContextManifest/build_context_manifest.py \
  --request Tests/ContextManifest/requests/csharp-local-fix-retry.yaml \
  --previous Artifacts/ContextManifests/golden-csharp-local-fix-a1.yaml
```

次AttemptへコピーするのはPrevious Manifest全体ではなく、Previous Manifest ID / Attempt / Failure Reason / Evidence IDの要約です。

**Project Factは暗黙コピーしません。** 同一revisionのFactをRetryで`current`として使う場合も、Request側で明示的に再提示し、現在Attemptで再検証して`checked_at_attempt`を更新します。

Budget Observationも前Attemptの値を暗黙に現在値扱いしません。Project Sourceが変わった場合は`source_revision`とbyte計測を更新します。

## Validation

Context Manifest Runtime:

```bash
python Tools/ContextManifest/validate_context_manifest.py
```

Context Budget Runtime:

```bash
python Tools/ContextBudget/validate_context_budget.py
```

UnityAgent全体:

```bash
python Tools/validate_all.py
```

GitHub Actionsが利用できない期間も`Tools/validate_all.py`をCanonicalな代替検証入口として使用できます。

## Graph projection

```bash
python Tools/ContextManifest/project_execution_graph.py \
  --manifest Artifacts/ContextManifests/camera-far-clip-fix-a1.yaml \
  --output Artifacts/ContextManifests/camera-far-clip-fix-a1.graph.yaml
```

Graphでは`external_reference`をローカル`source`と分け、`context_include`は`includes_context`、`route_handoff`は`hands-off-to`として投影します。

Context Budget ReportはExecution Traceの計測情報であり、GraphからCanonical Budget Contractを逆更新しません。

Graphは`.ai/graph-contract.yaml`に従うExecution Viewです。Node/Edgeは表示・解析用であり、Canonical YAMLの編集入口ではありません。
