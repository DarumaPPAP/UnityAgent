# UnityAgent

UnityAgent は、個人向け Unity 開発 Agent の **canonical single-repository authority（正本）**です。

ユーザー固有 Policy、semantic routing、Task Contract、bounded Context materialization、Runtime 実行と Guardrail、durable Persistence、Operations の observability/control、Eval による品質測定までを、この Repository 内で一貫して管理します。

この Repository は汎用 Unity Best Practice 集ではありません。安全上の上位境界に反しない限り、今回のユーザー明示指示と `Policy/User/user-policy.yaml` を、外部 Reference や一般的推奨より優先します。

## 現在地点

UnityAgent の品質基盤 v1 は Phase 10 まで完了しています。

```text
Phase 8   Canonical single-repo cutover          完了
Phase 9   Production re-baseline                 完了
Phase 9   Reviewed baseline freeze               完了
Phase 10  Baseline comparator / regression gate  完了
Phase 10  Local Production gate                  標準運用
```

正式な Phase 9 Frozen Baseline は次です。

`Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml`

この Baseline は `gpt-5.6-luna` / reasoning effort `xhigh` による Real Production observation を固定しており、次の4 canonical case がすべて `observed / passed` です。

- `GOLDEN-ARCH-001`
- `GOLDEN-NAMING-001`
- `GOLDEN-MUTATION-001`
- `GOLDEN-EVIDENCE-001`

Frozen quality は 4/4 observed、4/4 quality-passed、`regression_pass_rate = 1.0`、canonical failure taxonomy はすべて clean です。

Phase 10 は、新しい Production candidate をこの Frozen Baseline と比較します。`PASS` しても Baseline は自動更新しません。

## Authority 順位

```text
今回のユーザー明示指示
  ↓
Policy/User/user-policy.yaml
  ↓
Project固有Policy / 検証済みProject Fact
  ↓
Unity Domain Standard / 選択されたSkill
  ↓
外部Reference
  ↓
一般的Best Practice
```

Project Fact とユーザー Preference は分離します。Unity Version、Render Pipeline、namespace、Scene構成、Asset、Package Version などの Project Fact を推測で埋めません。一方、ユーザー固有の設計・レビュー方針を一般論で上書きしません。

`AGENTS.md` は bootstrap map です。詳細規約を複製する場所ではなく、各 canonical authority への入口です。

## Canonical ownership

| Area | Canonical Source | Responsibility |
| --- | --- | --- |
| User Policy | `Policy/User/user-policy.yaml` | ユーザー固有の開発Policy |
| Risk / Security / Approval / Evidence | `Policy/` | 判断・安全境界 |
| Route selection | `Orchestration/Routing/` | semantic primary route の選択 |
| Parent Graph / semantic coordination | `Orchestration/Definitions/` + `Orchestration/Graph/` | bounded coordination、replan、local loop |
| Task Contract | `Orchestration/Contracts/TaskContracts/` | Input、Mutation境界、Gate、Completion / Stop条件 |
| Orchestrator | `Orchestration/Orchestrator/` | Runtime handoff。process実行は所有しない |
| Context | `Context/` | current-call の選択・materialization・retrieval・budget |
| Runtime execution | `Runtime/Runner/` + `Runtime/Dispatcher/` + `Runtime/ExecutionControl/` | 実process / tool実行、hard limit |
| Runtime guardrails / harnesses | `Runtime/Sandbox/` + `Runtime/Guardrails/` + `Runtime/Permissions/` + `Runtime/Harnesses/` | Mutation scope、Permission、実行可能なVerification |
| Runtime evidence / telemetry | `Runtime/EvidenceCapture/` + `Runtime/Telemetry/` | current-run observation |
| Persistence | `Persistence/` | durable State / Checkpoint / Memory / Evidence / Session truth |
| Operations | `Operations/` | Observability、Detection、Incident/Runbook、approved control、ChangeManagement |
| Eval | `Eval/` | Golden/Behavior grading、Attribution、Replay、Rebaseline、Regression、ChangeProposal |
| Domain Skills | `.agents/skills/` | 選択されたTask固有の実行指示 |
| Supporting references | `SkillReferences/`, `Specs/`, `Templates/`, `docs/` | 人間向け・補助資料。上記authorityの代替ではない |

責務の基本原則は次です。

> Policy defines; Orchestration decides; Context materializes; Runtime executes; Persistence remembers; Operations observes/controls; Eval measures/proposes.

近くのComponentで技術的に実装可能だからという理由で、Authorityを別Layerへ移しません。

## Production execution flow

bounded Task では最短の canonical path を優先します。

