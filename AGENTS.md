<!-- unityagent-bootstrap-map:v1 -->
# UnityAgent Bootstrap Map

> `bootstrap_map_only: true`

`AGENTS.md`はUnityAgentを起動するための地図です。詳細なCoding、Architecture、Rendering、Shader、Visual、Comment、Mutation Ruleの正本ではありません。詳細Ruleを`AGENTS.md`へ複製せず、下記のCanonical Sourceへ委譲します。

## 1. Authority

適用優先順位は次の通りです。

1. 今回のユーザー明示指示
2. `.ai/user-policy.yaml`
3. 対象Project固有Policy
4. Unity Domain Standard
5. 外部Reference
6. 一般的Best Practice

- ユーザー固有Policyを一般論で上書きしない。
- 古いPolicyを現在のPolicyへ自動マージしない。
- Projectから検出したFactとPreferenceを混同しない。
- Policyの削除・簡略化は`.ai/user-policy.yaml`の保護契約に従う。

## 2. Bootstrap sequence

1. `.ai/user-policy.yaml`を読む。
2. `.ai/execution-profiles.yaml`からExecution Profileを選ぶ。
3. ユーザー要求と確認済みEvidenceから`.ai/context-index.yaml#task_fingerprint`のTask Fingerprintを作る。
4. Task Fingerprintを`.ai/context-index.yaml#routes`の`fingerprint_match`へ照合し、Primary Routeを一つ選ぶ。技術名や単語だけでRouteを決めない。
5. 選択RouteのContext Pack、Task Contract、Primary Domain Skillを一つずつ読む。
6. Primary Knowledgeは必要な場合だけ最大一つ選び、Conditional Knowledge / Operationは条件成立時だけ追加する。
7. Mutation前に対象Sourceと必要な直接依存を読む。
8. MCP能力が必要な場合だけ`.ai/harness/mcp-activation.yaml`から必要Tool Groupを段階的に公開する。
9. `.ai/harness/`のMutation ContractとRequired Quality Gateで結果を検証する。
10. Evidenceを`passed` / `failed` / `unavailable`で返し、未検証範囲を成功扱いしない。
11. Loop / Graph / Retry / Budget / Checkpoint / Human Gateは`DarumaPPAP/Unity-Graph-Engineering`へ委譲する。

## 3. Canonical map

| Area | Canonical Source | Responsibility |
|---|---|---|
| User Policy | `.ai/user-policy.yaml` | ユーザー固有の正しさ、Preference、禁止事項 |
| Execution Profile | `.ai/execution-profiles.yaml` | Generic / Personal / Team Safeの実行境界 |
| Domain Routing | `.ai/context-index.yaml` | Task Fingerprint、Primary Route、Pack、Contract、Skill選択 |
| Context Trace | `.ai/context-manifest.schema.yaml` | 今回読ませたContextとEvidenceの追跡 |
| Context Packs | `.ai/context-packs/` | TaskごとのRequired / Conditional / Excluded Context |
| Knowledge | `.ai/knowledge/` | AI実装用の圧縮Knowledge Contract |
| Harness | `.ai/harness/` | Task Contract、Mutation、Risk、Quality Gate、MCP Activation |
| Domain Skills | `.agents/skills/` | Unity固有の実装・調査・監査手順 |
| Human Standards | `SkillReferences/` | 詳細Coding、Formatting、Architecture、Rendering等のReference |
| Project Fallback | `Specs/ProjectProfile.md` | Project未接続時の補助情報。検出済みFactより弱い |

旧Supervisor / Skill Routing互換AdapterはPhase 4で削除済みです。過去互換情報はGit履歴だけをArchiveとし、Runtime Routingへ戻しません。

## 4. Repository ownership

