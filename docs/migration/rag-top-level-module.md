# RAG Top-Level Module Migration Record

この文書は RAG 導入の移行記録です。現在の責務は `RAG/README.md` と `docs/architecture/architecture.md` を参照します。

## Boundary

`RAG/` が検索、ranking、Grounding、provenance、retrieval diagnosticsを所有します。Route / Provider / Runtimeの選択は既存のOrchestration / Runtimeに残り、durable Memory / Evidenceの正本はPersistenceに残ります。

## Staged compatibility

既存 `Context/Retrieval/Knowledge` は移行期間中の静的Knowledge入力として `RAG/Adapters/local_knowledge.py` から読みます。既存 `Context/Retrieval/Memory/project_memory.py` の公開read APIも保持し、RAGのMemory adapterはPersistenceのread APIだけを呼びます。

## Handoff invariant

RAGは出典を削除せず `rag://grounding/...` と source/evidence identityをContextへ渡します。Contextは参照を選択してbudget評価・圧縮・materializeし、RAGがContextやPersistenceへ直接書き込みません。

## Versioning

RAG contract revisionは `1.0`、local lexical backend revisionは `local-lexical-v1` としてDefinitionFingerprintへ記録します。IndexやGrounding bundleのrevisionが変わった場合はContext / Definition driftとして扱い、既存Frozen Baselineを自動更新しません。
