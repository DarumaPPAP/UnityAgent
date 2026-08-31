# Graph Observatory Builder

Graph ObservatoryのBuilderは、現在のUnityAgent Canonical Contractから派生Graph Artifactを生成します。

## 処理の流れ

```text
Policy / Orchestration / Context / Runtime / Persistence / Eval
                         ↓
                  Graph Builder
                         ↓
                派生JSON Artifact
                         ↓
              Graph Observatory UI
```

Context Viewの現在の入力は `Context/Packs/*.yaml` です。旧dot-ai SourceをCurrent Inputとして使用しません。

## ルール

- Graph Outputは派生Viewとして扱う
- Canonical ContractをSource of Truthとする
- Node / EdgeにProvenanceを保持する
- 不明なRelationを推測で補完しない
- VisualizationからCanonical Contractを直接Mutationしない
- Empty Graphになった場合、Canonical Inputが存在しないと即断せず、Input Path / Schemaの不一致を確認する
