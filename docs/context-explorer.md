# Context Explorer

UnityAgentのCanonical Contractから読み取り専用のHuman Architecture / Context Mapを生成し、Context RelationとProvenanceを人間が短時間で理解・保守できるようにする **Human Maintenance Viewer** です。

Context ExplorerはProduction Execution、Route Selection、Policy編集、Regression判定のAuthorityではありません。

## 正本となる入力

```text
Policy/
Orchestration/
Context/
Runtime/
Persistence/
Operations/
Eval/
        │
        ├─ Human Architecture Projection
        └─ Context/Packs Metadata Parser
                │
                ▼
        read-only Derived Context Map
                │
                ├─ Artifacts/ContextExplorer/context-map.json
                └─ Artifacts/ContextExplorer/viewer/
```

Human Architecture ProjectionはCanonical Repository Pathの存在を検証しながら、初見向けの7概念へMachine Architectureを投影します。

```text
Rules -> Planner -> Knowledge -> Executor -> Evidence -> Memory / Quality
```

Context Mapは `Context/Packs/*.yaml` のMetadataだけを読み取ります。Relationは `metadata.related` に明示された既存Context間の関係だけを表示し、欠落Relationを推測で補いません。

## Context Metadata Schema

生成物は [`../Tools/ContextExplorer/schema/context-map.schema.json`](../Tools/ContextExplorer/schema/context-map.schema.json) に従います。

各Context Nodeは最低限次のProvenanceを保持します。

- canonical `source_path`
- source file SHA-256 `source_hash`
- `primary_skill`
- Purpose / Decision / Forbidden / Related metadata

Map自体には `read_only: true` を固定し、Runtime Stateや永続Evidenceとして扱いません。

## Viewer Surface

### Overview

- 3分以内で理解するGuided Animation
- THINK -> ACT -> VERIFYのMental Model
- 7 Human Concepts
- MyResourceCenter / UnityAgent / Unity Projectのシステム境界
- Human Concept -> Machine Area -> Source PathのProgressive Disclosure

### Task Demo

`Shaderを最適化して` を代表例として、実依頼が次の順で進むことを説明します。

```text
Rules -> Planner -> Knowledge -> Executor -> Evidence -> Quality
```

Task DemoはExecution Traceではなく、Architecture理解のための説明Scenarioです。

### Explore

- Context Pack検索
- Priority filter
- Relation traversal
- Purpose / Decision / Forbidden / Related表示
- Provenance Source Path表示・Copy

## Human Architecture Contract

| Human Concept | Primary Machine Mapping |
| --- | --- |
| Rules | `Policy/` |
| Planner | `Orchestration/`、必要時のみGraph / Loop |
| Knowledge | `Context/`、`.agents/skills/`、MyResourceCenter Snapshot |
| Executor | `Runtime/`、Provider / Harness |
| Evidence | `Runtime/EvidenceCapture/` |
| Memory | `Persistence/` |
| Quality | `Eval/`、`Operations/` |

GraphはPlanner内部でTask complexityに応じて利用されるStrategyであり、UnityAgent全体のRuntime Engineではありません。

## Frontend Safety / Accessibility

BundleはStatic / Offline / Read-onlyです。

禁止:

- `fetch()` / `XMLHttpRequest`
- Canonical FileへのSave / Apply
- Browser StorageへのState persist
- External CDN依存
- `innerHTML`を使ったProjected Data描画

必須:

- `textContent`ベースのDOM構築
- Keyboard操作可能なControls
- `prefers-reduced-motion`で自動Animationを抑制
- Source PathはCopyのみで、ExplorerからMutationしない

## Build / Validation

```powershell
python .\Tools\ContextExplorer\build.py --check
python .\Tools\ContextExplorer\validate.py
python .\Tools\validate_all.py
```

Bundle生成:

```powershell
python .\Tools\ContextExplorer\build.py --bundle .\Artifacts\ContextExplorer\viewer
```

## #32 Migration Result

旧`Tools/GraphObservatory/`にあったgeneric graph builder、generic projection runner、graph schema、expansion gateは削除しました。

Context Explorerは `Context/Packs` -> `ContextMap` -> Static Viewer の一方向Projectionだけを所有します。Context / Harness / LoopのCanonical Authorityを奪いません。

## 非目標

- 第二のRouting System / Runtime Graph Engineを作ること
- Graph UIからCanonical YAMLを変更すること
- GraphだけでRoot CauseやRegressionを確定すること
- Frozen BaselineやBaseline Comparatorを代替すること
- MyResourceCenterをUnityAgent内部Runtimeとして扱うこと

Human-facing Mental Modelの詳細は [`architecture/three-minute-architecture.md`](architecture/three-minute-architecture.md) を参照してください。
