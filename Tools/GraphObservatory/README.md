# UnityAgent Context Explorer

`Tools/GraphObservatory/` は、CanonicalなUnityAgent Contractから読み取り専用Projectionを生成する補助ツールです。

Production Authorityは `Policy/`、`Orchestration/`、`Context/`、`Runtime/`、`Persistence/`、`Operations/`、`Eval/` にあります。このToolが生成するGraphは派生Viewであり、正本ではありません。

## 現在の入力

Context Viewは `Context/Packs/*.yaml` の現行Metadataを読みます。single-repo cutoverで廃止された旧dot-ai treeをCurrent Sourceとして使用しません。

## BuildとValidation

```powershell
python .\Tools\GraphObservatory\build.py --view context --check
python .\Tools\GraphObservatory\build.py --view context --bundle .\Artifacts\GraphObservatory\ContextExplorer
```

BundleはStatic / Offlineであり、Edit、Save、Apply、Agent Control、Canonical YAMLへのWrite Surfaceを持ちません。

## 境界

- ProjectionはSource Path / HashなどのProvenanceを保持する
- 不明なRelationを推測で埋めない
- Graph UIからCanonical Contractを変更しない
- Graph OutputをRoute、State、Evidence、Eval、Frozen BaselineのSource of Truthとして扱わない
- 旧Builder / Projection Codeが残る場合もCompatibility AuthorityとしてProduction Bootstrapへ接続しない

Current Contractの詳細は [`docs/graph-observatory-spec.md`](../../docs/graph-observatory-spec.md) を参照してください。
