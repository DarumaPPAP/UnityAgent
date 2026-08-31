# Graph Observatory テスト

Graph Observatoryには、現在サポートしているContext Explorerの回帰テストと、将来の修復候補を表す旧Foundation Contract Testが混在しています。両者を同じ意味では扱いません。

## 現在サポートしている確認項目

Context Explorerの現行Canonical Input / Provenance / Read-only Surfaceは次で検証します。

```powershell
python .\Tools\GraphObservatory\validate_context_explorer.py
python -m unittest Tests.GraphObservatory.test_context_explorer_projection
python -m unittest Tests.GraphObservatory.test_context_explorer_security
```

`test_context_explorer_projection.py` は `Context/Packs/` から空ではないProjectionを生成し、旧Input Pathへ戻らないことを確認します。

## 旧Foundation Contract / 将来候補

`test_graph_observatory_foundation_contract.py` などの一部は、Graph Observatoryの未統合Viewや将来のFoundation Requirementを記録するRepair-oriented Contractです。

これらは現在のProduction品質判定ではありません。全件を `Tools/validate_all.py` へ無条件に接続せず、未実装Requirementを意図的に保持するTestは、採用するAuthority BoundaryをレビューしてからCanonical CIへ昇格します。

## 境界

- 現行Context ExplorerのRegressionはGreenであること
- 旧または将来向けContractのFailureをAgent品質Regressionへ変換しないこと
- Graph Observatoryを第二のRouting / Execution / Eval Authorityにしないこと
- 現行Canonical Pathを使用し、旧Compatibility SourceへFallbackしないこと
