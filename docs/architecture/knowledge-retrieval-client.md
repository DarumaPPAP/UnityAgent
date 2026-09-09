# Knowledge Retrieval Client Boundary

`Context/Retrieval/Knowledge/knowledge_client.py` is the UnityAgent-side thin client for the MyResourceCenter Knowledge/RAG Service.

The client sends query intent, scope, filters, and retrieval budget. It does not send identity fields in the request body. Identity is supplied by the HTTP transport using a bearer token.

The client preserves `success`, `empty`, `partial`, `stale`, `blocked`, and `unavailable` as distinct states. It never turns a timeout or `unavailable` response into an empty result, and it never connects to Qdrant, an embedding provider, Google Drive, or an index file.

`KnowledgeContextAssembler` only performs Context-budget admission: it retains complete provenance, suppresses exact duplicate `(document, source_units)` pairs, preserves different source units, and records truncation. `KnowledgeCitationState` carries citations and `index_revision` to the answer layer.

## Example

```python
from Context.Retrieval.Knowledge.knowledge_client import (
    KnowledgeClientOptions,
    KnowledgeContextAssembler,
    KnowledgeHttpClient,
    KnowledgeSearchRequest,
)

client = KnowledgeHttpClient(
    KnowledgeClientOptions("http://127.0.0.1:8080", bearer_token="dev-token")
)
response = client.search(KnowledgeSearchRequest("RenderGraph post process", top_k=5))
context = KnowledgeContextAssembler(max_characters=12000).assemble(response)
```

The server-side contract and MCP tool definitions remain owned by MyResourceCenter. MCP consumers use the same response shape through knowledge_search, knowledge_get_document, and knowledge_index_status.

## Grounded answer generation

Context/Retrieval/Knowledge/answer_generation.py owns the layer after retrieval. It calls the thin client, admits evidence within a context budget, sends retrieved text as untrusted reference material to an AnswerModel adapter, validates claim-to-citation indexes, and abstains when evidence is empty, stale, unavailable, contradictory, or not fully cited.

The production model is configured behind the AnswerModel protocol. DeterministicAnswerModel is for local deterministic tests only. Prompt and answer bodies must not be written to normal logs.
