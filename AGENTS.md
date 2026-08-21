# UnityAgent Domain Bootstrap

UnityAgentはUnity / C# / URP / RenderGraph / Shader / Performance / Visual DirectionのDomain Knowledgeと、ユーザー固有の設計思想・運用規則の正本です。UnityAgentMCP、Creator Workflow、Domain MCP、Capability Moduleの仕様と実装は`DarumaPPAP/MyUnityMCP`が所有します。汎用の実行モード、Task Graph、Retry、Token Budget、Checkpointは`DarumaPPAP/Unity-Graph-Engineering`が所有します。

## 0. User policy authority

UnityAgentは汎用Best Practiceを適用するためのAgentではなく、ユーザー専用Unity開発Agentです。今回のユーザー明示指示と`.ai/user-policy.yaml`を、一般的推奨、外部記事、他Agentの既定設計より優先します。

優先順位:

1. 今回のユーザー明示指示
2. `.ai/user-policy.yaml`
3. 対象Project固有Policy
4. Unity Domain Standard
5. 外部Reference
6. 一般的Best Practice

Projectから検出した事実とユーザーPreferenceを混同しない。Unity Version、Render Pipeline、既存namespaceなどの事実は対象Projectを優先し、ファイル粒度、過剰設計防止、日本語コメント、Team Safe Import、安全境界などのユーザーPolicyは一般論で上書きしない。

- 古いPolicyを現在のPolicyへ自動マージしない。
- 競合時は現在のPolicyを保持して報告する。
- 古いSourceにしかない現行User Policyだけを移行してから古いSourceを削除する。
- コメント体系、ファイル粒度、Architecture Preference、Security、Team Safe Import、Rendering Preference、Validation要求、禁止事項は保護対象とする。
- Policyの削除または簡略化はユーザー承認とPolicy Loss確認を要求する。

コメント体系の正本:

- `.ai/user-policy.yaml#comment_system`
- `.agents/skills/production-code-comments/SKILL.md`
- `.agents/skills/learning-code-comments/SKILL.md`
- `.agents/skills/comment-quality-reviewer/SKILL.md`
- `SkillReferences/JAPANESE_CODE_COMMENT_STANDARDS.md`
- `SkillReferences/COMMENT_REVIEW_CHECKLIST.md`

## 1. Workspace

- このRepositoryはUnityプロジェクト本体ではない。
- `Assets/`、`Packages/`、`ProjectSettings/`を推測で作成しない。
- 通常の製品コード、製品仕様、導入資料は`DarumaPPAP/UnityAIGC-Archive`へ保存する。
- UnityAgentMCP、Creator Workflow、Domain MCP、Capability Module、MCP Manifest、Tool Schema、MCP固有仕様、MCP Package、MCP Testは`DarumaPPAP/MyUnityMCP`へ保存する。
- MCP関連の正本をUnityAgentまたはUnityAIGC-Archiveへ複製しない。
- MCPが生成または変更したScene、Prefab、Material、Timeline、Volume Profile等は対象Unity Projectが所有する。
- `Reference/`はRead-only。
- 美的正本は`DarumaPPAP/Beautiful-Definition`。
- Google Driveは原資料と大容量Evidence。編集正本はGitHub。
- 人間向けの詳細Knowledge Productは`DarumaPPAP/Unity-Knowledge-Products`を予定し、UnityAgentへ長文を複製しない。

## 2. Execution ownership

Execution Modeが未指定の場合はUnity-Graph-EngineeringのPolicyによりPrompt Engineeringを使用する。Graph / Loopへの無断変更は禁止する。

UnityAgentは次を担当する。

- User Policy
- Domain route
- Context Pack
- Knowledge Contract
- Task Contract
- ユーザー固有のコーディング・設計・Visual Direction規則
- MyUnityMCPの選択・Activation Policy
- Unity固有の実装・監査手順
- Unity固有ValidatorとEvidence要求

MyUnityMCPは次を担当する。

- UnityAgentMCP Control Plane
- Creator Workflow
- Domain MCP
- Capability Module
- MCP Catalog / Manifest / Tool Schema
- Unity Editorへ接続するPackage実装
- MCP固有Test

UnityAgentは次を担当しない。

- MCP ServerまたはMCP Tool Providerの製品実装
- 汎用Supervisor State Machine
- 汎用Task Graph
- Retry Scheduler
- Token Accounting
- Human Gate orchestration

Compatibility-only path:

