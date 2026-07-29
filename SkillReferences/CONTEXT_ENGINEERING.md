# UnityAgent Context Engineering

## Goal

UnityAgentの専門知識を失わず、Taskごとに必要なSkill、Reference、Sourceだけを読み込む。

## Selection flow

```text
Execution Mode
  ↓
.ai/context-index.yaml
  ↓
One Primary Route
  ↓
One Context Pack
  ↓
Required + satisfied Conditional references
  ↓
Target Source and direct dependencies
```

## Required / Conditional / Excluded

Context Packは資料を三種類へ分ける。

### Required

Task成立に必須。対象Source、Project fact、Domain Standardなど。

### Conditional

Variant変更、RenderGraph、Burst、Visual、Runtime Measurementなど、条件が成立した場合だけ読む。

### Excluded by default

Taskと無関係なSupervisor、Visual、C# Catalog、Shader Catalogなど。必要性がEvidenceで判明した場合だけ別RouteまたはSecondary Skillとして追加する。

## Primary Skill

各StateまたはPrompt TaskでPrimary Domain Skillは一つにする。Secondary SkillはPrimaryが所有しない専門判断だけを補う。

例:

- RenderGraph errorの原因未確定: IncidentがPrimary、RenderingがSecondary
- Shaderの確定済み修正: RenderingまたはShader RefactorがPrimary
- 美的Scene設計: Visual DirectionがPrimary、RenderingがSecondary

## Context expansion

Contextを追加するAgentは次を記録する。

- 追加するArtifact
- 追加が必要な判断
- 現在のEvidenceでは不足する理由
- Expansion Hop

「念のため」で全Referenceを読み込まない。

## Knowledge Graph

Knowledge Graphは候補Artifactを選ぶNavigation Layerである。

```text
Query -> Candidate artifacts -> Direct source read -> Decision
```

禁止:

- Graphだけで原因を確定する
- 推論Edgeだけで互換性を判断する
- Graph Report全文を毎回Contextへ入れる
- Unity生成Folderを無制限にIndexする

Pilot契約は`.ai/knowledge-graph-pilot.yaml`を参照する。

## Measurement

最低限次を記録する。

- 選択Route
- Context Pack
- Initial file reads
- Expanded files and reason
- Retrieved context tokens
- Direct source tokens
- Missed dependency
- Verifier verdict

## Quality gate

Context削減は品質低下を正当化しない。

- 重要Dependency漏れが増えた場合はPackを修正する。
- Verifier Approvalが低下した場合は採用範囲を戻す。
- Token削減だけで成功判定しない。
