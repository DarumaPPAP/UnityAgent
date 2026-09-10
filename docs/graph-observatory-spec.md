# Graph Observatory / Architecture & Context Explorer

UnityAgentのCanonical Contractから読み取り専用のHuman Architecture / Context Projectionを生成し、Agent DecisionのProvenanceやContext Relationを人間が短時間で理解・確認できるようにするための補助仕様です。

Graph ObservatoryはProduction Execution、Route Selection、Policy編集、Regression判定のAuthorityではありません。

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
        └─ Context Pack Projection
                │
                ▼
        read-only Derived View
                │
                ▼
Artifacts/GraphObservatory/ContextExplorer
```

Human Architecture ProjectionはCanonical Repository Pathの存在を検証しながら、初見向けの7概念へMachine Architectureを投影します。

```text
Rules -> Planner -> Knowledge -> Executor -> Evidence -> Memory / Quality
```

Context Projectionは `Context/Packs/*.yaml` のMetadataを読み取り専用でProjectionします。single-repo cutover前の旧dot-ai設定TreeはCurrent Inputとして使用しません。

## 実装済みView

現在のStatic HTML Bundleは次の3 Surfaceを持ちます。

### Overview

- 3分以内で理解するGuided Animation
- THINK -> ACT -> VERIFYの30秒Mental Model
- 7 Human Concepts
- MyResourceCenter / UnityAgent / Unity Projectのシステム境界
- Human Concept -> Machine Area -> Source PathのProgressive Disclosure

### Task Demo

`Shaderを最適化して` を代表例として、実依頼が次の順で進むことをアニメーション表示します。

```text
Rules -> Planner -> Knowledge -> Executor -> Evidence -> Quality
```

Task DemoはExecution Traceではありません。Architecture理解のための説明用Scenarioです。

### Explore

- Context Pack検索
- Priority filter
- Relation traversal
- Purpose / Decision / Forbidden / Related表示
- Provenance Source Path表示・Copy

## Human Architecture Contract

Human-facing UIは次の7概念をPrimary Navigation Modelとします。

| Human Concept | Primary Machine Mapping |
| --- | --- |
| Rules | `Policy/` |
| Planner | `Orchestration/`、必要時のみGraph / Loop |
| Knowledge | `Context/`、`.agents/skills/`、MyResourceCenter Snapshot |
| Executor | `Runtime/`、Provider / Harness |
| Evidence | `Runtime/EvidenceCapture/` |
| Memory | `Persistence/` |
| Quality | `Eval/`、`Operations/` |

Machine Directory名を削除・改名するためのContractではありません。人間に同じ抽象度で全Subsystemを並べないためのInformation Architectureです。

GraphはPlanner内部でTask complexityに応じて利用されるStrategyとして表示し、UnityAgent全体のRuntime Engineとして扱いません。

## Progressive Disclosure

```text
Animation
  -> Human Concept
      -> Machine Subsystem
          -> Repository Source Path
```

初見ユーザーへFile Treeを直接提示しないことを原則とします。

## 設計原則

- Graph / Human MapはCanonical Sourceから生成するDerived Viewとする。
- VisualizerはPolicy / Orchestration / Runtime / Eval Contractを直接編集しない。
- Node / Edgeは可能な限りSource Path / Hash等のProvenanceを保持する。
- Human ArchitectureのSource PathはBuild時に存在確認する。
- Missing Relationを推測で補完しない。
- Empty Projectionを正常なCanonical Graphと誤認しない。
- Graph OutputはDurable State / Evidence / Baselineの代替Truthではない。
- MyResourceCenterをUnityAgent内部Runtimeとして表現しない。

## Frontend Safety / Accessibility

BundleはStatic / Offline / Read-onlyです。

禁止:

- `fetch()` / `XMLHttpRequest`
- Canonical FileへのSave / Apply
- Browser StorageへのState persist
- External CDN依存
- `innerHTML`を使ったProjected Data描画

必須:

- Text ContentベースのDOM構築
- Keyboard操作可能なControls
- `prefers-reduced-motion`で自動Animationを抑制
- Source PathはCopyのみで、ExplorerからMutationしない

## Build

Projection Validation:

```powershell
python .\Tools\GraphObservatory\build.py --view context --check
python .\Tools\GraphObservatory\validate_context_explorer.py
```

Bundle生成:

```powershell
python .\Tools\GraphObservatory\build.py --view context --bundle .\Artifacts\GraphObservatory\ContextExplorer
```

## 非目標

- 第二のRouting Systemを作ること
- Legacy Compatibility Authorityを維持すること
- Graph UIからCanonical YAMLを直接変更すること
- GraphだけでRoot CauseやRegressionを確定すること
- Frozen BaselineやBaseline Comparatorを代替すること
- Architecture AnimationをProduction Execution Traceと誤認させること

Human-facing Mental Modelの詳細は [`architecture/three-minute-architecture.md`](architecture/three-minute-architecture.md) を参照してください。
