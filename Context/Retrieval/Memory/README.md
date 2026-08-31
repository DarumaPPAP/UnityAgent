# Context側のMemory Projection

`Context/Retrieval/Memory/` は、`Persistence/Memory/` が所有する正本の永続Memoryを読み取り専用で参照するアダプターです。

## 所有権境界

- `Persistence/Memory/` が永続Memoryレコード、Validation、Revision、Conflict / Risk metadata、Project単位のRetrievalを所有します。
- `Context/Retrieval/Memory/` はRequestのValidation、Persistence interfaceへのQuery、候補のRank / Reduce、`MemoryProjection` の出力だけを担当します。
- Context配下に第二の永続Memory Storeを作成しません。
- 廃止済みまたはTest専用のMemory RootをCurrent Stateの入力として信頼しません。

## Projection契約

Projection Contractは `Context/Contracts/memory-projection.schema.yaml` です。

現行実装の入口:

```python
from Context.Retrieval.Memory.project_memory import build_memory_projection
```

PersistenceまたはProjectMemoryが利用できない場合、このアダプターは推測で補完せず安全側に停止します。
