# RAG Module

`RAG/` は UnityAgent の独立した Retrieval-Augmented Grounding boundary です。

## Responsibility

- Query normalization、classification、explicit metadata extraction
- MyResourceCenter Search Index と Persistence Memory の read-only adapter
- deterministic local lexical retrieval、filtering、ranking、RRF seam
- Candidate の provenance-preserving Grounding Bundle
- bounded output、source failure、backend failure、retrieval trace

RAG は Route / Provider / Tool / Runtime の選択を行わず、Persistence Memory や Evidence に書き込みません。回答の最終的な品質判定も Eval の責務です。

## Sources and ownership

MyResourceCenter の `catalog/search-index.json` 相当の再生成可能 Index を読みます。Index は Evidence の投影であり、元の Drive 資料を複製しません。`RAG/Adapters/my_resource_center` は read と normalization だけを行います。

Persistence が durable Memory の正本を所有します。`RAG/Adapters/memory` は `MemoryStore.list_accessible` のみを呼び、`put` / `promote` / projection cache write は行いません。

既存 `Context/Retrieval/Knowledge` は staged migration 中の互換入力として `RAG/Adapters/local_knowledge.py` から読みます。新しい retrieval authority はこの top-level module です。

## Context handoff

`retrieve_knowledge(...)` は `grounding_bundle` と `context_projection` を返します。Context が受け取るのは `rag://grounding/...` と source reference で、検索・選択の結果を出典なしの文字列へ変換しません。Context はその後の selection、budget、compression、materialization を所有します。

## MVP and extension boundary

MVP backend は外部 DB に依存しない `local-lexical-v1` です。Dense、hybrid、Qdrant は optional な後続 adapter の差し込み点であり、未構成の外部 index を local backend 成功として隠す silent fallback は行いません。

Golden dataset と受入閾値は `Eval/Datasets/Retrieval/`、runner は `Eval/Retrieval/run_retrieval_eval.py` です。
