# Runtime / Harness Authority

Status: **canonical boundary** (Issue #126).

## Ownership

UnityAgentのHarnessは、**Orchestrationが選び、Runtimeが執行する**構造です。

```text
Task Fingerprint
    ↓
src/unityagent/orchestration/routing
    ↓ explicit selection
route_id + task_contract + execution_profile
    ↓
src/unityagent/runtime/harnesses/effective_harness.py
    ↓ enforcement projection
Mutation / Verification / Dispatcher / Runner
```

Authorityは次のとおり固定します。

- **Policy** — Risk、Human Approval、Quality Gateの意味を定義する。
- **Context** — 現在のモデル入力をmaterializeする。Routeを選択しない。
- **Orchestration** — Route、Task Contract、Execution Profileを選択する。
- **Runtime** — 選択済み入力を実行・制約・検証する。
- **Persistence** — Durable state / evidence / memoryの正本を保持する。
- **Eval** — Runtime結果を評価する。実行権限を持たない。

## Effective Harness

`src/unityagent/runtime/harnesses/effective_harness.py` は、選択済みTask ContractをRuntimeの実行制約へ投影します。

入力は必ず明示します。

- canonical Task Contract path
- selected `route_id`
- selected `execution_profile`
- current request bindings / approvals / mutation channels

Runtimeは次を**行いません**。

- `src/unityagent/context/selection/context-catalog.yaml`からRouteを逆引きする
- Task Contract IDからRouteやMutation Channelを推測する
- Execution Profileを自動選択する
- Contract名からHuman Gateを暗黙追加する
- Semantic retry / replan / TODO selectionを行う

つまり、Runtimeは「どの道を走るか」を決めず、「渡された道で何が許可されるか」を執行します。

## Runtime enforcement sources

Effective Harnessが参照する正本は以下です。

- `src/unityagent/runtime/profiles/runtime-profiles.yaml` — supplied profileの実行能力
- `src/unityagent/policy/risk/risk-levels.yaml` — Risk / Human Approval rule
- `src/unityagent/policy/evidence/quality-gates.yaml` — Gate catalog
- `src/unityagent/runtime/guardrails/mutation-channels.yaml` — authoritative mutation channel
- `src/unityagent/runtime/permissions/mcp-activation.yaml` — tool exposure / access boundary
- `src/unityagent/orchestration/contracts/task_contracts/*.yaml` — Orchestrationから選択済みのTask Contract

`src/unityagent/context/selection` と `src/unityagent/orchestration/routing` はRuntime enforcementの探索対象ではありません。

## Runtime Harness surfaces

`src/unityagent/runtime/harnesses/harness-registry.yaml` がRuntime harnessの入口を列挙します。

- `effective_harness` — selected task/profileのenforcement projection
- `codex` — agent runner
- `native_unity_editor` — Native Unity Editor provider adapter
- `unity_editor_artifact_graph` — Unity Asset dependency inspection only
- `test` / `performance` / `scm` — explicit command harness
- `ix` — bounded code-intelligence transport

`command_harness.py` はTest / Performance / SCMだけを担当します。Unity EditorやTool Providerは専用ownerを経由し、generic command harnessへのsilent fallbackは行いません。

## Fail-closed invariants

- R0は常にmutation blocked。
- unresolved bindingがある間、direct mutationを許可しない。
- mutationには既知のresolved channelが必要。
- required Human Approvalが未承認ならdirect mutationを許可しない。
- `generic_planning` profileはdirect mutationを許可しない。
- `team_safe_import` はpackage channelのportable importだけを許可する。
- unavailable / unknown verificationをPASSへ昇格しない。
- allowed/prohibited mutationの競合はvalidation error。

## Validation

Harness invariant testは `tests/runtime/test_effective_harness.py` に集約します。

`tools/validate_all.py` は既存の `tests/runtime` suiteを通じてHarness contractを検証します。旧 `tools/HarnessProjection` / `tests/harness_projection` はcanonical authorityではなく、Issue #126で削除します。

## Non-goals

Runtime Harnessは次を所有しません。

- semantic route selection
- ParentGraph / SubGraph / Node selection
- semantic retry / replan
- durable checkpoint / workflow state
- long-term memory truth
- eval grading / Golden expectations
- human visual acceptanceそのもの

この境界により、Harnessは巨大なControllerではなく、**明示的に選ばれた実行を安全に通すExecution Harness Plane**として維持します。
