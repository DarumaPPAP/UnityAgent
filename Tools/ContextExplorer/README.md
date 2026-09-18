# UnityAgent Context Explorer

`Tools/ContextExplorer/`は、人間がCanonical Context Contractを保守・確認するためのStatic / Offline / Read-only Viewerです。Production Authorityは`Policy/`、`Orchestration/`、`Context/`、`Runtime/`、`Persistence/`、`Operations/`、`Eval/`にあります。

## 生成する表示

1. `Context/Packs/*.yaml`から決定的に`context-map.json`を作成します。
2. UnityAgentのContextを7つのHuman Conceptへ投影し、Canonical Source Pathへ辿れるようにします。
3. RelationとProvenanceを外部通信なしで表示します。
4. 選択Contextの`metadata.related`に記録されたRelationだけを決定的にOne-hop表示します。

Context ExplorerはRelationを推測せず、Route、Policy、Runtime State、Provider、SubAgent eligibilityを判定しません。UnitySubAgentHubのManifestを読み込むResolverでもありません。

## Build / Validate

```powershell
python .\Tools\ContextExplorer\build.py --check
python .\Tools\ContextExplorer\validate.py
python .\Tools\ContextExplorer\build.py
```

Default Artifact: `Artifacts/ContextExplorer/context-map.json`

Viewerの制約はStatic / Offline / Read-onlyです。YAML編集、Save / Apply、Agent Control、Routing / Dispatch / Approval / Execution、External CDN、Browser Storage、任意のRelation推測は行いません。描画には`textContent`を使います。

Context Mapは表示用のProjectionです。旧`Context Graph` / `__CONTEXT_GRAPH__`の語彙や汎用Graph Engineを復活させません。
