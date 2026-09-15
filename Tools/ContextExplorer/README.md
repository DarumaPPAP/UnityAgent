# UnityAgent Context Explorer

`Tools/ContextExplorer/` は、CanonicalなUnityAgent Contractを人間が保守・確認するための **read-only Human Maintenance Viewer** です。

Context Explorer自身はRouting、Execution、Policy、RegressionのAuthorityを持ちません。Production Authorityは引き続き `Policy/`、`Orchestration/`、`Context/`、`Runtime/`、`Persistence/`、`Operations/`、`Eval/` にあります。

## 役割

1. `Context/Packs/*.yaml` を決定的に読み取り、`context-map.json` を生成する。
2. UnityAgentを7つのHuman Conceptへ投影し、Canonical Source Pathまでdrill-downできるようにする。
3. Static / Offline / Read-only HTML ViewerとしてContext relationとProvenanceを表示する。
4. 選択Contextについて、Canonical `metadata.related` に存在するRelationだけを **deterministic one-hop projection** として表示する。

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
- Routing / Dispatch / Approval / ExecutionのAuthority
- `fetch()` / `XMLHttpRequest` / WebSocket / EventSourceによる外部通信
- Browser StorageへのState persist
- External CDN依存
- Projected Dataを`innerHTML`で描画
- Force-directed layout / physics / generic graph runtime

Frontendは`textContent`を使い、Source PathはCopyだけを提供します。

## Visualization Contract

Viewer内部の正規語彙は **Context Map** です。旧 `Context Graph` / `__CONTEXT_GRAPH__` は使用しません。

選択ContextのRelation表示は次だけを行います。

- `metadata.related` 由来の既存Edgeだけを表示
- incoming / outgoingを `←` / `→` で区別
- 1-hopだけを決定的順序で表示
- Relation先ContextへのNavigationだけを許可

Visualizationは追加のRelationを推測せず、Route、Loop、Runtime State、Execution結果を計算しません。

## Graphの扱い

旧`GraphObservatory`に存在したgeneric graph builder、projection runner、expansion gateは削除しました。Context Explorerが保持するNode / Relationは **表示用Context Map** に限定されます。

`Orchestration/Graph` はPlanner内のTopology責務として独立したままです。Context Explorerはそれをimport・execute・mutateしません。Graph / LoopはTask complexityに応じて必要時だけ使うStrategyであり、UnityAgent Runtime全体をGraph Engineとして扱いません。
