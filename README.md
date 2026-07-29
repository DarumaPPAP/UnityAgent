# UnityAgent

Unity / C# / URP / RenderGraph / Shader / Performance / Visual DirectionのDomain Skill、Standards、Rules、Validatorを管理する正本Repositoryです。

汎用の実行モード、Task Graph、Retry、Token Budget、Checkpoint、Human Gateは`DarumaPPAP/Unity-Graph-Engineering`が所有します。

## Source of truth

- `DarumaPPAP/UnityAgent`: Unity Domain Knowledge、Skill、Standards、Context Pack、Validator
- `DarumaPPAP/Unity-Graph-Engineering`: Prompt / Graph-Loop実行、Budget、State、Recovery、Human Gate
- `DarumaPPAP/UnityAIGC-Archive`: 生成した製品コード、製品仕様、導入資料
- `DarumaPPAP/Beautiful-Definition`: Visual Intent、Beauty Definition、Human feedback
- Google Drive: PDF、PowerPoint、画像、動画、Capture、外部資料

UnityAgent内へ製品Feature用の新しい`Implementation/`または`Specs/`を作成しません。

## Execution integration

```text
User Request
  ↓
Unity-Graph-Engineering Execution Router
  ├─ Prompt【既定】
  └─ Graph / Loop【明示指定または承認後】
         ↓
UnityAgent .ai/context-index.yaml
         ↓
One Context Pack
         ↓
One Primary Domain Skill
         ↓
Target Source and direct dependencies
```

無指定TaskはPrompt Engineeringです。UnityAgentはGraph / Loopへの無断変更、汎用State Machine、Token Budget管理を行いません。

旧参照PathはCompatibility Adapterとして残します。

- `.agents/skills/unity-production-workflow/SKILL.md`
- `SkillReferences/UNITY_AGENT_SUPERVISOR_MODEL.md`

## Context Engineering

入口は`.ai/context-index.yaml`です。

```text
.ai/
├─ context-index.yaml
├─ context-packs/
│  ├─ csharp-local-fix.yaml
│  ├─ rendering-incident.yaml
│  ├─ shader-change.yaml
│  ├─ performance.yaml
│  └─ visual-direction.yaml
└─ knowledge-graph-pilot.yaml
```

Context Packは資料を次へ分けます。

- Required
- Conditional
- Excluded by default

全Skill、全Referenceを一括で読みません。Primary Domain Skillは一つです。Context拡張時は、どの判断に追加Artifactが必要かを記録します。

詳細: `SkillReferences/CONTEXT_ENGINEERING.md`

## Knowledge Graph

Knowledge Graphは候補Artifactを絞るNavigation Layerです。

```text
Query
  ↓
Candidate artifacts
  ↓
Top source files
  ↓
Direct source inspection
  ↓
Decision or mutation
```

Graphだけで原因、互換性、性能を確定しません。PilotはFakeUnity7のRendering / RendererFeature / Shader周辺、200ファイル以下を想定します。

## Domain routes

| Route | Primary responsibility |
|---|---|
| C# local fix | 確定済みの局所C#修正 |
| Rendering incident | 原因不明の描画、RenderGraph、Editor / Player差 |
| Shader change | ShaderLab、HLSL、Compute、RendererFeature連携 |
| Performance | CPU、GPU、Memory、Build Size、Before / After |
| Visual direction | Scene、Lighting、Composition、Color、Atmosphere、Beauty Review |

## Core constraints

- Runtimeから`UnityEditor`を参照しない
- 既存namespaceと公開・Serialize契約を保持する
- 不要なController、Manager、Setup、自動探索、static状態を追加しない
- Shader名、Property、Keyword、Pass、LightMode、RenderStateを無断変更しない
- Read-only AuditとMutationを分離する
- 一つのPatchで一つのTask、Confirmed Finding、主要仮説を扱う
- 性能変更はBefore / AfterとRevert条件を持つ
- Editor結果だけでPlayerまたは実機を保証しない
- AIの自己申告だけで完了にしない

詳細は選択されたContext Packから必要なReferenceだけを読みます。

## Visual boundary

Visual Taskは`unity-visual-direction`でBeautiful-Definitionから必要なDefinitionだけを取得し、Visual Intent Contractを作成します。

- Technical GateとBeauty Gateを分離する
- CompileやCapture生成をVisual Acceptanceにしない
- Human reviewなしに`VISUAL_ACCEPTED`としない

## Validation

Skill構造Validator:

```bash
python Tools/SkillValidator/validate_skills.py
python Tools/SkillValidator/validate_skills.py --strict
python Tools/SkillValidator/validate_skills.py --json
```

新規・大幅更新SkillはRouting TestとValidatorを通す。Context Pack導入後はTokenだけでなく、Missed DependencyとVerifier Approvalも計測します。

## Target KPI

- Framework Token: 50%以上削減
- Accepted Task総Token: 30%以上削減
- Context File Read: 30%以上削減
- Verifier品質低下: 0
- Missed Dependency悪化: 0

削減率は公開事例ではなく、同じUnity TaskとSource revisionによるA/B比較で判断します。
