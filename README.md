# UnityAgent

UnityAgent is the canonical single-repository authority for a personal Unity development agent. It owns user-specific Policy, semantic routing and task contracts, bounded Context materialization, Runtime execution and guardrails, durable Persistence, Operations observability/control, and Eval quality measurement.

This repository is **not** a generic Unity best-practice collection. The user's explicit instructions and `Policy/User/user-policy.yaml` take precedence over external references and general recommendations unless a higher safety boundary requires otherwise.

## Current state

UnityAgent's quality foundation v1 is complete through Phase 10.

```text
Phase 8   Canonical single-repo cutover         complete
Phase 9   Production re-baseline                complete
Phase 9   Reviewed baseline freeze              complete
Phase 10  Baseline comparator / regression gate complete
Phase 10  Local Production gate                 standard operating path
```

The accepted Phase 9 baseline is:

`Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml`

It freezes a real Production observation using `gpt-5.6-luna`, reasoning effort `xhigh`, with all four canonical cases observed and passed:

- `GOLDEN-ARCH-001`
- `GOLDEN-NAMING-001`
- `GOLDEN-MUTATION-001`
- `GOLDEN-EVIDENCE-001`

The frozen quality result is 4/4 observed, 4/4 quality-passed, `regression_pass_rate = 1.0`, with the canonical failure taxonomy clean.

Phase 10 compares new Production candidates against that frozen baseline. It never auto-updates the baseline.

## Authority order

```text
Current explicit user instruction
  ↓
Policy/User/user-policy.yaml
  ↓
Project-specific policy / verified project facts
  ↓
Unity domain standards and selected Skills
  ↓
External references
  ↓
General best practice
```

Project facts and user preferences are different things. Unity version, render pipeline, namespace, scene structure, assets, package versions, and other project facts must not be guessed. User-specific design and review policies must not be silently replaced by generic recommendations.

`AGENTS.md` is only the bootstrap map. It points to canonical authorities; it is not a duplicate policy store.

## Canonical ownership

| Area | Canonical source | Responsibility |
| --- | --- | --- |
| User Policy | `Policy/User/user-policy.yaml` | User-specific development policy |
| Risk / Security / Approval / Evidence rules | `Policy/` | Decision and safety boundaries |
| Route selection | `Orchestration/Routing/` | Semantic primary route selection |
| Parent graph / semantic coordination | `Orchestration/Definitions/` + `Orchestration/Graph/` | Bounded semantic coordination, replan and local loops |
| Task contracts | `Orchestration/Contracts/TaskContracts/` | Inputs, mutation boundaries, gates, completion / stop conditions |
| Orchestrator | `Orchestration/Orchestrator/` | Runtime handoff; no process execution implementation |
| Context selection / materialization | `Context/` | Current-call context, retrieval and budget |
| Runtime execution | `Runtime/Runner/` + `Runtime/Dispatcher/` + `Runtime/ExecutionControl/` | Actual process / tool execution and hard limits |
| Runtime guardrails / harnesses | `Runtime/Sandbox/` + `Runtime/Guardrails/` + `Runtime/Permissions/` + `Runtime/Harnesses/` | Mutation scope, permissions and executable verification |
| Runtime evidence / telemetry | `Runtime/EvidenceCapture/` + `Runtime/Telemetry/` | Current-run observations |
| Persistence | `Persistence/` | Durable state, checkpoint, memory, evidence and session truth |
| Operations | `Operations/` | Observability, detection, incident/runbook, approved runtime control and change management |
| Eval | `Eval/` | Golden/Behavior grading, attribution, replay, rebaseline, regression comparison and change proposals |
| Domain Skills | `.agents/skills/` | Selected task-specific operating instructions |
| Supporting references | `SkillReferences/`, `Specs/`, `Templates/`, `docs/` | Human/reference material; not a replacement for canonical authorities above |

The responsibility rule is:

> Policy defines; Orchestration decides; Context materializes; Runtime executes; Persistence remembers; Operations observes/controls; Eval measures/proposes.

Do not move these responsibilities across layers just because a nearby component can technically perform them.

## Production execution flow

For bounded tasks, UnityAgent prefers the shortest canonical path:

```text
User request
   ↓
Policy
   ↓
Task fingerprint
   ↓
Orchestration/Routing/task-routes.yaml
   ↓
One primary route + semantic execution profile
   ↓
Context/Selection/context-catalog.yaml
   ↓
One Context Pack + one Primary Skill + one Task Contract
   ↓
Context/Assembly/materialize_context.py
   ↓
Runtime handoff
   ↓
Runtime execution / guardrails / evidence capture
   ↓
Persistence append
   ↓
Eval measurement
```

A Parent Graph is used only when semantic coordination is actually needed. Local loops are bounded graph coordination; they are not a separate top-level control plane.