- `DarumaPPAP/UnityAgent`: User Policy、Context、Unity Harness Contract、Domain Skill、Validator、Eval。
- `DarumaPPAP/Unity-Graph-Engineering`: Execution Mode、Loop / Graph、Retry、State、Budget、Checkpoint、Human Gate。
- `DarumaPPAP/MyUnityMCP`: UnityAgentMCP、Creator Workflow、Domain MCP、Capability、Catalog、Manifest、Tool Schema、Package実装。
- `DarumaPPAP/UnityAIGC-Archive`: 生成した製品コード、製品仕様、導入資料。
- `DarumaPPAP/Beautiful-Definition`: Visual Intent、Beauty Definition、Human feedback。
- `DarumaPPAP/Unity-Knowledge-Products`: 人間向けの詳細解説、比較、実験、Decision。
- Google Drive: PDF、PowerPoint、画像、動画、Profiler / GPU Capture等の原資料。

UnityAgent内へ通常の製品コードやMCP Package実装を複製しません。

## 5. Context guards

- 全Skill、全Reference、全Knowledge、全MCP Manifestを最初から一括読込しない。
- Primary Route / Context Pack / Task Contract / Domain Skillはそれぞれ一つを基本とする。
- HLSL、RendererFeature、ECS、Materialなどの単語が存在するだけでDomain Routeを確定しない。Primary GoalとTask Fingerprintを先に確定する。
- Project Path、Scene、Renderer Data、Layer、ShaderTag、Platform条件を推測しない。
- Knowledge GraphはNavigationにだけ使い、変更前にSourceを直接確認する。
- 人間向け長文Referenceは設計理由、比較、実験、Visual Decisionが必要な場合だけ読む。
- Context不足は未解決Bindingとして残し、無関係なContext追加で埋めない。

## 6. Harness guards

- Mutation可能範囲は選択Task Contractと`.ai/harness/mutation-channels.yaml`に従う。
- Riskと承認境界は`.ai/harness/risk-levels.yaml`に従う。
- Required Evidenceは`.ai/harness/quality-gates.yaml`に従う。
- `unavailable`はFailureでもSuccessでもない。理由と残作業を記録する。
- Compile成功だけでRuntime、Visual、Performance、Player、実機を承認しない。
- AIの自己申告だけをEvidenceにしない。
- UnityAgentへ汎用Loop / Graph / Retry Schedulerを戻さない。

## 7. Domain detail entrypoints

詳細Ruleが必要な場合だけ、選択Context Packから対応Sourceへ進みます。

- C# / Formatting: `unity-coding-standards`、`SkillReferences/CODING_STANDARDS.md`、`SkillReferences/CODE_FORMATTING_STANDARDS.md`
- Architecture / File split / ECS: `unity-architecture-design`、`SkillReferences/ARCHITECTURE_DECISION_POLICY.md`、`SkillReferences/ARCHITECTURE_STANDARDS.md`
- Rendering / Shader: `unity-rendering`と選択Rendering Context Pack / Knowledge Contract
- Runtime Evidence / Performance: `unity-runtime-evidence`とPerformance Task Contract / Quality Gate
- Production / Learning Comment: `.ai/user-policy.yaml#comment_system`と対応Comment Skill
- Visual Direction: `unity-visual-direction`と必要なBeautiful-Definition Reference

## 8. Completion handoff

Domain実行結果はExecution Ownerへ最低限次を返します。

- applied_user_policy
- execution_profile
- task_fingerprint
- selected_route
- selected_context_pack
- selected_task_contract
- primary_domain_skill
- confirmed_context
- mutation_constraints
- required_validation
- evidence_status
- unavailable_gates
- unresolved_bindings
- compatibility_or_revert_conditions

## 9. Anti-regression

- `AGENTS.md`へ詳細なCoding / Architecture / Rendering / Shader / Visual規約本文を戻さない。
- Rule変更はCanonical Sourceを変更し、必要なValidator / Eval / Regression Caseを更新する。
- Route選択を`triggers`やTechnology Keyword中心へ戻さない。
- 削除済みのLegacy Supervisor / Skill Routing Adapterを復活させない。
- Context / Harness / Loop / Graphの責務境界を逆流させない。