- `.agents/skills/unity-production-workflow/SKILL.md`
- `SkillReferences/UNITY_AGENT_SUPERVISOR_MODEL.md`
- `SkillReferences/UNITY_SKILL_ROUTING.md`

これらはRouting入口ではない。旧State Machine、旧Lane、旧Skill選択表を再構築しない。

## 3. Execution profiles

`.ai/user-policy.yaml`を確認した後、`.ai/execution-profiles.yaml`を読み、次のProfileを選ぶ。

### Generic Planning

Projectへアクセスしない標準Profile。Unity Version、Render Pipeline、Goal、Constraints、禁止事項、期待結果の最小手動入力だけで計画とPortable成果物を作る。

- Project Contextは必須ではない。
- Capability Manifestは必須ではない。
- Target PlatformはPlatform固有API、Build、互換性または性能主張がある場合だけ必須。
- 未解決のPath、Scene、Renderer Data、Layer、ShaderTagを推測しない。
- 未解決Bindingを記録し、残りの設計と実装を継続する。

### Personal Full-Control

個人Projectで明示的に許可された場合だけ、Source、Unity Tool、Screenshot、Profiler、Gitを利用する。

- Project Context GeneratorはOptionalな加速装置。
- Generatorが失敗しても最小手動入力とSource探索から継続する。
- Credential、Private Key、Password、Environment Variable値、証明書、Keystore Secretは収集しない。

### Team Safe Import

会社Project向け。一方向のPortable Package Importだけを行う。

- Project Context Generatorを使用しない。
- Personal Packageへ依存しない。
- Project Scanner、Source Export、Screenshot、Hierarchy Export、Unity Project ID、Git、Issue、Cloud、Environment Variable、組織情報、顧客情報へのアクセス機能を持たない。
- これらの情報は`redacted`としてもSchemaへ追加しない。

## 4. Context and MCP routing

`.ai/context-index.yaml`をUnity Domain Routingの唯一の入口とし、依頼に一致するPrimary Route、Context Pack、Task Contractを一つずつ選ぶ。MCP能力が必要な場合だけ`.ai/harness/mcp-activation.yaml`を読み、MyUnityMCPのCatalogからCreatorまたはPrimary Domain MCPを一つ選ぶ。

- 全Skillを一括で読まない。
- 全Referenceを一括で読まない。
- Primary Domain Routeは一つ。
- Primary Domain Skillは一つ。
- Primary Task Contractは一つ。
- Primary Knowledgeは一つ。
- Primary CreatorまたはPrimary Domain MCPは一つ。
- Conditional Domain MCPは条件成立時だけ追加し、原則2つまでとする。
- コメント追加・監査は`.ai/user-policy.yaml#comment_system`からConditional Operationを選ぶ。
- 全MCP Manifestを一括で読まない。
- 全Tool Schemaを一括で読まない。
- 通常のMCP利用ではPackage C# Sourceを読まない。
- 選択されたManifestと、現在必要なTool Groupだけを読み込む。
- Tool Groupは`inspect`、`plan`、`mutate`、`bake`、`capture`の順で段階的に公開する。
- `mutate`は承認済みPlan、Revision、Diff、Undo、明示許可を要求する。
- `bake`は別の明示許可とDirty Dependencyを要求する。
- Conditional ReferenceとRelated Knowledgeは条件成立時だけ読む。
- 対象Sourceと直接依存を優先する。
- Knowledge Graphは候補Artifactの絞り込みにだけ使い、変更前にSourceを直接読む。
- 人間向けHTMLは設計理由、比較、実験、Visual Reference、Decision履歴が必要な場合だけ読む。
- Route不一致時に旧Routing文書へFallbackしない。

Context Pack:

- `.ai/context-packs/architecture-design.yaml`
- `.ai/context-packs/graphics-mcp.yaml`
- `.ai/context-packs/csharp-local-fix.yaml`
- `.ai/context-packs/rendering-incident.yaml`
- `.ai/context-packs/shader-change.yaml`
- `.ai/context-packs/renderer-feature-change.yaml`
- `.ai/context-packs/performance.yaml`
- `.ai/context-packs/asset-data-change.yaml`
- `.ai/context-packs/portable-feature.yaml`
- `.ai/context-packs/visual-direction.yaml`

Task Contract:

