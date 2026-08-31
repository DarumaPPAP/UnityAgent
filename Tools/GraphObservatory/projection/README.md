# Graph Observatory 実データProjection Layer

## 目的

UnityAgentのCanonical Dataを、読み取り専用のGraph Observatory Projectionへ変換します。

Source of Truthとの関係:

```text
Policy / Orchestration / Context / Runtime / Persistence / Eval
                         ↓
                   Projection Layer
                         ↓
                    Graph Artifact
                         ↓
                      Visualizer
```

このLayerはRead-onlyであり、Canonical Configurationを変更しません。

## Projection対象

現行実装済みのProjectionと、旧または未完成のProjectionを区別します。`Tools/GraphObservatory/build.py` が直接公開するViewだけを現在サポートするSurfaceとして扱います。

候補Surface:

- Context Graph
- Harness / Verification Graph
- Execution Graph
- Regression Graph

## ルール

- 現行Canonical Pathから読み込む
- 旧dot-ai AuthorityをCurrent Inputへ戻さない
- Provenanceを保持する
- Node ID / Typed Relationを可能な範囲で保持する
- 不明な情報を推測で補完しない
- Graph Outputは派生ViewでありSource of Truthではない
- Graph EditingからCanonical YAMLをMutationしない
- Empty GraphによってSchema / Pathの不一致を隠さない

## 出力

生成Artifactは `Artifacts/GraphObservatory/` 配下へ出力し、Production State / Evidence / Frozen Baselineの代替Source of Truthとして使用しません。
