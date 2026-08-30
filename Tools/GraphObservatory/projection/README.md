# Graph Observatory Real Data Projection Layer

## Purpose

UnityAgent canonical dataをread-only Graph Observatory projectionへ変換する。

Source of Truth:

```text
Policy / Orchestration / Context / Runtime / Persistence / Eval
                         ↓
                  Projection Layer
                         ↓
                   Graph Artifact
                         ↓
                     Visualizer
```

このLayerはread-onlyであり、canonical configurationを変更しない。

## Projection targets

現行実装済みprojectionとlegacy/incomplete projectionを区別する。`Tools/GraphObservatory/build.py` が直接公開するviewだけをcurrent supported surfaceとして扱う。

候補surface:

- Context Graph
- Harness / Verification Graph
- Execution Graph
- Regression Graph

## Rules

- current canonical pathから読む
- legacy dot-ai authorityをcurrent inputへ戻さない
- provenanceを保持する
- node ID / typed relationを可能な範囲で保持する
- Missing informationを推測で補わない
- Graph outputはderived viewでありsource of truthではない
- Graph editingからcanonical YAMLをmutationしない
- Empty graphでschema/path mismatchを隠さない

## Output

Generated artifactsは `Artifacts/GraphObservatory/` 配下へ出力し、Production State / Evidence / Frozen Baselineの代替truthとして使用しない。
