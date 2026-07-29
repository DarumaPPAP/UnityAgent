---
name: unity-production-workflow
description: Compatibility adapter for Unity production requests. Delegates execution mode, task graph, budgets, state, recovery, and human gates to DarumaPPAP/Unity-Graph-Engineering, then routes only the required Unity domain skill and Context Pack from UnityAgent. Do not use it as an independent Supervisor implementation.
allowed-tools:
  - Read
metadata:
  version: "3.0.0"
---

# Unity Production Workflow Adapter

このSkillは旧`unity-production-workflow`利用者を、新しいExecution OwnerとUnityAgent Domain Skillsへ接続するAdapterです。

## Ownership

### Unity-Graph-Engineering

- Prompt / Graph-Loop Mode
- Mode変更確認
- Goal Contract
- Task Graph
- Node Loop
- Budget
- State / Checkpoint
- Recovery
- Independent Verifier
- Human Gate

### UnityAgent

- Domain route
- Context Pack
- Unity固有規約
- C# / Rendering / Shader / Performance / Visual Skill
- Domain validation requirements

汎用Supervisor処理をこのSkillへコピーしません。

## Entry flow

1. Unity-Graph-Engineeringの`unity-execution-router`でModeを確定する。
2. 無指定ならPrompt Engineeringを選ぶ。
3. `.ai/context-index.yaml`からTask classを選ぶ。
4. 対応Context PackとPrimary Domain Skillだけを読む。
5. Domain outputをExecution Ownerへ返す。

```text
Execution Router
  ↓
Prompt or Graph / Loop
  ↓
UnityAgent Context Index
  ↓
One Context Pack
  ↓
One Primary Domain Skill
```

## Domain routes

- 原因不明のエラー、回帰、Editor / Player差: `unity-incident-investigation`
- C#局所修正: `csharp-safe-patch`
- Unity 6 URP / RenderGraph / RendererFeature: `unity-rendering`
- Shader監査: `shader-performance-auditor`
- Confirmed Shader修正: `shader-performance-refactor`
- Keyword / Variant / Strip: `unity-shader-variant-governor`
- CPU / GPU / Memory Evidence: `unity-runtime-evidence`または対応Evidence Skill
- 美的Scene / Lighting / LookDev: `unity-visual-direction`
- 仕様、設計、Task分割が成果物として必要: `unity-specify`、`unity-plan`、`unity-tasks`

全Skillを一括で読みません。

## Prompt Mode contribution

Prompt Modeでは次だけを返します。

- Minimal Contractに必要なDomain constraints
- 対象Sourceと直接依存
- 一つのPrimary Skill
- 必須Validator
- Compatibility / Revert条件

Task Graphや永続StateをUnityAgent側で生成しません。

## Graph / Loop contribution

Graph / Loopでは各Nodeへ必要なDomain Contextだけを返します。

- NodeごとのContext Pack
- Owned artifact constraints
- Domain evidence requirements
- Failure classification hints

Maker / Verifierへ同一の巨大Contextを渡しません。

## Output contract

```yaml
context_pack: ""
primary_domain_skill: ""
confirmed_context: []
constraints: []
required_validation: []
evidence_required: []
unverified: []
revert_condition: ""
```

## Common mistakes

- UnityAgent内で別のSupervisor State Machineを再構築する
- 無指定TaskをGraphへ送る
- 全Referenceを常時読む
- Domain SkillへToken Budget管理を持たせる
- Compile成功をRuntime、Visual、Performanceの完了とする
