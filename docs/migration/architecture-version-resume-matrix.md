# Architecture v3.1 Versioning / Resume Compatibility Matrix

Status: Phase 0.

## Versioned definitions

Every run must be traceable to the deployed definition combination.

| definition | required revision/fingerprint | persisted in | resume sensitivity |
|---|---|---|---|
| Policy clause set | `policy_revision` | Run, Checkpoint, Evidence, Eval | critical |
| Prompt specification | `prompt_revision` | Run, Checkpoint, Eval | high |
| Context definition/packs | `context_revision` | Run, ContextManifest, Checkpoint, Eval | high |
| ParentGraph/SubGraph definitions | `graph_revision` | Run, WorkflowState, Checkpoint, Eval | critical |
| Runtime execution profile | `runtime_profile_revision` | Run, Checkpoint, Evidence, Eval | critical |
| Tool schema set | `tool_schema_revision` | Run, Checkpoint, Evidence, Eval | critical |
| Checkpoint schema | `checkpoint_schema_revision` | Checkpoint | critical |
| Evidence schema | `evidence_schema_revision` | Evidence, Checkpoint, Eval | critical |
| Golden/Grader contracts | `eval_contract_revision` | Eval result/report | replay-critical |
| Architecture | `architecture_version` | VersionManifest, Run, Checkpoint | critical |

`Operations/ChangeManagement/VersionManifest/` is the deployed-combination source for these revision references.

## Resume decision matrix

| saved vs current | semantic compatibility | schema migration | decision |
|---|---|---|---|
| identical fingerprint | compatible | none | resume |
| only non-executed documentation/reporting revision changed | compatible if declared | none | resume with audit note |
| Prompt/Context changed but active step has not materialized model input yet | conditionally compatible | optional | re-materialize Context, record new fingerprint, then resume |
| Prompt/Context changed after current action was issued | ambiguous | possible | do not reuse issued action; return to safe orchestration boundary and replan |
| Policy changed | unknown by default | policy-specific | fail closed unless explicit compatibility declaration exists |
| Approval/Risk/Permission rule changed | incompatible by default | none automatic | require new Policy evaluation and possibly Human Gate |
| Graph changed outside completed path only | conditionally compatible | graph migration mapping required | migrate WorkflowState then resume |
| Graph changed at/around active Node/SubGraph | ambiguous | graph migration required | fail closed for human review if mapping is not exact |
| Runtime profile/tool schema changed before a tool action executes | conditionally compatible | none | revalidate action/ticket under current Runtime before execute |
| Runtime profile/tool schema changed while an external action may be in-flight | incompatible/ambiguous | none automatic | reconcile external side effects/evidence before resume |
| Checkpoint schema changed with tested migration | compatible after migration | required | migrate copy, validate, then resume |
| Checkpoint schema changed without tested migration | incompatible | unavailable | fail closed |
| Evidence schema changed | historical evidence remains immutable | compatibility reader required | read old version; never rewrite evidence merely to resume |
| Eval/Golden/Grader changed | Runtime resume unaffected | none | evaluation replay uses explicitly selected Eval revision; never silently compare mixed baselines |
| Architecture major boundary changes | incompatible by default | explicit architecture migration | Human review |

## Compatibility declaration

Every versioned definition that supports resume across revisions may declare:

```yaml
revision: "..."
compatible_from:
  - "..."
migrations:
  - from: "..."
    to: "..."
    migration_id: "..."
```

Absence of a compatibility declaration for a changed critical definition is not interpreted as compatible.

## Resume algorithm

```text
1. load checkpoint without mutating it
2. verify checkpoint integrity/hash/provenance
3. resolve saved DefinitionFingerprint
4. resolve current VersionManifest
5. compare every critical revision
6. classify each difference: compatible / migration_required / ambiguous / incompatible
7. if migration_required: migrate into a new checkpoint record, preserve original
8. if ambiguous or incompatible: fail closed and require review/replan
9. revalidate Policy/Approval/Runtime permissions immediately before high-risk execution
10. emit resume evidence recording saved/current revisions and decision
```

## Evidence compatibility

Evidence is historical fact. Schema evolution uses versioned readers/adapters. A migration may create a derived normalized record that references the original evidence, but must not overwrite the original payload/hash/provenance.

## Eval replay compatibility

A replay result records both:

- the production definition fingerprint under which the original run executed; and
- the Eval/Golden/Grader revision used for the replay.

This prevents a newer evaluator from being mistaken for the original production definition.

## Phase migration matrix

| phase | old state compatibility expectation |
|---|---|
| 1 canonical contracts | legacy artifacts accepted through explicit adapters; canonical output preferred |
| 2 Policy/Context | old `.ai` references may be read only through temporary compatibility mapping; no new writes |
| 3 Runtime | old Graph-run evidence replayed into canonical contracts; active old in-flight runs require explicit reconciliation |
| 4 Orchestration | old loop/orchestrator state must map to ParentGraph/SubGraph/LocalLoop schemas or fail closed |
| 5 Persistence | legacy state/memory/evidence split with provenance; original evidence retained |
| 6 Eval | old Behavior/Golden artifacts replayed with explicit evaluator revision |
| 7 Operations | checkpoints/control actions record VersionManifest refs |
| 8 cutover | no legacy runtime compatibility assumed unless explicitly retained for historical read-only replay |
| 9 re-baseline | new baseline starts only after runtime/evaluator defects are separated from Agent regressions |

## Mandatory tests

- identical-version resume
- compatible definition-only change
- Policy revision mismatch fail-closed
- active Graph node revision mismatch
- tool schema change before execution
- checkpoint schema migration success/failure
- evidence old-schema read without mutation
- HITL pause followed by definition change
- replay using old production fingerprint + new Eval revision
- corrupted/unknown revision reference fail-closed