- `.ai/harness/task-contracts/architecture-design.yaml`
- `.ai/harness/task-contracts/graphics-mcp.yaml`
- `.ai/harness/task-contracts/csharp-local-fix.yaml`
- `.ai/harness/task-contracts/rendering-incident.yaml`
- `.ai/harness/task-contracts/shader-change.yaml`
- `.ai/harness/task-contracts/renderer-feature-change.yaml`
- `.ai/harness/task-contracts/performance-experiment.yaml`
- `.ai/harness/task-contracts/asset-data-change.yaml`
- `.ai/harness/task-contracts/portable-feature.yaml`
- `.ai/harness/task-contracts/safe-import-integration.yaml`
- `.ai/harness/task-contracts/visual-direction.yaml`

## 5. Minimum project facts

Project ContextやUnity Toolがなくても計画を止めない。最低限、依頼または手動定義から次を得る。

- Unity Version
- Render Pipeline
- RenderGraph使用有無
- Goal
- Constraints
- Prohibited Changes
- Expected Result

Target PlatformはPlatform固有API、Build、互換性または性能主張がある場合だけ追加する。

対象Repositoryへアクセスできる場合は、既存コード、asmdef、Feature Spec、Project Contextから追加事実を確定する。

- Render Pipeline Version
- Graphics API
- Editor / Player
- Mono / IL2CPP
- Burst / Jobs / Entities
- Root Namespace
- Build / Test方法
- 実機Evidenceの有無

Repositoryから確定できる情報を質問し直さない。確認できない条件は推測せず、未解決Bindingまたは未検証Gateとして記録する。

## 6. Knowledge boundary

UnityAgentの`.ai/knowledge/`にはAI実装用の圧縮契約だけを置く。

- 使用条件
- 必須入力
- 実装契約
- 禁止事項
- 関連Knowledge
- 必須Evidence
- Stop条件
- Human Reference ID

長い解説、画像、資料全文、Source要約のDump、実験画像は置かない。詳細Knowledgeの正本はUnity-Knowledge-Products、原資料の正本はGoogle Driveとする。MCPの長い仕様、Manifest、Tool Schema、Package SourceはMyUnityMCPを正本とする。

## 7. Capability-independent validation

Quality Gateの結果は`passed`、`failed`、`unavailable`のいずれか。

- `unavailable`はTask失敗ではない。
- `unavailable`を成功として報告しない。
- 環境待ちは`unavailable`と`reason_code: deferred-environment`で表現する。
- 実行できないGateは理由と残作業へ移す。
- Compile成功だけでRuntime、Visual、Performance、実機を承認しない。
- AIの自己申告だけをEvidenceにしない。

## 8. Non-negotiable C# constraints

- 既存コード変更では既存namespaceを保持する。
- Root Namespaceありは`<RootNamespace>.<FeatureName>`、なしは`<FeatureName>`。
- `Namespace`、`RootNamespace`、`CHANGE_ME`、先頭・末尾`.`を実出力しない。
- private fieldは`_camelCase`。
- enumは`E_UPPER_SNAKE_CASE`。
- structは必要時のみ`S_UPPER_SNAKE_CASE`、原則`readonly struct`。
- constは`SCREAMING_SNAKE_CASE`。
- Runtimeから`UnityEditor` APIを参照しない。
- Editor機能はEditor FolderまたはEditor-only Assemblyへ隔離する。
- Unity上で独立してアタッチ、生成、参照されるMonoBehaviour、ScriptableObject、EditorWindow等は原則1 File 1 Primary Unity Type。
- private補助型、Feature専用Enum、Result、Comparer、Job、ECS Component、Tag、Aspect、System専用型を無条件に別ファイルへ分離しない。
- 新規C#ファイルごとにSplit Reasonを持つ。hypothetical reuseは分離理由にしない。
- 小規模機能へMVP、Controller、Service、Profileを機械的に適用しない。
- 1実装しかないInterfaceは、外部境界または実在するVariation Axisがなければ作らない。
- ScriptableObjectは独立したAsset Identity、共有、差し替え、Authoring要件がある場合だけ作る。
- asmdefは境界が必要な場合だけ追加する。
- mutable static状態、static event、Singleton、Service Locatorを安易に追加しない。
- 不要なController、Manager、Setup、自動探索、Fallback、Cache、Debug UIを追加しない。
- public API、SerializeField、Prefab、Scene、Save Data互換性を無断変更しない。
- コメントは日本語で意図、制約、所有権、寿命、実行順、危険箇所を必要な密度で書く。
- 本番用と学習用のコメント密度を混同しない。

詳細は選択Context Packから対応Referenceを読む。新規Architectureまたはファイル構成判断では`SkillReferences/ARCHITECTURE_DECISION_POLICY.md`を必ず読む。

## 9. Architecture and ECS constraints

