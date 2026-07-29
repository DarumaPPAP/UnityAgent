# UnityAgent

Unity / C# / URP / RenderGraph / Shader / Performance / Visual DirectionのDomain Skill、Knowledge Contract、Task Contract、Standards、Validatorを管理する正本Repositoryです。

汎用の実行モード、Task Graph、Retry、Token Budget、Checkpoint、Human Gateは`DarumaPPAP/Unity-Graph-Engineering`が所有します。

## Source of truth

- `DarumaPPAP/UnityAgent`: Unity Domain Skill、圧縮Knowledge YAML、Task Contract、Quality Gate、Validator
- `DarumaPPAP/Unity-Graph-Engineering`: Prompt / Graph-Loop実行、Budget、State、Recovery、Human Gate
- `DarumaPPAP/UnityAIGC-Archive`: 生成した製品コード、製品仕様、導入資料
- `DarumaPPAP/Beautiful-Definition`: Visual Intent、Beauty Definition、Human feedback
- `DarumaPPAP/Unity-Knowledge-Products`: 人間向けHTML、詳細解説、実験、Decisionを置く予定の知的資産Repository
- Google Drive: PDF、PowerPoint、画像、動画、Capture、外部資料の原資料庫

UnityAgent内へ長い技術解説や製品Feature用の新しい`Implementation/`または`Specs/`を作成しません。

## Execution profiles

入口は`.ai/execution-profiles.yaml`です。

| Profile | 用途 | Project Context |
|---|---|---|
| `generic_planning` | Project非参照の設計、Portable Package、外部Authoring | 不要 |
| `personal_full_control` | 個人Projectの直接実装、Unity検証、Git | Optional |
| `team_safe_import` | 会社Projectへの一方向Staging Import | 使用禁止 |

### Generic Planning

Unity Version、Render Pipeline、Platform、Goal、Constraints、禁止事項、期待結果の最小手動入力だけで計画できます。Project固有Path、Scene、Renderer Data、Layer、ShaderTagは推測せず、未解決Bindingとして残します。

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

入口は`.ai/context-index.yaml`です。

```text
.ai/
├─ context-index.yaml
├─ execution-profiles.yaml
├─ context-packs/
├─ knowledge/
│  ├─ knowledge.schema.yaml
│  ├─ index.yaml
│  └─ rendering/
├─ task-contracts/
│  ├─ task-contract.schema.yaml
│  ├─ csharp-local-fix.yaml
│  ├─ rendering-incident.yaml
│  ├─ shader-change.yaml
│  ├─ renderer-feature-change.yaml
│  ├─ performance-experiment.yaml
│  ├─ asset-data-change.yaml
│  ├─ portable-feature.yaml
│  └─ safe-import-integration.yaml
├─ quality-gates.yaml
├─ mutation-channels.yaml
├─ risk-levels.yaml
└─ knowledge-graph-pilot.yaml
```

全Skill、全Reference、全Knowledgeを一括で読みません。Primary Domain Skill、Task Contract、Primary Knowledgeをそれぞれ一つに限定し、Related Knowledgeは条件成立時だけ追加します。

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
| `csharp-local-fix` | 確定済みの局所C#修正 |
| `rendering-incident` | 原因不明の描画、RenderGraph、Editor / Player差 |
| `shader-change` | ShaderLab、HLSL、Compute |
| `renderer-feature-change` | RendererFeature、Pass、Resource連携 |
| `performance-experiment` | Baseline付き性能実験 |
| `asset-data-change` | Scene、Prefab、Material、Serialized Asset |
| `portable-feature` | Project非依存のUPM Package／外部Authoring |
| `safe-import-integration` | Team用一方向Staging Import |

## Capability-independent validation

Quality Gateの結果は`passed`、`failed`、`unavailable`です。

- `unavailable`はTask失敗ではありません。
- `unavailable`を成功と報告しません。
- 実行できないGateは理由と残作業へ移します。
- Compile成功だけでRuntime、Visual、Performance、実機を保証しません。

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

Routing Case:

```text
Tests/ContractValidator/routing-cases.yaml
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

削減率は公開事例ではなく、同じUnity TaskとSource revisionによるA/B比較で判断します。