```text
User Request
   ↓
Policy
   ↓
Task Fingerprint
   ↓
Orchestration/Routing/task-routes.yaml
   ↓
One Primary Route + semantic Execution Profile
   ↓
Context/Selection/context-catalog.yaml
   ↓
One Context Pack + One Primary Skill + One Task Contract
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

Parent Graph は semantic coordination が本当に必要な場合だけ使います。Local Loop は bounded Graph coordination であり、別の top-level control plane ではありません。

## Routes / Task Contracts

Route の正本は次です。

`Orchestration/Routing/task-routes.yaml`

現在の primary route は以下です。

| Route | 主用途 |
| --- | --- |
| `generic-planning` | より具体的なsemantic routeに一致しない一般Planning |
| `architecture-design` | Architecture、File粒度、Type / Ownership判断 |
| `graphics-mcp` | MyUnityMCP Graphics / Domain Capability設計 |
| `csharp-local-fix` | boundedな局所C#実装 / Review |
| `rendering-incident` | 原因不明のRendering障害、Platform divergence調査 |
| `shader-change` | ShaderLab / HLSL / Compute変更 |
| `renderer-feature-change` | RendererFeature / Renderer Pipeline変更 |
| `performance-experiment` | Baseline付きPerformance調査 |
| `asset-data-change` | Scene / Prefab / Material / Serialized Asset変更 |
| `portable-feature` | Project非依存Package / Editor Tool設計 |
| `safe-import-integration` | 制限付きStaging Import |
| `visual-direction` | Lighting、Composition、LookDev、Visual Review |

Technology keyword だけで Route を決めません。未知の Fingerprint dimension は推測しません。

Task Contract は次にあります。

`Orchestration/Contracts/TaskContracts/`

選択されたRouteについて、allowed/prohibited mutation、required gate、completion、stop condition を定義します。

## Execution Profiles

Execution Profile は Runtime enforcement contract です。

`Runtime/Profiles/runtime-profiles.yaml`

| Profile | Project Access | Mutation Role |
| --- | --- | --- |
| `generic_planning` | none | direct mutationなし |
| `personal_full_control` | full when authorized | 許可済み analysis / verification / mutation |
| `team_safe_import` | no external export | staging-only portable import |

Profile の **選択** は Orchestration が所有します。Runtime は渡された Profile を enforce するだけで、semantic retry / replan のAuthorityは持ちません。

## Context Engineering

Context selection の正本は次です。

`Context/Selection/context-catalog.yaml`

Context は、Orchestrationが先に選んだRouteへ bounded に materialize されます。Context自身はRouteを選ばず、durable State / Evidence store にもなりません。

Materializer は必要に応じて以下を解決します。

```text
Selected Route
  ├─ Context Pack
  ├─ Primary Skill
  ├─ Canonical Task Contract
  ├─ Required Policy Clauses
  └─ Optional / Conditional Knowledge
