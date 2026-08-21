# UnityAgent

Unity / C# / URP / RenderGraph / Shader / Performance / Visual DirectionのDomain Skill、Knowledge Contract、Task Contract、Standards、Validatorと、**ユーザー固有のUnity開発Policy**を管理する正本Repositoryです。

UnityAgentは汎用的なUnity Best Practice集ではありません。ユーザーが決めた設計思想、ファイル粒度、コメント品質、禁止事項、安全境界を、外部記事や一般的推奨より優先して適用する個人専用Unity開発Agentです。

汎用の実行モード、Task Graph、Retry、Token Budget、Checkpoint、Human Gateは`DarumaPPAP/Unity-Graph-Engineering`が所有します。

## Source of truth

- `DarumaPPAP/UnityAgent`: ユーザー固有Policy、Unity Domain Skill、圧縮Knowledge YAML、Task Contract、Quality Gate、Validator
- `DarumaPPAP/Unity-Graph-Engineering`: Prompt / Graph-Loop実行、Budget、State、Recovery、Human Gate
- `DarumaPPAP/MyUnityMCP`: UnityAgentMCP、Creator Workflow、Domain MCP、Capability Module、Catalog、Manifest、Tool Schema、Package実装
- `DarumaPPAP/UnityAIGC-Archive`: 生成した製品コード、製品仕様、導入資料
- `DarumaPPAP/Beautiful-Definition`: Visual Intent、Beauty Definition、Human feedback
- `DarumaPPAP/Unity-Knowledge-Products`: 人間向けHTML、詳細解説、実験、Decisionを置く予定の知的資産Repository
- Google Drive: PDF、PowerPoint、画像、動画、Capture、外部資料の原資料庫

UnityAgent内へ長い技術解説や製品Feature用の新しい`Implementation/`または`Specs/`を作成しません。

## User policy authority

ユーザー固有Policyの正本は`.ai/user-policy.yaml`です。

```text
今回のユーザー明示指示
  ↓
UnityAgent User Policy
  ↓
Project固有Policy
  ↓
Unity Domain Standard
  ↓
外部Reference
  ↓
一般的Best Practice
```

Projectから検出した事実とユーザーのPreferenceは分離します。対象ProjectのUnity Version、Render Pipeline、既存namespaceなどの事実は推測しません。一方、ファイル分割、過剰設計防止、日本語コメント、Team Safe ImportなどのユーザーPolicyは一般論で上書きしません。

古いPolicyは現在のPolicyへ自動マージしません。競合時は現在のPolicyを保持し、古い重複・廃止情報を削除します。

コメント体系は保護対象です。

- 本番コード: `production-code-comments`
- 学習・コードリーディング: `learning-code-comments`
- コメント品質監査: `comment-quality-reviewer`

## Execution profiles

入口は`.ai/execution-profiles.yaml`です。

| Profile | 用途 | Project Context |
|---|---|---|
| `generic_planning` | Project非参照の設計、Portable Package、外部Authoring | 不要 |
| `personal_full_control` | 個人Projectの直接実装、Unity検証、Git | Optional |
| `team_safe_import` | 会社Projectへの一方向Staging Import | 使用禁止 |

### Generic Planning

Unity Version、Render Pipeline、Goal、Constraints、禁止事項、期待結果の最小手動入力だけで計画できます。Target PlatformはPlatform固有API、Build、互換性または性能主張がある場合だけ必須です。Project固有Path、Scene、Renderer Data、Layer、ShaderTagは推測せず、未解決Bindingとして残します。

### Personal Full-Control

Project Context GeneratorやUnity Command Surfaceは、Source探索と検証を高速化するOptional Toolです。利用不能でもTaskを中止せず、手動要件とSourceから継続します。Credentialや秘密鍵などのSecretはFull Access時も収集対象外です。

### Team Safe Import

Personal版とは別Packageを前提とし、Project Scanner、Source Export、Screenshot、Hierarchy、Unity Project ID、Git、Issue、Cloud、Environment Variable、組織情報、顧客情報へのアクセス機能を持たせません。会社固有情報は`redacted`項目としてもSchemaへ作りません。

## Execution integration

