# UnityAgent Context Explorer

`Tools/ContextExplorer/` は、CanonicalなUnityAgent Contractを人間が保守・確認するための **read-only Human Maintenance Viewer** です。

Context Explorer自身はRouting、Execution、Policy、RegressionのAuthorityを持ちません。Production Authorityは引き続き `Policy/`、`Orchestration/`、`Context/`、`Runtime/`、`Persistence/`、`Operations/`、`Eval/` にあります。

## 役割

1. `Context/Packs/*.yaml` を決定的に読み取り、`context-map.json` を生成する。
2. UnityAgentを7つのHuman Conceptへ投影し、Canonical Source Pathまでdrill-downできるようにする。
3. Static / Offline / Read-only HTML ViewerとしてContext relationとProvenanceを表示する。

```text
Canonical Contract
  Policy / Orchestration / Context / Runtime / Persistence / Operations / Eval
        │
        ├─ Human Architecture Projection
        └─ Context Pack Parser
                │
                ▼
          Context Map
         Derived View only
                │
                ▼
      Offline Context Explorer
```

## Source of Truth

Context relationの正本は `Context/Packs/*.yaml` の `metadata.related` です。ExplorerはRelationを推測・補完しません。NodeにはSource PathとSHA-256をProvenanceとして保持します。

生成ArtifactのSchemaは [`schema/context-map.schema.json`](schema/context-map.schema.json) です。

## Build / Validate

```powershell
python .\Tools\ContextExplorer\build.py --check
python .\Tools\ContextExplorer\validate.py
```

Mapを生成:

```powershell
python .\Tools\ContextExplorer\build.py
```

既定出力:

```text
Artifacts/ContextExplorer/context-map.json
```

Offline Viewerを生成:

```powershell
python .\Tools\ContextExplorer\build.py --bundle .\Artifacts\ContextExplorer\viewer
```

## Read-only Contract

Context Explorerでは次を禁止します。

- Canonical YAML / Policy / Runtime Stateの編集
- Save / Apply / Agent Control
- `fetch()` / `XMLHttpRequest`による外部通信
- Browser StorageへのState persist
- External CDN依存
- Projected Dataを`innerHTML`で描画

Frontendは`textContent`を使い、Source PathはCopyだけを提供します。

## Graphの扱い

旧`GraphObservatory`に存在したgeneric graph builder、projection runner、expansion gateは削除しました。Context Explorerが保持するNode / Relationは **表示用Context Map** に限定されます。

UnityAgent Runtime全体をGraph Engineとして扱いません。Graph / Loopは引き続きPlannerがTask complexityに応じて必要時だけ使うStrategyです。
