# UnityAgent Context Explorer

`Tools/GraphObservatory/` は、canonical UnityAgent contractからread-only projectionを生成するsupporting toolです。

Production authorityは `Policy/`、`Orchestration/`、`Context/`、`Runtime/`、`Persistence/`、`Operations/`、`Eval/` にあり、このtoolのgraph出力はderived viewにすぎません。

## Current input

Context viewは `Context/Packs/*.yaml` のcurrent metadataを読みます。Phase 8で削除されたlegacy `.ai` treeをcurrent sourceとして使用しません。

## Build and validate

```powershell
python .\Tools\GraphObservatory\build.py --view context --check
python .\Tools\GraphObservatory\build.py --view context --bundle .\Artifacts\GraphObservatory\ContextExplorer
```

Bundleはstatic / offlineで、edit、save、apply、agent-control、canonical YAML write surfaceを持ちません。

## Boundary

- projectionはsource path / hash等のprovenanceを保持する
- missing relationを推測で埋めない
- Graph UIからcanonical contractを変更しない
- Graph outputをRoute、State、Evidence、Eval、Frozen Baselineのtruthとして扱わない
- legacy builder/projection codeが残る場合もcompatibility authorityとしてProduction bootstrapへ接続しない

Current contractの詳細は `docs/phase8-graph-observatory-spec.md` を参照してください。
