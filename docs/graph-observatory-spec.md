# Graph Observatory / Context Explorer

UnityAgentのCanonical Contractから読み取り専用のGraph / Context Projectionを生成し、Agent DecisionのProvenanceやContext Relationを人間が確認できるようにするための補助仕様です。

Graph ObservatoryはProduction Execution、Route Selection、Policy編集、Regression判定のAuthorityではありません。

## 正本となる入力

```text
Policy/
Orchestration/
Context/
Runtime/
Persistence/
Eval/
        │
        ▼
read-only Graph / Context projection
        │
        ▼
Artifacts/GraphObservatory/**
        │
        ▼
Graph Observatory UI
```

現在のContext Explorerは主に `Context/Packs/*.yaml` のMetadataを読み取り専用でProjectionします。

single-repo cutover前の旧dot-ai設定Treeは廃止済みであり、Current Inputとして使用しません。

## View

長期的なView候補:

- Architecture View
- Context Explorer
- Task / Route Explorer
- Execution Trace
- Regression Dashboard

実装済み範囲と将来候補を混同しません。現在の `Tools/GraphObservatory/build.py` が直接サポートするViewだけを実装済みとして扱います。

## 設計原則

- Graph DataはCanonical Sourceから生成するDerived Viewとする。
- VisualizerはPolicy / Orchestration / Runtime / Eval Contractを直接編集しない。
- Node / Edgeは可能な限りSource Path / Hash等のProvenanceを保持する。
- Missing Relationを推測で補完しない。
- Empty Projectionを正常なCanonical Graphと誤認しない。
- Graph OutputはDurable State / Evidence / Baselineの代替Truthではない。

## Build

```powershell
python .\Tools\GraphObservatory\build.py --view context --check
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

## 来歴

Graph Observatoryはsingle-repo移行時に導入されました。現在は移行段階の番号ではなく、上記Canonical AuthorityとCurrent Contractだけを基準に運用します。
