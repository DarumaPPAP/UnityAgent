<!-- unityagent-bootstrap-map:v1 -->
# UnityAgent Bootstrap Map

> `bootstrap_map_only: true`

`AGENTS.md`はUnityAgent起動用の地図です。詳細なCoding、Architecture、Rendering、Shader、Visual、Comment、Mutation Ruleの正本ではありません。詳細Ruleを`AGENTS.md`へ複製せず、Canonical Sourceへ委譲します。

## 1. Authority

1. 今回のユーザー明示指示
2. `.ai/user-policy.yaml`
3. 対象Project固有Policy
4. Unity Domain Standard
5. 外部Reference
6. 一般的Best Practice

ユーザー固有Policyを一般論で上書きせず、古いPolicyを自動マージしません。Project FactとPreferenceを分離し、Policyの削除・簡略化は`.ai/user-policy.yaml`の保護契約に従います。

## 2. Bootstrap sequence

1. `.ai/user-policy.yaml`を読む。
2. `.ai/execution-profiles.yaml`からExecution Profileを選ぶ。
3. `.ai/context-index.yaml#task_fingerprint`でTask Fingerprintを作り、技術名ではなくPrimary GoalとEvidenceでPrimary Routeを一つ選ぶ。
4. 選択RouteのContext Pack、Task Contract、Primary Domain Skillを一つずつ読む。Task Contractに`required_policy_clauses`がある場合は各ClauseをCanonical Sourceから適用し、Context ManifestのPolicy provenanceへcanonical `id` / `source_path`を記録する。Primary Knowledgeは必要時のみ最大一つ、Conditional Contextは条件成立時だけ追加する。
5. Mutation前に対象Sourceと必要な直接依存を読み、`.ai/context-budget.yaml`でRetrieval / Context / Compression Budgetを計測する。`within_budget`でなければMutationしない。
6. MCP能力が必要な場合だけ`.ai/harness/mcp-activation.yaml`から必要Tool Groupを段階的に公開する。
7. `.ai/harness/`のMutation Contract、Risk、Required Quality Gateで検証し、Evidenceを`passed` / `failed` / `unavailable`で返す。未検証範囲を成功扱いしない。
8. Primary Routeを使うDomain Taskでは`.ai/context-manifest.schema.yaml`に従うContext Manifestを生成し、Budget Report、stable ID、typed edge、provenanceを保持する。単純read-only説明だけは省略可能。
9. User Policy、Routing、Context Pack、Context Budget、Task Contract、Quality Gate、Eval Contract変更時は`.ai/eval/`と`Tests/GoldenTasks/`のRegressionを確認する。
10. Actual Behavior Evalを実行する場合は`.ai/eval/behavior-eval-contract.yaml`と`Tests/BehaviorEval/suites.yaml`を使い、UnityAgentはRequest / Evidence Normalization / Deterministic Grading / Regression判定だけを所有する。実Agent実行は`DarumaPPAP/Unity-Graph-Engineering`のProduction Execution Pathへ委譲する。
11. Loop / Graph / Retry / Model・Execution Budget / Checkpoint / Human Gateは`DarumaPPAP/Unity-Graph-Engineering`へ委譲する。

## 3. Canonical map

| Area | Canonical Source | Responsibility |
|---|---|---|
| User Policy | `.ai/user-policy.yaml` | ユーザー固有の正しさ、Preference、禁止事項 |
| Execution / Routing | `.ai/execution-profiles.yaml` + `.ai/context-index.yaml` | Profile、Task Fingerprint、Primary Route |
| Context | `.ai/context-packs/` + `.ai/context-budget.yaml` | Required / Conditional / Excluded Context、Budget、Compression |
| Trace / Graph | `.ai/context-manifest.schema.yaml` + `.ai/graph-contract.yaml` | Attempt、Evidence、Definition / Execution / Regression Graph |
| Golden Regression | `.ai/eval/` + `Tests/GoldenTasks/` | Accepted Behavior、Boundary Pair、Grader、Failure Taxonomy |
| Actual Behavior Eval | `.ai/eval/behavior-eval-contract.yaml` + `Tests/BehaviorEval/` + `Tools/BehaviorEval/` | Production Execution Evidenceの要求、正規化、実挙動Regression判定 |
| Knowledge | `.ai/knowledge/` | AI実装用の圧縮Knowledge Contract |
| Harness | `.ai/harness/` | Task Contract、Mutation、Risk、Quality Gate、MCP Activation |
| Domain Skills | `.agents/skills/` | Unity固有の実装・調査・監査手順 |
| Human Standards | `SkillReferences/` | Coding、Formatting、Architecture、Rendering等のReference |
| Project Fallback | `Specs/ProjectProfile.md` | Project未接続時のみ。検出済みFactより弱い |

旧Supervisor / Skill Routing互換AdapterはPhase 4で削除済みです。過去互換情報はGit履歴だけをArchiveとし、Runtime Routingへ戻しません。

## 4. Repository ownership

- `DarumaPPAP/UnityAgent`: User Policy、Context、Context Budget、Unity Harness、Domain Skill、Validator、Golden Eval、Actual Behavior Eval Contract / Suite / Normalizer / Grader、Context Manifest Runtime、Graph Projection Contract。
- `DarumaPPAP/Unity-Graph-Engineering`: Execution Mode、Production Agent Execution、Loop / Graph、Retry、State、Model・Execution Budget、Quota、Checkpoint、Human Gate、Execution Evidence transport。
- `DarumaPPAP/MyUnityMCP`: UnityAgentMCP、Creator Workflow、Capability、Catalog、Manifest、Tool Schema、Package実装。
- `DarumaPPAP/UnityAIGC-Archive`: 製品コード、製品仕様、導入資料。
- `DarumaPPAP/Beautiful-Definition`: Visual Intent、Beauty Definition、Human feedback。
- `DarumaPPAP/Unity-Knowledge-Products`: 人間向け詳細解説、比較、実験、Decision。
- Google Drive: PDF、PowerPoint、画像、動画、Profiler / GPU Capture等の原資料。