```

Context Budget は `Context/Budget/`、Knowledge Retrieval は `Context/Retrieval/` が正本です。

全Skill、全Reference、全Knowledgeを毎Taskで一括読込しません。

## Runtime / Harness boundary

実行可能なSafetyとVerificationは `Runtime/` が所有します。旧Context側Harness authorityへ戻しません。

Runtime が所有するもの:

- Codex / tool / process の実実行
- hard timeout / cancellation
- workspace / mutation-scope enforcement
- permission enforcement
- Unity / test / performance / SCM harness実行
- current-run evidence capture / telemetry

Runtime が所有しないもの:

- semantic Route selection
- Parent Graph topology / semantic replan policy
- durable Evidence / Memory / Checkpoint truth
- Agent quality grading

## Persistence boundary

Persistence は durable truth layer です。

`Checkpoint != Memory != Evidence`

- Checkpoint: State snapshot reference
- Memory: durable retrievable context/history
- Evidence: Persistence commit後のappend-only execution evidence
- Resume: DefinitionFingerprintを比較し、互換性がない場合はfail-closed

RuntimeでcaptureしたEvidenceは、`Persistence/Evidence/` へappendされるまでhistorical durable evidenceではありません。

## Eval / Evidence semantics

Eval は structured Runtime / Persistence facts を測定します。canonical structured evidence が存在する場合、lossy prose から authority fact を再構築しません。

重要な意味論:

- `passed`: 必須Evidenceが成功を裏付ける
- `failed`: 観測済みEvidenceが失敗を裏付ける
- `unavailable`: Gateを観測できない。成功ではない
- `not_observed`: Production behaviorを観測できず、Agent quality denominatorから除外
- Compile成功だけで Runtime / Visual / Performance / Player / Target Device 成功を保証しない
- Golden expected content を Production Prompt / Context へ注入しない

Agent regression と Runtime / Infrastructure / Evaluator failure は分離します。

## Phase 9 Frozen Baseline

正式な accepted baseline は次です。

`Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml`

このManifestは以下を固定します。

- accepted Production run
- exact source revision / Runtime identity
- 4/4 observed / passed quality
- canonical failure taxonomy counts
- 4 caseのDefinitionFingerprint
- Historical Replay namespace coverage
- immutable provenance reference

Phase 10 candidate が `PASS` しても、このBaselineを置き換えません。

Baseline置換には、新しいProduction observation、RebaselineSummary、必要なHistorical Replay、`baseline_ready`、専用Reviewed Freeze PRが必要です。

## Phase 10 Regression Gate

標準運用は **Local Production Gate** です。ローカルの認証済みCodex CLI sessionを利用します。

Repository rootから実行します。

```powershell
python .\Tools\Phase10\run_local_regression_gate.py
```

標準比較条件:

- model: `gpt-5.6-luna`
- reasoning effort: `xhigh`
- per-case timeout: `600` seconds

Local runner は clean Git worktree を確認し、正確なHEAD revisionとCodex versionを記録したうえで、4 Production Smoke case → Behavior Eval → RebaselineSummary → Baseline Comparatorまで実行します。

標準Local pathは `OPENAI_API_KEY` を要求しません。親shellからその環境変数を継承していた場合も、Codex起動前に子Production environmentから除去します。

Phase 10の最終判定は4種類です。

| Decision | 意味 |
| --- | --- |
| `PASS` | Comparable candidate が Frozen Baseline を維持 |
| `BLOCK_REGRESSION` | 観測済みAgent Behaviorが劣化 |
| `BLOCK_INCONCLUSIVE` | 現在のProduction品質を十分に確立できない |
| `REBASELINE_REQUIRED` | Runtime / Eval definition が変わり直接比較できない |

GitHub-hosted workflow は明示的なCI自動化用のOptional経路として残しています。Hosted runnerにはローカルChatGPT/Codex login sessionが存在しないため、この経路では適切なRepository credentialが別途必要です。

詳細は `docs/migration/phase10-baseline-comparator.md` を参照してください。

## Local Validation

canonical local validation は次です。

```powershell
python .\Tools\validate_all.py
```

このコマンドは canonical YAML、Policy integrity、stale path、Skill、Knowledge / Task Contract、Context Pack、Golden / Behavior contract、Phase 8 cutover invariant、および Policy / Context / Orchestration / Runtime / Persistence / Operations / Eval のunit testを検証します。

個別確認例:

```powershell
python .\Tools\SkillValidator\validate_skills.py --strict
python .\Tools\ContractValidator\validate_contracts.py
python .\Tools\ContextPackValidator\validate_context_packs.py
python .\Eval\Behavior\validate_phase8_cutover.py
python .\Eval\Rebaseline\validate_baseline_freeze.py .\Eval\Rebaseline\Baselines\phase9-baseline-20260830-09.yaml
python -m unittest Eval.Tests.test_phase10_baseline_comparator
python -m unittest Eval.Tests.test_phase10_local_regression_gate
```

UnityAgentのText ArtifactはUTF-8です。PowerShellで確認するときは明示的にUTF-8を指定します。

```powershell
Get-Content ".\README.md" -Raw -Encoding UTF8
```

## External Repository boundary

`DarumaPPAP/Unity-Graph-Engineering` は Phase 8 cutover 後、**UnityAgent Production execution dependencyではありません**。

過去migrationのprovenanceはmigration documentへ残せますが、active execution authority はUnityAgent内の `Orchestration/` / `Runtime/` / `Persistence/` / `Eval/` が所有します。

`DarumaPPAP/MyUnityMCP` は、UnityAgentが自身のPolicy / Context / Runtime contractを通して選択・統制するMCP manifest / tool schema / package implementation surfaceの外部ownerです。

compatibility adapter、旧Graph側Production runner、fallback pathを使って、第二のactive execution authorityを復活させません。

## Legacy / Anti-regression

Post-cutover Repositoryはsingle authorityを維持します。

- legacy dot-ai authority treeを復活させない
- Context / Eval / Persistence compatibility layerや旧Eval / Loop shimを復活させない
- Unity-Graph-EngineeringをProduction execution dependencyへ戻さない
- semantic Graph / replan authorityをRuntimeへ移さない
- process / tool executionをEvalやOrchestrationへ移さない
- Contextをdurable Memory / Checkpoint / Evidence storeにしない
- `not_observed`をAgent regressionとして扱わない
- Candidateを通すためにFrozen Production evidenceを書き換えない
- Phase 10 `PASS` 後にFrozen Baselineを自動更新しない

Historical migration情報は `docs/migration/` とHistorical Eval Dataset / Replay surfaceに残し、active Production bootstrap authorityとして扱いません。

## Repository Map

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
├─ Tools/                    # local validators / Phase 10 local gate
├─ SkillReferences/          # supporting domain references
├─ Specs/                    # supporting feature / project specifications
├─ Templates/                # reusable supporting templates
└─ docs/migration/           # migration / contract-change provenance
```

詳細な責務Mapは `AGENTS.md` から確認してください。品質基盤の履歴は `docs/migration/phase8-cutover.md`、Phase 9 migration document群、`docs/migration/phase10-baseline-comparator.md` を正本として追跡します。
