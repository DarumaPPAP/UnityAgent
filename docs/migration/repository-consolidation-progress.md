# Repository Consolidation Progress

Verified P0 merges: Agent #173 `007dbc66365a8c2ca26fa12cbc89d5b544d7339a`; Hub #93 `83dcd6e7a2cba94e5bc0b4975579252da1d5e69a`. Do not reimplement P0. GitHub execution Goal is now available in docs/migration/CodexCloud_UnityAgent_Complete_Goal.md, published by #174. It differs from the received implementation specification.

| Phase | Status | Branch / PR |
|---|---|---|
| P1 | Implemented; local Canonical and migrated Hub no_op PASS; PR CI pending | chore/repository-consolidation-p1 |
| P2 | Hub core move prepared; merge only after P1 | chore/repository-consolidation-p2 |
| P3–P4 | Pending merged producer SHAs | — |
| P5–P6 | Pending src packaging / cleanup | — |
| P7 | CI foundation implementation in isolated worktree | — |
| P8 | Pending final Layout Gate | — |

P1 permits only the known Hub/ prefix for Consumer-owned manifest/reasoning refs, with exact identity and unchanged execution fields. Exporter choice accepts exactly one known path per committed tree. Pinned mode requires the source-lock exporter, full commit and repository. Unknown exporter, path escape, unsupported identity and hash mismatch remain rejected. Existing old pin `61d3fad2e0aef50b69fc76fbbd839aca076de19f` is unchanged.

Validation: four new migration tests RED→GREEN; 37 focused Import tests PASS; canonical suite PASS. Actual migrated Hub snapshot exports four specialists and imports read-only no_op. Unity Editor/License/Player/Visual/device remain BLOCKED_NOT_RUN.

Next: verify required Canonical Validation and Squash Merge P1, then Hub P2. Resolve PR and merge facts from GitHub before resuming; do not infer merge state from this ledger.