## Routes and task contracts

The canonical route selector is:

`Orchestration/Routing/task-routes.yaml`

Current primary routes are:

| Route | Main use |
| --- | --- |
| `generic-planning` | Generic planning when no more-specific semantic route matches |
| `architecture-design` | Architecture, file granularity, type/ownership decisions |
| `graphics-mcp` | MyUnityMCP graphics/domain capability design |
| `csharp-local-fix` | Bounded local C# implementation / review |
| `rendering-incident` | Unknown rendering failure or platform divergence investigation |
| `shader-change` | ShaderLab / HLSL / Compute changes |
| `renderer-feature-change` | RendererFeature / renderer pipeline changes |
| `performance-experiment` | Baseline-backed performance investigation |
| `asset-data-change` | Scene / Prefab / Material / serialized asset changes |
| `portable-feature` | Project-independent package / editor tool design |
| `safe-import-integration` | Restricted staging import path |
| `visual-direction` | Lighting, composition, look development and visual review |

Technology keywords alone are not route authority. Unknown fingerprint dimensions are not guessed.

Task contracts live under:

`Orchestration/Contracts/TaskContracts/`

They define allowed/prohibited mutation, required gates, completion conditions and stop conditions for the selected route.

## Execution profiles

Execution profiles are Runtime enforcement contracts at:

`Runtime/Profiles/runtime-profiles.yaml`

| Profile | Project access | Mutation role |
| --- | --- | --- |
| `generic_planning` | none | no direct mutation |
| `personal_full_control` | full when authorized | authorized analysis / verification / mutation |
| `team_safe_import` | no external export | staging-only portable import |

Profile **selection** belongs to Orchestration. Runtime only enforces the supplied profile; Runtime does not own semantic retry/replan decisions.

## Context Engineering

Context selection is resolved through:

`Context/Selection/context-catalog.yaml`

Context is bounded to the already-selected Orchestration route. It does not choose the route and it is not a durable state/evidence store.

The materializer resolves, as needed:

```text
selected route
  ├─ Context Pack
  ├─ Primary Skill
  ├─ canonical Task Contract
  ├─ required Policy clauses
  └─ optional / conditional Knowledge
```

Context Budget is defined under `Context/Budget/`. Knowledge retrieval is under `Context/Retrieval/`.

The repository does not load every Skill, reference or Knowledge document for every task.

## Runtime / Harness boundary

Executable safety and verification belong to `Runtime/`, not to a legacy context-side harness tree.

Runtime owns:

- actual Codex / tool / process execution;
- hard timeout and cancellation;
- workspace and mutation-scope enforcement;
- permissions;
- Unity/test/performance/SCM harness execution;
- current-run evidence capture and telemetry.

Runtime does **not** own:

- semantic route selection;
- Parent Graph topology or semantic replan policy;
- durable Evidence / Memory / Checkpoint truth;
- Agent quality grading.

## Persistence boundary

Persistence is the durable truth layer.

`Checkpoint != Memory != Evidence`.

- Checkpoint stores state snapshot references.
- Memory is durable retrievable context/history.
- Evidence is append-only execution evidence after Persistence commit.
- Resume compares DefinitionFingerprint and fails closed on incompatible state.

Runtime-captured evidence is not historical durable evidence until it is appended through `Persistence/Evidence/`.

## Eval and evidence semantics

Eval measures structured Runtime/Persistence facts. It must not reconstruct authoritative facts from lossy prose when canonical structured evidence exists.

Important semantics:

- `passed`: required evidence supports success.
- `failed`: observed evidence supports failure.
- `unavailable`: the gate could not be observed; it is not success.
- `not_observed`: Production behavior was not observed and is excluded from the Agent-quality denominator.
- compile success does not prove Runtime, Visual, Performance, Player or target-device success.
- Golden expected content must never be injected into Production Prompt or Context.

Agent regressions are kept separate from infrastructure/runtime/evaluator failures.

## Phase 9 frozen baseline

The accepted baseline is read-only reference data:

`Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml`

It records:

- the accepted Production run;
- exact source revision and runtime identity;
- 4/4 observed / passed quality;
- canonical failure taxonomy counts;
- all four DefinitionFingerprints;
- Historical Replay namespace coverage;
- immutable provenance references.

A passing Phase 10 candidate does **not** replace this baseline. Replacing the baseline requires a new Production observation, RebaselineSummary, required Historical Replay, `baseline_ready`, and a dedicated reviewed Freeze PR.

## Phase 10 Regression Gate

The standard operating path is local and uses the already-authenticated local Codex CLI session.

From the repository root:

```powershell
python .\Tools\Phase10\run_local_regression_gate.py
```

Default comparison identity:

