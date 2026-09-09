# Qdrant adapter

Qdrant is an optional external backend. The canonical RAG contracts do not
import Qdrant types, and local lexical retrieval remains available when Qdrant
is not configured.

## Configuration

Set the following environment variables at the integration boundary:

```text
UNITYAGENT_QDRANT_URL=https://...
UNITYAGENT_QDRANT_API_KEY=...
UNITYAGENT_QDRANT_COLLECTION=unityagent-knowledge
UNITYAGENT_QDRANT_DENSE_VECTOR_SIZE=384
UNITYAGENT_QDRANT_EMBEDDING_MODEL=<approved-model-id>
```

The API key is never included in `QdrantConfig.to_public_dict()`, traces, or
retrieval diagnostics. Do not commit secrets or embedding payloads containing
private originals.

## Retrieval

`QdrantBackend` sends two named prefetches (`dense` and `sparse`) with the same
payload filter, then requests server-side RRF fusion. Returned payloads contain
summary and provenance only; canonical originals remain in MyResourceCenter /
Google Drive.

```python
from RAG.Adapters.qdrant import QdrantBackend

backend = QdrantBackend.from_environment(
    fallback=local_backend,
    allow_fallback=True,
)
```

Fallback is explicit. An unavailable Qdrant request produces diagnostics and a
partial result when the configured local fallback succeeds. Without an explicit
fallback, the result is blocked; it is never silently reported as a successful
Qdrant retrieval.

## Ingestion

`QdrantCollectionManager` is the only explicit write-side helper. It creates the
collection, creates payload indexes, and then upserts named dense/sparse vectors.
Retrieval never invokes it.