- Architecture PatternはProject全体ではなく問題領域ごとに選ぶ。
- Single Cohesive Script Firstを既定とし、最小構成で成立するかを先に評価する。
- Controller、Manager、Coordinator、Serviceは状態、順序、Lifetime、Resource、複数参加要素の調停を実際に所有する場合だけ作る。
- 行数だけでC#ファイルを分割しない。
- データ並列処理ではECS、Jobs、Burst案を評価対象から除外しない。
- ECS Component、Tag、Aspect、Jobを1型1ファイルへ機械的に分割しない。
- Productionで性能Architectureを採用する場合はBaseline、Before / After、品質条件、Revert条件を持つ。
- Architecture Decisionには採用案、不採用案、File Plan、Split Reason、再評価条件を含める。

## 10. Rendering / Shader constraints

- Unity / URP Versionを確認せず別VersionのAPIを移植しない。
- RendererFeatureではInjection Point、Queue、Layer、ShaderTag、Sorting、Resource read/writeを確認する。
- RenderGraphとCompatibility APIを無計画に混在させない。
- Shader名、Property、Keyword、Pass、LightMode、RenderState、CBUFFERを無断変更しない。
- 新Pass追加より既存Pass、RendererList filtering、RenderQueue、Layer、ShaderTagを先に検討する。
- Motion Vector、Depth、History UV、Reprojection、Disocclusionを安易に低精度化しない。
- `if`、`loop`、`half`、`discard`を一律禁止しない。
- Shader PatternだけでGPU時間を断定しない。
- Variant削減前にRuntime Keyword、Addressables、AssetBundle、Resources、Strict Variantを確認する。
- Editor結果だけでPlayer、Switch、Console実機を保証しない。

## 11. Audit, mutation, evidence

- Read-only AuditとMutationを分離する。
- 原因未確定のIncidentで複数箇所を同時変更しない。
- 一つのPatchにつきTask、Confirmed Finding、主要仮説のいずれか一つを扱う。
- 性能変更はBefore / After、品質条件、Revert条件を持つ。
- Scene、Prefab、MaterialはRaw YAMLで直接変更しない。
- PackageはPackageManager ClientまたはPortable UPM Packageを使用する。
- Project Settings、Renderer Data、Render Pipeline Assetの変更には明示承認を要求する。
- MCPのRead-only ToolがScene、Asset、Timeline、ProfileをDirtyにしてはならない。
- MCPのMutationはTransaction単位とし、Automatic Saveを禁止する。

## 12. Visual boundary

美しいScene、Lighting、Composition、Color、Atmosphere、Camera presentationでは`unity-visual-direction`を使用し、必要なBeautiful-Definitionだけを取得する。

- Visual Intentなしに美しさを推測しない。
- Compile、Capture生成、Light数、Bloom、FogをBeauty Evidenceにしない。
- Human reviewなしに`VISUAL_ACCEPTED`としない。
- 固有Character、Logo、Architecture、配置を直接複製しない。

## 13. Generated artifacts and MCP ownership

UnityAgentを参照して生成した通常の製品FeatureはUnityAIGC-Archiveへ保存する。UnityAgent内の製品Feature用`Implementation/`または`Specs/`へ新規生成しない。

UnityAgentMCP、Creator Workflow、Domain MCP、Capability Module、Catalog、Manifest、Tool Schema、Package Source、MCP固有仕様とTestはMyUnityMCPへ保存する。UnityAgentまたはUnityAIGC-Archiveへこれらを新規生成しない。

MCPが対象Unity Projectへ生成・変更するScene、Prefab、Material、Shader、RendererFeature、Timeline、Volume Profile、Lighting Data等は対象Unity Projectが所有する。明示的なExport依頼なしに外部Repositoryへ複製しない。

Generic PlanningのPortable成果物はProject固有Pathや名前を持たず、Integration Contract、未解決Binding、Validation手順を含める。Setup Wizardや環境構築はユーザーが明示した場合だけ成果物へ含める。

## 14. Completion contribution

Domain SkillはExecution Ownerへ次を返す。

- 適用したUser Policy
- Execution Profile
- Primary Domain Route
- Task Contract
- Confirmed context
- 適用したContext Pack
- Primary Knowledgeと追加Related Knowledge
- 選択したCreatorまたはPrimary Domain MCP
- 選択したTool Group
- Domain findings
- Mutation constraints
- Required validation
- Evidence status
- Unavailable Gateと残作業
- Compatibility / Revert条件

実行モード、Graph State、Budget、Human Gateの最終管理はUnity-Graph-Engineeringへ委譲する。
