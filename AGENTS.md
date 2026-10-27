<!-- unityagent-bootstrap-map:v3 -->
# UnityAgent Bootstrap Map
> `bootstrap_map_only: true`

Unity開発の依頼を、既存構造とユーザー固有契約を保ちながら実装・検証・成果の報告まで完遂する。

## Authority
プラットフォームのSystem / Developer instructionと実行権限を上書きしない。
Repository内の優先順位は `src/unityagent/policy/user/user-policy.yaml#instruction_priority` を正本とする。
現在の明示要求・対象Taskの指示をSkillの一般的手順で上書きしない。
承認判断は `src/unityagent/policy/approval/approval-policy.yaml` に従い、既に与えられた承認の範囲を確認する。

## Git workflow
branch運用の正本は `.github/branch-policy.json`、説明は `docs/development/branch-policy.md` とする。
`main` は永続する統合正本であり、通常の作業は `main` から `feature/*`、`fix/*`、`chore/*`、必要時のみ `release/*` を作成する。
新機能は `feature/*`、不具合修正は `fix/*`、CI・Docs・Refactor・Repository整理は `chore/*` に分類する。`release/*` を `develop` の代替として常設しない。
新規branchに `codex/*`、`refactor/*`、`docs/*`、`ci/*` 等の追加prefixを作らない。通常PRのbaseは `main` とし、Squash Merge後に短命branchを削除する。

## Execution
1. User Policyを読み、Goal・対象範囲・完了条件を固定する。修正依頼は調査だけで終えず、変更・検証・必要な修復まで進む。
2. `src/unityagent/orchestration/routing/task-routes.yaml` で意図と範囲からRouteを選び、`src/unityagent/context/selection/context-catalog.yaml` で必要なContext / Skill / Task Contractだけ解決する。選択Routeの`required_policy_clauses`をPolicy provenanceとして記録する。
3. `src/unityagent/context/assembly/materialize_context.py` でcurrent-call Contextを構築する。Context / Retrieval Budgetと圧縮時の必須制約保持は `src/unityagent/context/budget/context-budget.yaml` に従う。
4. bounded TaskはFast Pathを使う。Graph、Local Loop、SubAgentは分解・修復・独立並列作業が必要な場合にだけ利用する。
5. Orchestrationは必要Capabilityを要求する。専門作業はSubAgent Definitionから適格なSubAgentを解決する。Provider-backed CapabilityはRuntime Tool Brokerが実行Backendを解決・実行し、Providerless reasoningはCanonical Runtime HandoffからCodexRunnerが実行する。SubAgent / Providerの直接呼出しでApproval / Scopeを迂回しない。
6. 開発中は変更範囲と影響する安全性契約に限定したテストを先に実行する。Python unittest は `-q -b` で成功ログを抑え、AI Contextに成功ログ全文を取り込まない。必要な失敗箇所だけを読む。Canonical Full ValidationはPRの必須CIで実行し、変更・失敗・リスクがなければ同じPASSを反復しない。Skip・未観測をPASS扱いしない。
7. 承認済み依頼に複数段階が含まれるなら全体のGoalまで継続する。依頼外の次Taskには進まない。LoopはGoal / Failureを基準とし、既存Retry Budgetを守る。

## Test lifecycle
- テストは機能の責務・Failureごとに適度な大きさのTest Moduleへまとめ、異なる責務や実Unity E2Eを巨大な1ファイルに押し込まない。テスト数やファイル数を削減目的だけで変更しない。
- 調査や修復のための一時TestはTask専用Worktree／TemporaryDirectory等で実行し、Task終了時に不要な作業ファイルを清掃する。セッション終了イベントだけにCleanupを依存させない。
- 恒久的なRegression Testは、既存Testとの差分・保護Invariant・Failureリスク・実行/保守コストを通常PRに記載して審査する。Eval起点なら既存ChangeProposalに紐付け、新しい承認機構を追加しない。
- 既存テストの置換はB案。移行対象だけを `tests/delete/` に原本のまま凍結し、最小スイートへの置換と重要な負例の検出を検証してから削除する。凍結TestをCanonicalのPASSとして扱わず、未置換の旧テストは通常Gateで維持する。詳細は `tests/delete/README.md`。
- テスト追加・変更・統合・採用・セッション限定ProbeのCleanupには `.agents/skills/test-lifecycle/SKILL.md` を適用する。Stage A/B/Cはリスク条件付き審査であり、Skillは独立した承認権限を持たない。Task終了／最終報告前にRun所有Temporaryの残存を確認する。

Skillが確認要求・停止・ユーザー要求との競合を生む場合、Skill path、該当instruction、effect、判断理由を明示する。
Policy追加の前にKnowledge / Retrieval / Tool / Harness / Eval / Architectureの原因を調べる。

