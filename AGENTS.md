<!-- unityagent-bootstrap-map:v3 -->
# UnityAgent Bootstrap Map
> `bootstrap_map_only: true`

Unity開発の依頼を、既存構造とユーザー固有契約を保ちながら実装・検証・成果の報告まで完遂する。

## Authority
プラットフォームのSystem / Developer instructionと実行権限を上書きしない。
Repository内の優先順位は `Policy/User/user-policy.yaml#instruction_priority` を正本とする。
現在の明示要求・対象Taskの指示をSkillの一般的手順で上書きしない。
承認判断は `Policy/Approval/approval-policy.yaml` に従い、既に与えられた承認の範囲を確認する。

## Execution
1. User Policyを読み、Goal・対象範囲・完了条件を固定する。修正依頼は調査だけで終えず、変更・検証・必要な修復まで進む。
2. `Orchestration/Routing/task-routes.yaml` で意図と範囲からRouteを選び、`Context/Selection/context-catalog.yaml` で必要なContext / Skill / Task Contractだけ解決する。選択Routeの`required_policy_clauses`をPolicy provenanceとして記録する。
3. `Context/Assembly/materialize_context.py` でcurrent-call Contextを構築する。Context / Retrieval Budgetと圧縮時の必須制約保持は `Context/Budget/context-budget.yaml` に従う。
4. bounded TaskはFast Pathを使う。Graph、Local Loop、SubAgentは分解・修復・独立並列作業が必要な場合にだけ利用する。
5. Orchestrationは必要Capabilityを要求し、Runtime Tool BrokerがProviderを解決・実行する。Provider直接呼出しでApproval / Scopeを迂回しない。
6. 変更リスクと必須Gateに応じて検証する。新しい変更・失敗・未解決リスクがなければ同じPASS検証を反復しない。
7. 承認済み依頼に複数段階が含まれるなら全体のGoalまで継続する。依頼外の次Taskには進まない。LoopはGoal / Failureを基準とし、既存Retry Budgetを守る。

Skillが確認要求・停止・ユーザー要求との競合を生む場合、Skill path、該当instruction、effect、判断理由を明示する。
Policy追加の前にKnowledge / Retrieval / Tool / Harness / Eval / Architectureの原因を調べる。

## Canonical map
| 必要な情報 | 正本 / 入口 |
|---|---|
| User preferences / Comments | `Policy/User/user-policy.yaml` |
| Risk / Approval / Evidence | `Policy/Risk/` / `Policy/Approval/` / `Policy/Evidence/` |
| Route / Graph / Task boundary | `Orchestration/Routing/` / `Orchestration/Definitions/` / `Orchestration/Contracts/TaskContracts/` |
| Context / Retrieval / Compression | `Context/Selection/` / `Context/Budget/` / `Context/Manifest/` |
| Task workflow / Unity knowledge | `.agents/skills/` / `SkillReferences/` |
| Naming contract / Golden checks | `SkillReferences/TYPE_NAMING_STANDARDS.md` / `Eval/Golden/validate_naming_grader.py` |
| Execution / Tools / Validation | `Runtime/Runner/` / `Runtime/Tooling/` / `Runtime/Harnesses/` |
| State / Resume / Evidence | `Persistence/State/` / `Persistence/Resume/` / `Persistence/Evidence/` |
| Operations | `Operations/` |
| Actual Behavior / Golden / Regression | `Eval/Behavior/` / `Eval/Golden/` / `Tools/run_regression_gate.py` |
| Local repository validation | `Tools/validate_all.py` |
| Architecture boundaries / handoff | `docs/architecture/architecture.md` |
| Five-layer dependency contract | `Specs/unityagent-layer-contract.yaml` / `Tools/LayerBoundaryValidator/validate_layer_boundaries.py` |
| Local Unity project use | `docs/local-project-development.md` / `Templates/DevelopmentRequest.md` |

## Completion and invariants
- Policy defines; Orchestration decides; Context materializes; Runtime executes; Persistence remembers; Operations observes/controls; Eval measures/proposes.
- Runtime capture becomes durable Evidence only after Persistence append. Checkpoint、Memory、Evidenceを混同しない。
- Unknown Project Fact / Bindingを推測で補完しない。legacy path fallbackやGolden期待値のProduction Prompt注入を行わない。
- Static / Compile / Editor / Player / 実機 / Visual / Performanceの検証状態を分け、未観測は`not_observed`、利用不可は`unavailable`として報告する。
- Goal達成、変更差分、実施した検証、残る制約を報告する。実行不能な必須Gateを成功扱いしない。
- UI / CodexはProviderへ直接到達しない。必ずEntry → UnityAgent Control Plane → Capability / Policy / Resolver → Provider → Evidenceを通る。
- Setupは `unity-agent doctor → setup plan → approval → setup apply` の順序で行い、InstallReceiptとEvidenceを残す。
- Host Control PlaneはGitHubのremote bootstrapから直接導入できる。UPM PackageとCodex Pluginは同じGitHubリポジトリの別Entryとして扱い、bootstrapがProviderを直接実行しない。