UnityAgent内へ通常の製品コード、MCP Package実装、Model Runtime、Eval専用Execution Engineを複製しません。

## 5. Context / Harness guards

- 全Skill、Reference、Knowledge、MCP Manifestを一括読込しない。Primary Route / Context Pack / Task Contract / Domain Skillは各一つを基本とする。
- Technology KeywordだけでRouteを決めず、Project Path、Scene、Renderer Data、Layer、ShaderTag、Platform条件を推測しない。
- Knowledge GraphはNavigation専用。変更前にSourceを直接確認し、Context不足は未解決Bindingとして残す。
- Context ManifestへCanonical YAML全体や前Attempt全体を複製せず、今回選択Contextと前Attempt Failure要約だけを記録する。
- Retrieval BudgetはArtifact数とUTF-8 byteを基準にし、estimated tokenを正確なModel Token数として報告しない。
- User Policy、Context Pack、Primary Skill、Task Contract、Project FactをLossy Compressionしない。Required ContextをBudget都合で無言削除しない。
- Target Source / Direct Dependency / Required ContextはRevision付きLossless Excerptのみ、Semantic Summaryは非Authoritative Contextだけに使う。Hard Limit超過は`blocked`。
- Mutation可能範囲はTask Contractと`.ai/harness/mutation-channels.yaml`、Riskは`.ai/harness/risk-levels.yaml`、Evidenceは`.ai/harness/quality-gates.yaml`に従う。
- `unavailable`はSuccessでもFailureでもない。Compile成功だけでRuntime、Visual、Performance、Player、実機を承認せず、AI自己申告だけをEvidenceにしない。
- UnityAgentへ汎用Loop / Graph / Retry Schedulerを戻さない。

## 6. Graph / Regression guards

- Canonical YAMLがSource of TruthでGraphは派生View。Graph EditorからPolicy / Context Pack / Task Contractを直接変更しない。
- Nodeはstable ID、Edgeはtyped edge、Context Manifestは一回のExecution Graph Instanceとしてprovenanceを保持する。
- Golden TaskはAccepted Behaviorと判断境界を保持するRegression Asset。完成Sourceの文字列完全一致を既定Graderにしない。
- Deterministic Graderを優先し、`require` / `forbid`のBoundary Pairを維持する。`unavailable`をPASSにせず、Agent失敗と`broken_eval`を区別する。
- Generated Eval ResultとRegression Graphは`Artifacts/GoldenEval/`へ置き、Canonical Policyへ昇格させない。
- Actual BehaviorのRequest / Envelope / Response / Diff / Generated Artifact / Reportは`Artifacts/BehaviorEval/`へ置く。Agent Self-reportを主要Evidenceにせず、Raw Behavior ArtifactをCanonical Policyへ昇格させない。

## 7. Domain detail entrypoints

- C# / Formatting: `unity-coding-standards`、`SkillReferences/CODING_STANDARDS.md`、`SkillReferences/CODE_FORMATTING_STANDARDS.md`
- Architecture / ECS: `unity-architecture-design`、`SkillReferences/ARCHITECTURE_DECISION_POLICY.md`、`SkillReferences/ARCHITECTURE_STANDARDS.md`
- Rendering / Shader: `unity-rendering` + 選択Rendering Context Pack / Knowledge
- Runtime / Performance: `unity-runtime-evidence` + Performance Task Contract / Quality Gate
- Context Budget: `.ai/context-budget.yaml`、`Tools/ContextBudget/`
- Comments: `.ai/user-policy.yaml#comment_system` + 対応Comment Skill
- Visual Direction: `unity-visual-direction` + 必要なBeautiful-Definition Reference
- Golden Regression: `.ai/eval/golden-eval-contract.yaml`、`Tests/GoldenTasks/`、`Tools/GoldenEval/`
- Actual Behavior Eval: `.ai/eval/behavior-eval-contract.yaml`、`Tests/BehaviorEval/`、`Tools/BehaviorEval/`

## 8. Completion handoff

Execution Ownerへ、適用Policy / Profile / Task Fingerprint / Route / Context Pack / Task Contract / Primary Skill / Context Manifest ID / Attempt / Context Budget / Compression / Mutation constraints / Required validation / Evidence status / unavailable gates / unresolved bindings / compatibility or revert conditionsを返します。

## 9. Anti-regression

- `AGENTS.md`へ詳細規約本文を戻さず、Rule変更はCanonical Sourceと対応Validator / Eval / Regressionを更新する。
- Route選択をTrigger文字列やTechnology Keyword中心へ戻さない。
- Primary Route実行でContext Manifest / Context Budget Traceを理由なく省略しない。
- Accepted BehaviorやBoundary Pairを黙って削除・緩和しない。
- Graph ProjectionをCanonical Policyへ昇格させず、stable node ID、typed edge、provenanceを維持する。
- 削除済みLegacy Adapterを復活させず、Context BudgetをModel Billing / Loop Budgetの正本へ拡張しない。
- Actual Behavior EvalのためにEval専用Agent Route、Model Runtime、Retry Loop、Execution EngineをUnityAgentへ追加しない。
