# PR #148 と現行 main の差分監査

対象は `DarumaPPAP/UnityAgent` の PR #148（head `aa123f1c57b755d86d2fe556ec80d08857bfc06a`）と、2026-09-29 時点のPR #157 merge後 `main`（`3aca3c221aa8bbc60d2ba49d4f392bc99c03bf78`）。19ファイル、追加1632行、削除2行を監査し、その後PR #158で固有挙動を現行Entry v2 Architectureへ回収した。以下の分類はPR #158着手前の機能差分である。

## 判定

**初回監査時点ではPR #148をsupersededとして閉じられなかった。** その後PR #158で、固定Scene / GameObject / Material / Script生成、Compile / Editor PlayMode、専用Editor Bridge、保存の別承認、実行後Scope検査、署名付きResult等を現行Architectureへ回収した。PR #148のEntry v1によるRoute / Context / Mutation Scopeのcaller指定は回収せず、Entry v2 Typed Intent → Orchestration生成へ置換した。

| 項目 | 分類 | 現行 main と PR #148 の差分 |
|---|---|---|
| Scene 作成 | UNIQUE_REQUIRED_BEHAVIOR | 現行の `scene.mutate` は契約と別 Provider の操作。固定 Scene を作成する Editor 実装はない。 |
| GameObject 作成 | UNIQUE_REQUIRED_BEHAVIOR | Cube と Probe Component の生成・確認が PR 固有。 |
| Material 作成 | UNIQUE_REQUIRED_BEHAVIOR | 候補 Shader の選択と実際の選択結果の照合が PR 固有。 |
| Script 作成 | UNIQUE_REQUIRED_BEHAVIOR | Template の SHA-256 と生成 Asset の一致確認が PR 固有。 |
| Plan と script preview | UNIQUE_REQUIRED_BEHAVIOR | 未作成状態を前提とする固定 Plan と Script 全文の事前表示が PR 固有。 |
| exact diff | UNIQUE_REQUIRED_BEHAVIOR | 汎用 Evidence 項目は存在するが、作成予定の `.meta` を含む差分の事前固定と事後照合は PR 固有。 |
| Approval と失効 | UNIQUE_REQUIRED_BEHAVIOR | 汎用 Approval Store と取消 Epoch は存在する。Plan、Project、対象 Path、期限、保存の別承認を Editor 実行中にも再確認する結合は PR 固有。 |
| mutation / save | UNIQUE_REQUIRED_BEHAVIOR | 汎用 Mutation Scope Guard は存在する。固定 Asset の生成と明示的な Scene 保存の実行経路は PR 固有。 |
| Compile | CURRENT_ARCHITECTURE_HAS_EQUIVALENT | `compile.observe` に Native Editor / Unity CLI の Production Provider が存在する。ただし PR の生成 Script と同一 Run での Compile 観測は固有。 |
| Editor PlayMode | UNIQUE_REQUIRED_BEHAVIOR | Probe の `Start()` 実行を Editor PlayMode で確認する経路はない。Player / 実機検証とは区別が必要。 |
| Evidence Artifact | UNIQUE_REQUIRED_BEHAVIOR | 汎用 Evidence Store は存在するが、Editor の署名付き結果と個別 Run Artifact の照合は PR 固有。 |
| process binding | UNIQUE_REQUIRED_BEHAVIOR | 現行の Editor Discovery は存在する。heartbeat、PID、実行ファイル、Project、Instance、HMAC の照合は PR 固有。 |
| scope inventory | UNIQUE_REQUIRED_BEHAVIOR | 汎用 Scope Guard は存在する。作成ディレクトリ全体の実在ファイル照合は PR 固有。 |
| retry policy | CURRENT_ARCHITECTURE_HAS_EQUIVALENT | Tool Broker は `maximum_retry_attempts=0` を受け付ける。PR は Control Plane の公開経路にも引数を通す。 |
| quarantine / fail-closed | UNIQUE_REQUIRED_BEHAVIOR | 汎用 Operations の quarantine は存在する。Bridge の不正 Job を隔離し、署名・承認・実在 Asset の不一致を失敗にする処理は PR 固有。 |

分類の合計は、上記 15 項目中 `CURRENT_ARCHITECTURE_HAS_EQUIVALENT=2`、`KNOWLEDGE_ALREADY_MIGRATED=0`、`UNIQUE_REQUIRED_BEHAVIOR=13`、`OBSOLETE=0`。部分的な汎用契約の存在を E2E の置換完了として数えていない。

## ファイル単位の確認範囲

