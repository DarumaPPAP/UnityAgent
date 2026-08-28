# Architecture v3.1 Compatibility / Delete List

Status: Phase 0. **This is a future cutover list, not deletion authorization.**

Deletion requires: migrated canonical owner, reference removal, regression parity, production artifact replay where applicable, controlled Production Smoke, and explicit Human Gate approval.

## Delete after Phase 8 cutover approval

| path/component | why temporary | prerequisites before delete | evidence required |
|---|---|---|---|
| `UnityAgent/.ai/` | legacy ownership root; Policy/Context/Harness/Eval are being reassigned to canonical modules | all reads/writes switched; stale-reference scan = 0; user-policy equivalence proven | full CI + policy/context/runtime/eval regressions |
| `UnityAgent/.ai/integrations/unity-graph-engineering.yaml` | two-repo handoff definition | UnityAgent owns imported Runtime/Orchestration/Persistence contracts | cross-repo compatibility parity + one-repo smoke |
| `UnityAgent/Tools/LoopIntegration/*` | compatibility bridge to old Graph execution ownership | canonical Orchestration/Runtime path active | handoff parity + artifact replay |
| Graph `Tools/UnityAgentCompatibility/*` | reverse compatibility bridge | no active caller after UnityAgent cutover | stale-reference scan + compatibility suite migrated |
| Graph `Tests/UnityAgentCompatibility/*` | bridge-specific tests | replacement canonical integration tests pass | new integration tests + CI |
| Graph `.github/workflows/validate-unityagent-compatibility.yml` | cross-repo compatibility CI | one-repo CI covers boundary contracts | UnityAgent CI green |
| Graph `policies/unityagent-compatibility.yaml` | two-repo policy | no active Graph execution source of truth | stale-reference scan |
| Graph `Tools/BehaviorEvalAdapter/*` | translation layer between mismatched Runtime/Eval contracts | Runtime/Persistence/Eval natively share canonical evidence/result contracts | ARCH/NAMING/MUTATION/EVIDENCE replay with zero fact loss |
| any legacy duplicate failure-taxonomy/evidence schema | duplicate canonical contract | one owning schema established; all consumers migrated | schema uniqueness CI |
| any temporary `.ai` compatibility reader | migration-only fallback | new canonical paths stable; no fallback hit in controlled smoke | runtime telemetry proving no fallback use |
| root `Tools/` ownership buckets after all content migrated | legacy form-based grouping | every implementation has an owning v3.1 module | root ownership validator |
| root legacy `Schemas/`/Graph `schemas/` concepts after migration | catch-all schema placement | all schemas live near owner | duplicate/stale schema validator |

## Repository-level cutover

`DarumaPPAP/Unity-Graph-Engineering` becomes archive/read-only **only after**:

1. all production execution/runtime code needed by UnityAgent is imported or intentionally retired;
2. UnityAgent no longer reads Graph files at runtime/CI;
3. all historical provenance links record the Graph base revisions;
4. canonical Runtime/Orchestration/Persistence tests pass;
5. Behavior/Golden regressions pass;
6. controlled Production Smoke passes on the one-repo path;
7. artifact replay proves no evidence/failure-attribution loss;
8. explicit human approval is given.

The Graph repository is not deleted. Git history remains migration provenance.

## Never delete automatically

- user-specific policy clauses
- comment policy or linked comment skills/standards
- accepted Golden boundary pairs/invariants without explicit reviewed replacement
- raw/canonical Evidence needed for audit or replay
- migration provenance/base revision references
- a compatibility path while any active code still depends on it

## Delete-order rule

```text
add replacement
 -> test replacement
 -> switch canonical reference
 -> observe no legacy use
 -> full regression/replay/smoke
 -> Human Gate
 -> delete compatibility/legacy source
 -> re-run stale-reference/full CI
```

A cleanup is invalid if deletion is used to force consumers onto an unproven replacement.
