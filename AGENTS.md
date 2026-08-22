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
8. `.ai/context-budget.yaml`に従ってRetrieved Contextを計測し、必要なら許可されたSourceだけを圧縮して再計測する。Mutationでは`within_budget`になるまで進めない。
9. MCP能力が必要な場合だけ`.ai/harness/mcp-activation.yaml`から必要Tool Groupを段階的に公開する。
10. `.ai/harness/`のMutation ContractとRequired Quality Gateで結果を検証する。
11. Evidenceを`passed` / `failed` / `unavailable`で返し、未検証範囲を成功扱いしない。
12. Primary Routeを選んでDomain Taskを実行する場合は`.ai/context-manifest.schema.yaml`に従うContext Manifestを標準Traceとして生成し、Context Budget Report、stable ID、typed edge、provenanceを保持する。Primary Route不要の単純read-only説明だけは省略できる。
13. User Policy、Routing、Context Pack、Context Budget、Task Contract、Quality Gate、Eval Contractを変更する場合は`.ai/eval/golden-eval-contract.yaml`と`Tests/GoldenTasks/`の関連Regressionを確認し、以前Acceptedだった挙動を壊していないか検証する。
14. Loop / Graph / Retry / Model・Execution Budget / Checkpoint / Human Gateは`DarumaPPAP/Unity-Graph-Engineering`へ委譲する。

## 3. Canonical map

| Area | Canonical Source | Responsibility |
|---|---|---|
| User Policy | `.ai/user-policy.yaml` | ユーザー固有の正しさ、Preference、禁止事項 |
| Execution Profile | `.ai/execution-profiles.yaml` | Generic / Personal / Team Safeの実行境界 |
| Domain Routing | `.ai/context-index.yaml` | Task Fingerprint、Primary Route、Pack、Contract、Skill選択 |
| Context Budget | `.ai/context-budget.yaml` | Retrieval Budget、Context推定量、Compression許可範囲、Mutation前Budget Gate |
| Context Trace | `.ai/context-manifest.schema.yaml` | Primary Route実行ごとのContext、Budget、Attempt、Evidence追跡 |
| Graph Projection | `.ai/graph-contract.yaml` | Definition / Execution / Regression GraphのNode、Edge、Provenance、Visualization契約 |
| Golden Regression | `.ai/eval/` + `Tests/GoldenTasks/` | Accepted Behavior、Boundary Pair、Grader、Failure Taxonomy、Regression契約 |
| Context Packs | `.ai/context-packs/` | TaskごとのRequired / Conditional / Excluded Context |
| Knowledge | `.ai/knowledge/` | AI実装用の圧縮Knowledge Contract |
| Harness | `.ai/harness/` | Task Contract、Mutation、Risk、Quality Gate、MCP Activation |
| Domain Skills | `.agents/skills/` | Unity固有の実装・調査・監査手順 |
| Human Standards | `SkillReferences/` | 詳細Coding、Formatting、Architecture、Rendering等のReference |
| Project Fallback | `Specs/ProjectProfile.md` | Project未接続時の補助情報。検出済みFactより弱い |

旧Supervisor / Skill Routing互換AdapterはPhase 4で削除済みです。過去互換情報はGit履歴だけをArchiveとし、Runtime Routingへ戻しません。

## 4. Repository ownership

- `DarumaPPAP/UnityAgent`: User Policy、Context、Context Budget / Retrieval / Compression Contract、Unity Harness Contract、Domain Skill、Validator、Golden Eval、Context Manifest Runtime、Graph Projection Contract。
- `DarumaPPAP/Unity-Graph-Engineering`: Execution Mode、Loop / Graph、Retry、State、Model・Execution Budget、Checkpoint、Human Gate、Model比較実行。
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
- Context ManifestへCanonical YAML全体や前Attempt全体を複製せず、今回選択したContextと前Attempt Failure要約だけを記録する。
- Retrieval Budgetは実測可能なArtifact数とUTF-8 byteを基準にし、estimated tokenを正確なModel Token数として報告しない。
- Local Repository Sourceは実ファイルから自動計測できる。Project SourceとExternal SourceはSource Revision付きObservationを必要とする。
- User Policy、Context Pack、Primary Skill、Task Contract、Project FactをLossy Compressionしない。
- Target Source、Direct Dependency、Required / Conditional ContextはSource Revisionと選択Rangeを保持したLossless Excerptだけを許可する。
- Semantic SummaryはKnowledge、Background Reference、Previous Failureなど非Authoritative Contextへ限定する。
- Required ContextをBudget都合で無言削除しない。Hard Limitを満たせない場合は`blocked`として停止する。
- Mutation TaskはContext Budgetが`within_budget`でなければ開始しない。

## 6. Harness guards