- model: `gpt-5.6-luna`
- reasoning effort: `xhigh`
- per-case timeout: `600` seconds

The runner verifies a clean Git worktree, records the exact HEAD revision and Codex version, executes the four Production Smoke cases, grades them, builds a candidate RebaselineSummary and runs the Baseline Comparator.

The standard local path does not require `OPENAI_API_KEY`. If that variable is inherited from the parent shell, the local runner removes it from the child Production environment before launching Codex.

Phase 10 decisions are:

| Decision | Meaning |
| --- | --- |
| `PASS` | Comparable candidate maintains the frozen baseline |
| `BLOCK_REGRESSION` | Fully observed Agent behavior regressed |
| `BLOCK_INCONCLUSIVE` | Current Production quality could not be fully established |
| `REBASELINE_REQUIRED` | Runtime/evaluation definition changed enough that the candidate is not directly comparable |

The optional GitHub-hosted workflow remains available for explicit CI automation. That hosted path requires an appropriate repository credential because a fresh hosted runner has no local ChatGPT/Codex login session.

See `docs/migration/phase10-baseline-comparator.md` for the detailed contract.

## Local validation

Run the canonical local validation suite:

```powershell
python .\Tools\validate_all.py
```

It validates canonical YAML, Policy integrity, stale paths, Skills, Knowledge/Task contracts, Context Packs, Golden/Behavior contracts, Phase 8 cutover invariants, and unit-test suites across Policy / Context / Orchestration / Runtime / Persistence / Operations / Eval.

Useful targeted checks include:

```powershell
python .\Tools\SkillValidator\validate_skills.py --strict
python .\Tools\ContractValidator\validate_contracts.py
python .\Tools\ContextPackValidator\validate_context_packs.py
python .\Eval\Behavior\validate_phase8_cutover.py
python .\Eval\Rebaseline\validate_baseline_freeze.py .\Eval\Rebaseline\Baselines\phase9-baseline-20260830-09.yaml
python -m unittest Eval.Tests.test_phase10_baseline_comparator
python -m unittest Eval.Tests.test_phase10_local_regression_gate
```

All UnityAgent text artifacts are UTF-8. When inspecting text from PowerShell, use explicit UTF-8 decoding, for example:

```powershell
Get-Content ".\README.md" -Raw -Encoding UTF8
```

## External repository boundary

`DarumaPPAP/Unity-Graph-Engineering` is **not** a UnityAgent Production execution dependency after the Phase 8 cutover. Historical migration provenance may remain in migration documentation, but active execution authority is owned inside this repository.

`DarumaPPAP/MyUnityMCP` remains the external owner for MCP manifest / tool schema / package implementation surfaces that UnityAgent selects or governs through its own Policy, Context and Runtime contracts.

Do not reintroduce a second active execution authority through compatibility adapters, old Graph-side Production runners or fallback paths.

## Legacy / anti-regression rules

The post-cutover repository must remain single-authority.

- Do not restore the legacy dot-ai authority tree.
- Do not restore Context/Eval/Persistence compatibility layers or old evaluation/loop shims.
- Do not make Unity-Graph-Engineering a Production execution dependency again.
- Do not move semantic Graph/replan authority into Runtime.
- Do not move process/tool execution into Eval or Orchestration.
- Do not make Context a durable Memory/Checkpoint/Evidence store.
- Do not treat `not_observed` as Agent regression.
- Do not rewrite frozen Production evidence to make a candidate pass.
- Do not auto-update the frozen baseline after a Phase 10 `PASS`.

Historical migration information belongs in `docs/migration/` and historical Eval datasets/replay surfaces, not in active Production bootstrap authority.

## Repository map

```text
UnityAgent/
├─ AGENTS.md                 # bootstrap map
├─ .agents/skills/           # selected domain Skills
├─ Policy/                   # user / risk / approval / security / evidence authority
├─ Orchestration/            # routes / graphs / task contracts / runtime handoff
├─ Context/                  # selection / packs / retrieval / budget / materialization
├─ Runtime/                  # execution / guardrails / harnesses / telemetry
├─ Persistence/              # durable state / checkpoint / resume / memory / evidence
├─ Operations/               # observability / detection / incidents / control / change management
├─ Eval/                     # behavior / golden / replay / rebaseline / regression
├─ Tools/                    # local validators and Phase 10 local gate
├─ SkillReferences/          # supporting domain references
├─ Specs/                    # supporting feature/project specifications
├─ Templates/                # reusable supporting templates
└─ docs/migration/           # historical migration / contract-change provenance
```

For the detailed responsibility map, start from `AGENTS.md`. For quality-baseline history, use `docs/migration/phase8-cutover.md`, the Phase 9 migration documents, and `docs/migration/phase10-baseline-comparator.md`.
