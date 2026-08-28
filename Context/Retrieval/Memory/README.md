# Memory Retrieval Projection

Context does not own durable Memory. This directory defines only the retrieval boundary used to select a bounded current-call projection from `Persistence/Memory`.

Rules:

- `MemoryProjection` references a durable `memory_id`.
- Every projection retains source Evidence references.
- Context may select or compress a projection, but it must not promote, overwrite, retain, or delete durable Memory.
- A Memory projection is model input, not a resume checkpoint and not Evidence.
- Until Phase 5 implements the durable Memory store, unresolved memory retrieval remains an explicit binding rather than a guessed source.
