---
name: csharp-antipattern-audit
description: Unity C#を仕様、意味論、AOT、Burst/Jobs、Allocation、API互換性からRead-only監査する。
metadata:
  version: "1.0.0"
---

# C# Anti-pattern Audit

1. Resolve environment and compatibility contracts.
2. Read `CODING_STANDARDS.md`, C# rules and policy.
3. Trace ownership, lifetime and call frequency.
4. Classify findings as Confirmed / High confidence / Evidence required.
5. Assign Error / Warning / Suggestion / Evidence Required.
6. Assign Safe / Review Required / Manual Only.
7. Do not modify code.

Output Rule ID, location, evidence, conditions, impact, proposal, compatibility risk and validation.