- 固定 Plan と入口: `src/unityagent/control_plane/full_e2e.py`、`src/unityagent/control_plane/unity_agent_control_plane.py`、`src/unityagent/cli.py`、`src/unityagent/control_plane/resources/FullE2EProbe.txt`。
- Editor 実行: `src/unityagent/runtime/tooling/providers/unity_agent_editor/full_e2e_provider.py`、`Packages/com.darumappap.unity-agent/Editor/FullE2EBridge.cs` と `.meta`、Editor 側の `FullE2EProbe.txt` と `.meta`。
- 契約と解決: `src/unityagent/policy/security/capability_policy.py`、`src/unityagent/runtime/tooling/capability_resolver.py`、`src/unityagent/runtime/tooling/provider_contract.py`、`src/unityagent/runtime/tooling/provider_registry.yaml`、`tests/runtime/test_provider_registry.py`。
- 検証と公開: `tests/runtime/test_full_e2e.py`、`.agents/plugins/unity-agent/skills/unity-agent-full-e2e/SKILL.md`、`docs/architecture/full-e2e-capability.md`、`README.md`、`pyproject.toml`。

## 回収方針と終了条件

現行 Architecture の責務に合わせ、固定 Plan は Control Plane、Editor 観測と操作は Production Provider、権限と証跡は既存 Policy / Persistence に結合する。PR の実装をそのまま Production と判定せず、特に Editor Bridge の寿命、署名、失効、途中失敗、Scope 検査を現行契約に対して再検証する。上記 13 件の固有挙動を回収し、現在の clean checkout での検証が成立するまで PR #148 は開いたままとする。

この監査は Source と PR 差分の静的比較である。PR #148 の Unity Editor、PlayMode、Player、実機での動作成功を示さない。


## PR #158 回収結果

PR #158 `PR #148のFull E2E固有機能をEntry v2へ回収` では、初回監査の `UNIQUE_REQUIRED_BEHAVIOR=13` を以下の現行責務へ移した。

| 初回固有挙動 | 現行回収先 / 状態 |
|---|---|
| Scene / GameObject / Material / Script作成 | 固定Full E2E Editor Bridge + `unity_agent_editor` Production Provider |
| Plan / script preview | `src/unityagent/control_plane/full_e2e.py` のcreate-only immutable Plan |
| exact diff | 固定Asset/.meta inventoryをPlanと署名Resultで照合 |
| Approval / revocation | 既存Approval StoreへPlan/Project/Scope/期限をbindし、dispatch中にも再確認 |
| mutation / separate save | Mutation承認とScene Save承認を分離 |
| Editor PlayMode | 固定Probe `Start()` をEditor PlayModeで観測 |
| Evidence Artifact | Control Plane Evidence + signed Editor Result Artifact |
| process binding | heartbeat / PID / executable / Project / instance / signatureを照合 |
| scope inventory | `Assets/UnityAgentE2E` create-only inventoryとundeclared path拒否 |
| quarantine / fail-closed | malformed/stale/unsigned/out-of-scope resultを成功へ昇格しない |

初回に `CURRENT_ARCHITECTURE_HAS_EQUIVALENT` としたCompileとbounded retryも、現行Compile/Evidence経路およびFull E2Eの `maximum_retry_attempts=0` と結合した。

### Authority migration

旧PR #148の次の設計は**移植しない**。

```text
Entry v1
→ caller supplied route_id
→ caller supplied context_id
→ caller supplied mutation_scope
→ caller supplied capability_requests
```

現行は次で固定する。

```text
Entry v2 fixed_full_e2e_probe Typed Intent
↓
Orchestration Task Fingerprint
↓
asset-data-change Route
↓
Orchestration-owned fixed Mutation Scope
↓
scene.mutate + workflow=full_e2e CapabilityRequest
↓
ToolBroker
↓
unity_agent_editor Provider
```

専用Providerは `required_qualifiers: [workflow]` により一般の `scene.mutate` 候補から隔離する。

### Verification state

PR #158のRepository / Fixture CIは全8 workflowがGreenになった。これは固定Plan、Approval、Provider resolution、署名Result、Scope検査、Evidence persistenceのRepository-level回収を示す。

ただし実Unity Editor / Editor PlayMode / Player / Target DeviceのLive実行成功はこのCIからは証明しない。

```text
Repository Static / Fixture: PASS
Live Unity Editor: NOT_EVALUATED_RUNTIME
Player: NOT_EVALUATED_RUNTIME
Target Device: NOT_EVALUATED_RUNTIME
```

**Close判定:** PR #158がcurrent mainへMergeされた時点で、PR #148の固有挙動は現行Architectureへ回収済みとなるため、PR #148は `Superseded by current UnityAgent architecture` としてClose可能。PR #148自体をMergeして旧Entry v1 Authorityを復活させてはならない。
