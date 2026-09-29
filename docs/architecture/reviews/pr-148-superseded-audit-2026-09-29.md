# PR #148 と現行 main の差分監査

対象は `DarumaPPAP/UnityAgent` の PR #148（head `aa123f1c57b755d86d2fe556ec80d08857bfc06a`）と、2026-09-29 時点の `main`（`08c1c95842d65c4818bb5a222d0ea613e5272518`）。19 ファイル、追加 1632 行、削除 2 行を確認した。以下の分類は機能単位であり、1 ファイルに複数の機能が含まれる。

## 判定

**PR #148 は現時点で superseded として閉じられない。** 現行 main は汎用の Control Plane、Tool Broker、Approval Store、Evidence Store、Compile Provider を持つが、固定の Scene / GameObject / Material / Script を実際の Editor で生成し、Compile と Editor PlayMode まで一続きで検証する経路を持たない。PR の専用 Editor Bridge、保存の別承認、実行後の範囲検査、署名付き結果も現行経路に相当するものがない。

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

- 固定 Plan と入口: `ControlPlane/full_e2e.py`、`ControlPlane/unity_agent_control_plane.py`、`Tools/unity_agent_cli.py`、`ControlPlane/Resources/FullE2EProbe.txt`。
- Editor 実行: `Runtime/Tooling/Providers/UnityAgentEditor/full_e2e_provider.py`、`Packages/com.darumappap.unity-agent/Editor/FullE2EBridge.cs` と `.meta`、Editor 側の `FullE2EProbe.txt` と `.meta`。
- 契約と解決: `Policy/Security/capability_policy.py`、`Runtime/Tooling/capability_resolver.py`、`Runtime/Tooling/provider_contract.py`、`Runtime/Tooling/provider_registry.yaml`、`Runtime/Tests/test_provider_registry.py`。
- 検証と公開: `Runtime/Tests/test_full_e2e.py`、`.agents/plugins/unity-agent/skills/unity-agent-full-e2e/SKILL.md`、`docs/architecture/full-e2e-capability.md`、`README.md`、`pyproject.toml`。

## 回収方針と終了条件

現行 Architecture の責務に合わせ、固定 Plan は Control Plane、Editor 観測と操作は Production Provider、権限と証跡は既存 Policy / Persistence に結合する。PR の実装をそのまま Production と判定せず、特に Editor Bridge の寿命、署名、失効、途中失敗、Scope 検査を現行契約に対して再検証する。上記 13 件の固有挙動を回収し、現在の clean checkout での検証が成立するまで PR #148 は開いたままとする。

この監査は Source と PR 差分の静的比較である。PR #148 の Unity Editor、PlayMode、Player、実機での動作成功を示さない。
