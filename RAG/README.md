# RAG Module

`RAG/` は UnityAgent の独立した Retrieval-Augmented Grounding boundary です。

## Responsibility

- Query normalization、classification、explicit metadata extraction
- MyResourceCenter Search Index と Persistence Memory の read-only adapter
- deterministic local lexical / dense retrieval、metadata filtering、RRF / weighted-RRF ranking、optional reranking
- optional Qdrant dense+sparse hybrid adapter、collection/index provisioning、explicit fallback diagnostics
- bounded query planning と Knowledge relation expansion（Orchestration graphとは別物）
- Candidate の provenance-preserving Grounding Bundle
- bounded output、source failure、backend failure、retrieval trace

RAG は Route / Provider / Tool / Runtime の選択を行わず、Persistence Memory や Evidence に書き込みません。回答の最終的な品質判定も Eval の責務です。

## Sources and ownership

MyResourceCenter の `catalog/search-index.json` 相当の再生成可能 Index を読みます。Index は Evidence の投影であり、元の Drive 資料を複製しません。`RAG/Adapters/my_resource_center` は read と normalization だけを行います。

Persistence が durable Memory の正本を所有します。`RAG/Adapters/memory` は `MemoryStore.list_accessible` のみを呼び、`put` / `promote` / projection cache write は行いません。

既存 `Context/Retrieval/Knowledge` は staged migration 中の互換入力として `RAG/Adapters/local_knowledge.py` から読みます。新しい retrieval authority はこの top-level module です。

## Context handoff

`retrieve_knowledge(...)` は `grounding_bundle` と `context_projection` を返します。Context が受け取るのは `rag://grounding/...` と source reference で、検索・選択の結果を出典なしの文字列へ変換しません。Context はその後の selection、budget、compression、materialization を所有します。

## Backend and ranking boundary

MVP backend は外部 DB に依存しない `local-lexical-v1` です。`LocalDenseBackend` は依存のない再現可能な baseline、`HybridRetriever` は lexical / dense の RRF seam、`TechnicalReranker` は候補集合だけを並べ替える bounded reranker です。重みと revision は `RAG/Ranking/ranking-config.yaml` で version 管理し、最終的な品質判定は Eval が行います。

Qdrant は `RAG/Adapters/qdrant/` の optional adapter です。`QdrantBackend` は named dense / sparse prefetch、同一 payload filter、server-side RRF を使い、`QdrantCollectionManager` が collection・payload index・upsert を明示的に担当します。未構成／timeout／unavailable の外部 backend は成功に見せず、fallback は呼び出し側が明示的に許可した場合だけ `partial` として返します。

## Bounded planning and graph expansion

`build_query_plan` は最大4件以内の決定的な subquery を作り、`execute_query_plan` は worker 数・candidate 数を制限し、成功／失敗を個別 trace に残します。`KnowledgeGraphExpander` が扱うのは Knowledge の `related` / `supports` / `depends_on` 等の明示 relation だけです。hop、node budget、relation provenance を必須にし、Runtime / Orchestration の制御グラフへ流用しません。

## Evaluation and Memory promotion

Golden dataset と受入閾値は `Eval/Datasets/Retrieval/`、単一 baseline runner は `Eval/Retrieval/run_retrieval_eval.py`、variant 比較は `Eval/Retrieval/run_retrieval_variants.py` です。variant runner は lexical、dense、equal-RRF、weighted-RRF、rerank を同じ20ケースで比較し、Recall / MRR / provenance / no-answer false-positive / p50-p95 latency / failure attribution を出力します。

PASS 評価から作るのは `RAG/Feedback/experience_feedback.py` の immutable proposal だけです。永続化は `Persistence/Memory/promotion_writer.py` が `MemoryStore` のみを通して行い、review・revision・conflict・Human Gateを評価します。RAG は次回検索で `MemoryStore` の read-only adapter を使うだけで、Memory の正本を直接変更しません。
