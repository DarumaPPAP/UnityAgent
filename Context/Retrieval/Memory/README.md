# Memory Retrieval Projection

Context does not own durable Memory. `Persistence/Memory/memory_store.py` is the canonical durable Memory owner; this directory defines only the read-only retrieval boundary used to select a bounded current-call projection.

Rules:

- `MemoryProjection` references a durable `memory_id`.
- Every projection retains source Evidence references.
- Context may select or compress a projection, but it must not promote, overwrite, retain, delete, or migrate durable Memory.
- Non-personal profiles retrieve only records admitted by Persistence's safe index; project-internal Memory is not scanned.
- A Memory projection is model input, not a resume checkpoint and not Evidence.
- Raw Evidence content is not included by default.
- Retrieval must not mutate the Persistence store.
