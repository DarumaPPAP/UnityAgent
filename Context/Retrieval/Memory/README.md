# Memory Projection Compatibility API

`Context/Retrieval/Memory/` は、`Persistence/Memory/` が所有する正本を読み取る既存APIを保持する互換入口です。新しい検索・候補正規化・Groundingは top-level `RAG/Adapters/memory/` が担当します。

## 所有権境界

- `Persistence/Memory/` が永続Memoryレコード、Validation、Revision、Conflict / Risk metadata、Project単位のRetrievalを所有します。
- `RAG/Adapters/memory/` はPersistenceのread APIからRAG Candidateを作り、ContextはRAGのprojectionを選択・予算化・materializeします。
- 既存 `Context.Retrieval.Memory.project_memory.retrieve_projections` は既存利用者向けの互換APIとして残します。
- Context配下に第二の永続Memory Storeを作成しません。
- 廃止済みまたはTest専用のMemory RootをCurrent Stateの入力として信頼しません。

## Projection契約

Projection Contractは `Context/Contracts/memory-projection.schema.yaml` です。

現行実装の入口:

```python
from Context.Retrieval.Memory.project_memory import retrieve_projections
```

PersistenceまたはProjectMemoryが利用できない場合、このアダプターは推測で補完せず安全側に停止します。