- Mutation可能範囲は選択Task Contractと`.ai/harness/mutation-channels.yaml`に従う。
- Riskと承認境界は`.ai/harness/risk-levels.yaml`に従う。
- Required Evidenceは`.ai/harness/quality-gates.yaml`に従う。
- Task Contractが参照するQuality GateはCanonical Gate Catalogに存在しなければならない。
- `unavailable`はFailureでもSuccessでもない。理由と残作業を記録する。
- Compile成功だけでRuntime、Visual、Performance、Player、実機を承認しない。
- AIの自己申告だけをEvidenceにしない。
- UnityAgentへ汎用Loop / Graph / Retry Schedulerを戻さない。

## 7. Graph projection guards

- Canonical YAMLをSource of Truthとし、Graphは派生Viewとして扱う。
- Graph EditorからPolicy、Context Pack、Task Contract等を直接更新する機能は、別途設計・承認されるまで無効とする。
- Nodeはstable IDとnode typeを持ち、Edgeは`requires`、`applies_policy`、`requires_gate`等のtyped edgeで意味を保持する。
- Context Manifestは一回のTask実行を表すExecution Graph Instanceとして扱い、Sourceを選択した理由とEvidence provenanceを失わない。
- Golden TaskはRegression Graphで`golden_task -> grader -> attempt -> regression_result`として追跡可能な構造を維持する。
- 将来のVisualizerはArchitecture View、Task View、Execution View、Regression Viewの4 Viewを最低限提供できる構造を維持する。

## 8. Golden Regression guards

- Golden Taskは以前Acceptedだった挙動と判断境界を保持するRegression Assetとして扱う。
- 完成Sourceの文字列完全一致を既定Graderにしない。Outcome、Invariant、Mutation Scope、Gate、Policy違反を優先して評価する。
- Deterministic Graderを優先し、Domain / Human / Model Graderは機械判定できない領域だけに限定する。
- `require` / `forbid`のBoundary Pairを維持し、ユーザーPolicyを絶対禁止Ruleへ過学習させない。
- `unavailable`をRegression PASSとして数えない。
- Agent失敗と`broken_eval`を区別する。
- Generated Eval ResultとRegression Graphは`Artifacts/GoldenEval/`へ置き、Canonical Policyへ昇格させない。

## 9. Domain detail entrypoints

詳細Ruleが必要な場合だけ、選択Context Packから対応Sourceへ進みます。

- C# / Formatting: `unity-coding-standards`、`SkillReferences/CODING_STANDARDS.md`、`SkillReferences/CODE_FORMATTING_STANDARDS.md`
- Architecture / File split / ECS: `unity-architecture-design`、`SkillReferences/ARCHITECTURE_DECISION_POLICY.md`、`SkillReferences/ARCHITECTURE_STANDARDS.md`
- Rendering / Shader: `unity-rendering`と選択Rendering Context Pack / Knowledge Contract
- Runtime Evidence / Performance: `unity-runtime-evidence`とPerformance Task Contract / Quality Gate
- Context Budget / Compression: `.ai/context-budget.yaml`、`Tools/ContextBudget/`
- Production / Learning Comment: `.ai/user-policy.yaml#comment_system`と対応Comment Skill
- Visual Direction: `unity-visual-direction`と必要なBeautiful-Definition Reference
- Golden Regression: `.ai/eval/golden-eval-contract.yaml`、`Tests/GoldenTasks/`、`Tools/GoldenEval/`

## 10. Completion handoff

Domain実行結果はExecution Ownerへ最低限次を返します。

- applied_user_policy
- execution_profile
- task_fingerprint
- selected_route
- selected_context_pack
- selected_task_contract
- primary_domain_skill
- context_manifest_id
- attempt
- confirmed_context
- context_budget_status
- estimated_context_tokens
- retrieval_bytes
- compression_summary
- mutation_constraints
- required_validation
- evidence_status
- unavailable_gates
- unresolved_bindings
- compatibility_or_revert_conditions

## 11. Anti-regression

- `AGENTS.md`へ詳細なCoding / Architecture / Rendering / Shader / Visual規約本文を戻さない。
- Rule変更はCanonical Sourceを変更し、必要なValidator / Eval / Regression Caseを更新する。
- Route選択を`triggers`やTechnology Keyword中心へ戻さない。
- Primary Route実行でContext Manifest TraceやContext Budget Traceを理由なく省略しない。
- Accepted Behaviorを変更する場合、Golden Taskを黙って削除・緩和せずユーザー指示またはPolicy変更理由を必要とする。
- Boundary Pairの片側だけを削除して絶対禁止Rule化しない。
- Graph ProjectionをCanonical Policyの正本へ昇格させない。
- stable node ID、typed edge、provenanceを将来の可視化都合だけで削除しない。
- 削除済みのLegacy Supervisor / Skill Routing Adapterを復活させない。
- Context BudgetをModel Billing / Loop Budgetの正本へ拡張しない。Context選択量の責務に限定する。
- Context / Harness / Loop / Graphの責務境界を逆流させない。
