---
name: csharp-safe-patch
description: 承認済みC# FindingへAPI・シリアライズ互換性を維持した最小修正を適用する。
metadata:
  version: "1.0.0"
---

# C# Safe Patch

- Require Rule ID, finding, safe-patch level and validation plan.
- One patch, one primary hypothesis.
- Preserve public API, serialized fields, enum values, save data and file names.
- Do not automatically change class/struct, sync/async API, exception contract or Job dependency graph.
- Prefer local semantic-preserving edits.
- Record changed files, reason, expected effect, tests, unresolved risk and revert condition.
