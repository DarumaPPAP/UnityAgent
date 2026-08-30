# Graph Observatory Tests

Graph Observatoryには、現在サポートするContext Explorerの回帰テストと、将来修復候補を表すlegacy foundation contract testsが混在しています。両者を同じ意味で扱いません。

## Current supported checks

Context Explorerのcurrent canonical input / provenance / read-only surfaceは次で検証します。

```powershell
python .\Tools\GraphObservatory\validate_context_explorer.py
python -m unittest Tests.GraphObservatory.test_context_explorer_projection
python -m unittest Tests.GraphObservatory.test_context_explorer_security
```

`test_context_explorer_projection.py` は `Context/Packs/` からnon-empty projectionを生成し、旧input pathへ戻らないことを確認します。

## Legacy / future foundation contracts

`test_graph_observatory_foundation_contract.py` 等の一部は、Graph Observatoryの未統合viewや将来foundation requirementを記録するrepair-oriented contractです。

それらは現在のUnityAgent Production quality gateではなく、全件を `Tools/validate_all.py` へ無条件接続しません。未実装requirementを意図的に保持するテストは、採用するPhaseとAuthority boundaryをレビューしてからcanonical CIへ昇格します。

## Boundary

- Current Context Explorer regressionはgreenであること
- Legacy/future contractのfailureをPhase 9/10 Agent quality regressionへ変換しないこと
- Graph Observatoryをsecond routing / execution / Eval authorityにしないこと
- Current canonical pathsを使い、legacy compatibility sourceへfallbackしないこと