## Canonical map
| 必要な情報 | 正本 / 入口 |
|---|---|
| Repository authority / mirrored declarations | `src/unityagent/contracts/repository-authority-map.yaml` / `tools/repository_authority_validator/validate_repository_authority.py` |
| Git branch policy | `.github/branch-policy.json` / `tools/branch_policy/validate_branch_policy.py` |
| User preferences / Comments | `src/unityagent/policy/user/user-policy.yaml` |
| Risk / Approval / Evidence | `src/unityagent/policy/risk/` / `src/unityagent/policy/approval/` / `src/unityagent/policy/evidence/` |
| Route / Graph / Task boundary | `src/unityagent/orchestration/routing/` / `src/unityagent/orchestration/definitions/` / `src/unityagent/orchestration/contracts/task_contracts/` |
| Context / Retrieval / Compression | `src/unityagent/context/selection/` / `src/unityagent/context/budget/` / `src/unityagent/context/manifest/` |
| Task workflow / Unity knowledge | `.agents/skills/` / `docs/standards/` |
| Naming contract / Golden checks | `docs/standards/TYPE_NAMING_STANDARDS.md` / `eval/golden/validate_naming_grader.py` |
| SubAgent identity / activation | `src/unityagent/runtime/reference_implementation/subagent-catalog.yaml` |
| Execution backend Provider | `src/unityagent/runtime/tooling/provider_registry.yaml` / `src/unityagent/runtime/tooling/providers/` |
| Execution / Tools / Validation | `src/unityagent/runtime/runner/` / `src/unityagent/runtime/tooling/` / `src/unityagent/runtime/harnesses/` |
| State / Resume / Evidence | `src/unityagent/persistence/state/` / `src/unityagent/persistence/resume/` / `src/unityagent/persistence/evidence/` |
| Operations | `src/unityagent/operations/` |
| Actual Behavior / Golden / Regression | `eval/behavior/` / `eval/golden/` / `tools/run_regression_gate.py` |
| Local repository validation | `tools/validate_all.py` |
| Architecture boundaries / handoff | `docs/architecture/architecture.md` |
| Five-layer dependency contract | `src/unityagent/contracts/unityagent-layer-contract.yaml` / `tools/layer_boundary_validator/validate_layer_boundaries.py` |
| Local Unity project use | `docs/local-project-development.md` / `docs/templates/DevelopmentRequest.md` |

## ドキュメント作成・更新
- `docs/` の説明文、見出し、表、図の表示文、手順は原則として**日本語**で記述する。既存英語文書を更新する場合も、変更箇所と関連説明を日本語へ揃える。
- プルリクエストの番号・タイトル・一時的な依存順序を、恒久的な仕様文書の見出し・識別子・本文に使わない。代わりに安定したファイルパス、設計判断、契約名、Commit SHA、実行した検証の証拠へ参照を張る。
- 型名、API、コード、環境変数、コマンド、ファイルパスなど機械的な識別子は改名せず、正確な表記を維持する。
- 執筆・整理方針の詳細は `docs/README.md` を参照する。

## Completion and invariants
- Policy defines; Orchestration decides; Context materializes; Runtime executes; Persistence remembers; Operations observes/controls; Eval measures/proposes.
- Runtime capture becomes durable Evidence only after Persistence append. Checkpoint、Memory、Evidenceを混同しない。
- Unknown Project Fact / Bindingを推測で補完しない。legacy path fallbackやGolden期待値のProduction Prompt注入を行わない。
- Static / Compile / Editor / Player / 実機 / Visual / Performanceの検証状態を分け、未観測は`not_observed`、利用不可は`unavailable`として報告する。
- Goal達成、変更差分、実施した検証、残る制約を報告する。実行不能な必須Gateを成功扱いしない。
- SubAgentの `profile_id` が専門Agentの正本IDであり、`provider_id` は実行BackendのIDに限定する。Artistの正本名は `artist_subagent` / `ArtistSubAgent`、実行Backendは `unity_cli`。旧 `unity_artist_cli` は新規Providerとして登録せず、実行依存へ戻さない。
- Specialist の選出は Orchestration、型付き Fact / 明示 Decision / Skill / Policy の選別と Budget 記録は既存 Context Assembly が行う。未観測の項目や Budget `unmeasured` を実行可能として扱わない。詳細は `docs/architecture/specialist-context-assembly.md`。
- SubAgentはoptional installとし、未インストール・未Bind・非互換・必要Environment Fact未成立のSubAgentを候補から除外する。RuntimeはCapabilityを満たすためにSubAgentを自動インストールしない。
- UI / CodexはSubAgentやProviderへ直接到達しない。必ずEntry → UnityAgent Control Plane → Capability / Policy → SubAgent Resolver（必要時）→ Runtime Handoffを通る。Tool CapabilityはBackend Provider Resolver、Providerless reasoningはCodexRunnerを経由し、Evidenceへ到達する。
- Setupは `unity-agent doctor → setup plan → approval → setup apply` の順序で行い、InstallReceiptとEvidenceを残す。
- Host Control PlaneはGitHubのremote bootstrapから直接導入できる。UPM PackageとCodex Pluginは同じGitHubリポジトリの別Entryとして扱い、bootstrapがProviderを直接実行しない。