```text
User Request
  ↓
Unity-Graph-Engineering Execution Router
  ↓
UnityAgent Execution Profile
  ↓
UnityAgent User Policy
  ↓
One Primary Domain Route
  ↓
One Task Contract
  ↓
One Context Pack
  ↓
Zero or One Primary Knowledge Contract
  ↓
Target Source or Portable Output
```

無指定TaskはPrompt Engineeringです。UnityAgentはGraph / Loopへの無断変更、汎用State Machine、Token Budget管理を行いません。

## Context Engineering

Unity Domain Routingの唯一の入口は`.ai/context-index.yaml`です。Context側は「今回AIへ何を渡すか」、Harness側は「何を変更でき、何を検証し、どこで止めるか」を所有します。

```text
.ai/
├─ user-policy.yaml
├─ context-index.yaml
├─ context-manifest.schema.yaml
├─ execution-profiles.yaml
├─ context-packs/
│  ├─ architecture-design.yaml
│  ├─ graphics-mcp.yaml
│  ├─ csharp-local-fix.yaml
│  ├─ rendering-incident.yaml
│  ├─ shader-change.yaml
│  ├─ renderer-feature-change.yaml
│  ├─ performance.yaml
│  ├─ asset-data-change.yaml
│  ├─ portable-feature.yaml
│  └─ visual-direction.yaml
├─ knowledge/
│  ├─ knowledge.schema.yaml
│  ├─ index.yaml
│  └─ rendering/
├─ harness/
│  ├─ task-contracts/
│  │  ├─ task-contract.schema.yaml
│  │  ├─ architecture-design.yaml
│  │  ├─ graphics-mcp.yaml
│  │  ├─ csharp-local-fix.yaml
│  │  ├─ rendering-incident.yaml
│  │  ├─ shader-change.yaml
│  │  ├─ renderer-feature-change.yaml
│  │  ├─ performance-experiment.yaml
│  │  ├─ asset-data-change.yaml
│  │  ├─ portable-feature.yaml
│  │  ├─ safe-import-integration.yaml
│  │  └─ visual-direction.yaml
│  ├─ quality-gates.yaml
│  ├─ mutation-channels.yaml
│  ├─ risk-levels.yaml
│  └─ mcp-activation.yaml
└─ knowledge-graph-pilot.yaml
```

全Skill、全Reference、全Knowledgeを一括で読みません。Primary Domain Route、Task Contract、Context Pack、Primary Domain Skillをそれぞれ一つに限定し、Related KnowledgeとConditional Operationは条件成立時だけ追加します。

旧Supervisor / Skill Routing互換AdapterはPhase 4で削除済みです。過去互換情報はGit履歴だけをArchiveとし、Routing正本へ戻しません。

## Harness Engineering

`.ai/harness/`はUnity固有の実行制約と検証契約を所有します。

- `task-contracts/`: Taskごとの入力、許可Mutation、禁止Mutation、必須Gate、完了条件、Stop条件
- `quality-gates.yaml`: Static / Compile / EditMode / PlayMode / Player / Rendering / Performance / Target Device等のEvidence境界
- `mutation-channels.yaml`: C#、Shader、Scene、Prefab、Material、Package、Project Settingsの正規変更経路
- `risk-levels.yaml`: R0〜R4とMutation RiskのEscalation
- `mcp-activation.yaml`: MyUnityMCPのCatalog、Manifest、Tool Groupを段階的に公開するActivation Policy

Loop / Graph / Retry / Checkpoint / Token BudgetはHarnessへ戻さず、`DarumaPPAP/Unity-Graph-Engineering`を正本とします。

## Architecture intelligence

新規Feature、System、C#ファイル構成、MonoBehaviour / Plain C# / ScriptableObject / ECSの境界判断には`architecture-design` Routeを使用します。

- 小規模機能はSingle Cohesive Script First
- 新規ファイルごとにSplit Reasonを要求
- Pattern名、hypothetical reuse、Mock可能性、行数だけでは分割しない
- Controller、Manager、Service、Interface、ScriptableObjectの必要性を明示的に審査
- データ並列処理ではECS、Jobs、Burst案を積極評価
- ECS Component、Tag、Aspect、Jobを1型1ファイルへ機械的に分割しない
- Architecture Decisionへ採用案、不採用案、File Plan、再評価条件を残す

