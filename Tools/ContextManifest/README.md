# Context Manifest Runtime

Context Manifest Runtimeは、1回のUnityAgent Task Attemptで実際に選択されたTyped Context / Harness / Project Fact / Evidenceを記録するための実行トレースです。

## Source of truth

- Policy / Context / Harnessの正本は`.ai/`配下のCanonical YAMLです。
- Context PackはTyped Context v3を使用します。
- Context Manifest v3.1は正本を置き換えません。
- Execution GraphはContext Manifestから生成されるDerived Viewです。
- Generated Manifest / GraphからCanonical PolicyやHarnessを逆更新しません。

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
Worker / Tool execution
  ↓
Evidence Recorder
  ↓
passed / failed / unavailable
  ↓
Execution Graph Projection
```

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

Graphも同時に生成する場合:

```bash
python Tools/ContextManifest/build_context_manifest.py \
  --request Tests/ContextManifest/requests/csharp-local-fix.yaml \
  --graph-output Artifacts/ContextManifests/golden-csharp-local-fix-a1.graph.yaml
```

## Runtime request

Builderへ渡すRequestはManifest全体ではなく、Task固有の確定情報だけを持ちます。

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
```

`Context Pack / Task Contract / Risk / Gate / Primary Skill`はRequestへ複製せず、Canonical YAMLからBuilderが解決します。

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

## Validation

単体Manifest:

```bash
python Tools/ContextManifest/validate_context_manifest.py \
  Artifacts/ContextManifests/camera-far-clip-fix-a1.yaml
```

Runtime自己回帰テスト:

```bash
python Tools/ContextManifest/validate_context_manifest.py
```

UnityAgent全体のローカル検証:

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

Graphは`.ai/graph-contract.yaml`に従うExecution Viewです。Node/Edgeは表示・解析用であり、Canonical YAMLの編集入口ではありません。
