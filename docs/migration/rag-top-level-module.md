# RAG Top-Level Module Migration Record

この文書は RAG 導入の移行記録です。現在の責務は `RAG/README.md` と `docs/architecture/architecture.md` を参照します。

## Boundary

`RAG/` が検索、ranking、Grounding、provenance、retrieval diagnosticsを所有します。Route / Provider / Runtimeの選択は既存のOrchestration / Runtimeに残り、durable Memory / Evidenceの正本はPersistenceに残ります。

## Staged compatibility

既存 `Context/Retrieval/Knowledge` は移行期間中の静的Knowledge入力として `RAG/Adapters/local_knowledge.py` から読みます。既存 `Context/Retrieval/Memory/project_memory.py` の公開read APIも保持し、RAGのMemory adapterはPersistenceのread APIだけを呼びます。

## Handoff invariant

RAGは出典を削除せず `rag://grounding/...` と source/evidence identityをContextへ渡します。Contextは参照を選択してbudget評価・圧縮・materializeし、RAGがContextやPersistenceへ直接書き込みません。

## Completed extension phases

Phase 4〜7 の実装は次の境界で追加されています。

- Phase 4: `RAG/Adapters/qdrant/` に optional REST adapter、named dense/sparse vector、BM25 sparse encoding、payload index、metadata filter、明示 fallbackを追加。
- Phase 5: versioned `RRFConfig`、weighted RRF、candidate-only reranker、variant evaluation と latency/failure attributionを追加。
- Phase 6: bounded deterministic query planner と Knowledge relation-only graph expansionを追加。hop/node budgetとrelation provenanceをtraceへ保存。
- Phase 7: PASS Evalからpromotion proposalを生成し、`Persistence.Memory.promotion_writer` がreview・revision・conflict・Human Gateを経てMemoryStoreへ一度だけ書き込む。RAG側からPersistence writeは行わない。

## Versioning

RAG contract revisionは `1.0`、local lexical backend revisionは `local-lexical-v1`、Qdrant hybrid revisionは `qdrant-hybrid-v1` としてtraceへ記録します。Ranking config、embedding、source index、Grounding bundle、Memory source revisionが変わった場合はContext / Definition driftまたはMemory conflictとして扱い、既存Frozen Baselineを自動更新しません。