判断Policyの正本は`.ai/user-policy.yaml`と`SkillReferences/ARCHITECTURE_DECISION_POLICY.md`です。

## Knowledge boundary

### UnityAgent YAML

AI実装に直接必要な圧縮契約だけを保持します。

- 使用条件
- 必須入力
- 実装契約
- 禁止事項
- 関連Knowledge
- Evidence
- Stop条件
- Human Reference ID

### Unity-Knowledge-Products

人間向けのHTML、図、詳細解説、比較、実験、Failure Signature、Decision、Platform差を保存します。AIは設計理由や実験値が必要な場合だけ参照します。

### Google Drive

PDF、PowerPoint、画像、動画、Profiler／GPU Captureなどの原資料を保存します。

## Task contracts

| Contract | 主用途 |
|---|---|
| `architecture-design` | 新規Feature/System、ファイル粒度、MVP/MVVM/SO/ECS選定 |
| `graphics-mcp` | MyUnityMCPのGraphics Domain、Creator Workflow、Capability設計 |
| `csharp-local-fix` | 確定済みの局所C#修正 |
| `rendering-incident` | 原因不明の描画、RenderGraph、Editor / Player差 |
| `shader-change` | ShaderLab、HLSL、Compute |
| `renderer-feature-change` | RendererFeature、Pass、Resource連携 |
| `performance-experiment` | Baseline付き性能実験 |
| `asset-data-change` | Scene、Prefab、Material、Serialized Asset |
| `portable-feature` | Project非依存のUPM Package／外部Authoring |
| `safe-import-integration` | Team用一方向Staging Import |
| `visual-direction` | Lighting、Composition、LookDev、Capture、Human Review |

## Capability-independent validation

Quality Gateの結果は`passed`、`failed`、`unavailable`です。

- `unavailable`はTask失敗ではありません。
- `unavailable`を成功と報告しません。
- 環境待ちは`unavailable`と`reason_code: deferred-environment`で表現します。
- 実行できないGateは理由と残作業へ移します。
- Compile成功だけでRuntime、Visual、Performance、実機を保証しません。
- Architecture用Gateとして`architecture_fit`、`file_granularity`、`ownership_and_lifetime`、`ecs_data_layout`を使用します。

## Mutation channels

- C#／Shader: Source Patch
- Scene／Prefab: Connected Editor CommandまたはEditor Script
- Material: SerializedObjectまたはEditor Command
- Package: PackageManager ClientまたはPortable UPM Package
- Project Settings／Render Pipeline Asset: Editor APIと明示承認
- Raw Scene／Prefab／Material YAML編集: 禁止

## Validation

Skill構造Validator:

```bash
python Tools/SkillValidator/validate_skills.py
python Tools/SkillValidator/validate_skills.py --strict
python Tools/SkillValidator/validate_skills.py --json
```

Knowledge／Task Contract Validator:

```bash
python Tools/ContractValidator/validate_contracts.py
python Tools/ContractValidator/validate_contracts.py --json
```

Context Pack Validator:

```bash
python Tools/ContextPackValidator/validate_context_packs.py
```

Canonical Route Graph／User Policy Validator:

```bash
python Tools/RouteGraphValidator/validate_route_graph.py
```

Routing Case:

```text
Tests/ContractValidator/routing-cases.yaml
Tests/ContextRouting/cases.yaml
```

## TAA Knowledge Pilot

最初のKnowledge Product Pilotとして次を追加しています。

```text
.ai/knowledge/rendering/temporal-anti-aliasing.yaml
```

Motion Vector、Transparent、Outline、UI Composition、Shader VariantはRelated Knowledge Stubとして追加し、TAA Taskで条件成立時だけ読み込みます。

## Target KPI

- Framework Token: 50%以上削減
- Accepted Task総Token: 30%以上削減
- Context File Read: 30%以上削減
- Verifier品質低下: 0
- Missed Dependency悪化: 0
- 未検証の成功報告: 0
- ユーザー固有Policyの欠落: 0

削減率は公開事例ではなく、同じUnity TaskとSource revisionによるA/B比較で判断します。
