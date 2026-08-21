# Context Manifest Runtime

Context Manifest Runtimeは、1回のUnityAgent Task Attemptで実際に選択されたContext / Harness / Evidenceを記録するための実行トレースです。

## Source of truth

- Policy / Context / Harnessの正本は`.ai/`配下のCanonical YAMLです。
- Context Manifestは正本を置き換えません。
- Execution GraphはContext Manifestから生成されるDerived Viewです。
- Generated Manifest / GraphからCanonical PolicyやHarnessを逆更新しません。

既定出力先は`.gitignore`対象の`Artifacts/ContextManifests/`です。

## Runtime flow

```text
Task Fingerprint
  ↓
Primary Route
  ↓
Context Manifest Builder
  ├─ Context Packを解決
  ├─ Primary Skillを解決
  ├─ Task Contractを解決
  ├─ Mutation Ruleを解決
  ├─ Risk Levelを解決
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
```

`Context Pack / Task Contract / Risk / Gate / Primary Skill`はRequestへ複製せず、Canonical YAMLからBuilderが解決します。

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

Graphは`.ai/graph-contract.yaml`に従うExecution Viewです。Node/Edgeは表示・解析用であり、Canonical YAMLの編集入口ではありません。
