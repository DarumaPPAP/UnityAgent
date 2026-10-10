# Memory Projection Adapter

`src/unityagent/context/retrieval/memory/`は、`src/unityagent/persistence/memory/`が所有する永続Memoryを読み取り専用で参照し、Request単位の`MemoryProjection`へ絞り込むAdapterです。

## 所有範囲

- `src/unityagent/persistence/memory/`が正本のMemory Record、Validation、Revision、Conflict/Risk metadata、Project単位のRetrievalを所有します。
- このDirectoryはRequestを検証し、PersistenceをQueryし、候補をRank / ReduceしてProjectionを返します。
- Context側に第二の永続Storeは作りません。
- 廃止済みまたはTest専用のMemory RootをCurrent Stateとして扱いません。
- Memory ProjectionはSubAgent RegistryやProvider Resolverではありません。

## Contract

Schema: `src/unityagent/context/contracts/memory-projection.schema.yaml`

```python
from unityagent.context.retrieval.memory.project_memory import build_memory_projection
```

PersistenceまたはProjectMemoryを利用できない場合、Adapterは不足情報を推測せず安全側に停止します。
