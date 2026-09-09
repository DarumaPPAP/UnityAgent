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

## Staging answer acceptance

Use `Tools/knowledge-answer-acceptance.example.json` as the case-file shape, replace both placeholder questions with questions grounded in the staged MyResourceCenter source set, and set the expected status for each case. The runner reads the Knowledge bearer token from `KNOWLEDGE_SERVICE_TOKEN` and the real AnswerModel credentials from `KNOWLEDGE_ANSWER_ENDPOINT`, `KNOWLEDGE_ANSWER_API_KEY`, and `KNOWLEDGE_ANSWER_MODEL`; no secret is accepted as a command-line argument.

```bash
export KNOWLEDGE_SERVICE_TOKEN="<injected-by-secret-manager>"
python Tools/run_knowledge_answer_acceptance.py \
  --service-url https://knowledge-staging.example.internal \
  --cases Tools/knowledge-answer-acceptance.json \
  --mode smoke \
  --output reports/knowledge-answer-staging-smoke.json

python Tools/run_knowledge_answer_acceptance.py \
  --service-url https://knowledge-staging.example.internal \
  --cases Tools/knowledge-answer-acceptance.json \
  --mode load --requests 200 --concurrency 10 --p95-slo-ms 1500 \
  --output reports/knowledge-answer-staging-load.json

python Tools/run_knowledge_answer_acceptance.py \
  --service-url https://knowledge-staging.example.internal \
  --cases Tools/knowledge-answer-acceptance.json \
  --mode soak --duration-seconds 86400 --interval-seconds 60 \
  --output reports/knowledge-answer-staging-soak.json
```

For a grounded case, optionally set `expected_citation_locators` to the expected Source Unit locators and `expected_citation_mode` to `all` (default) or `any`. The runner compares those locators with the citations actually referenced by claims, and can reject a forbidden locator through `forbidden_citation_locators`; this gives a deterministic citation-correctness check without storing source labels.

The report contains case IDs, expected/actual statuses, abstention, citation count, citation coverage, citation-correctness result, index/model revisions, safe diagnostics, and latency. It never stores the question, generated answer, claim text, citation labels, retrieved content, bearer token, or provider response body. A grounded case must be `answered` with complete citation coverage and the expected citation locator(s); negative, blocked, stale, unavailable, and provider-failure cases must remain abstained with their expected typed status.
