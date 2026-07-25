# UnityAgent

Unity向けAI Agent、Skill、コーディング規約、レンダリング規約、Rule Catalog、Prompt、検証Toolを管理する正本リポジトリです。

## Source of truth

- GitHub / UnityAgent: Agent、Skill、Standards、Rules、Templates、Tools、Tests、ワークスペース統治用Spec
- GitHub / UnityAIGC-Archive: UnityAgentを参照して生成した製品コード、製品仕様、導入資料
- GitHub / Beautiful-Definition: ユーザーが考える美しさ、Reference、Visual Intent、Beauty Review、Human feedbackの正本
- Google Drive: PDF、PowerPoint、画像、動画、GPU Capture、Profiler Capture、外部調査資料、大容量バイナリ、閲覧用ビジュアル

Google Drive上のコード・規約文書は閲覧用または移行履歴であり、今後の編集正本はGitHubです。

UnityAgentを参照して生成する製品Featureは`DarumaPPAP/UnityAIGC-Archive`へ保存し、UnityAgent内の`Implementation/`や製品Feature用`Specs/`へ新規追加しません。

美しいScene、Lighting、Look Development、Composition、Camera、Color、Atmosphereを扱う場合は、`DarumaPPAP/Beautiful-Definition`を取得してVisual Intent Contractを作成します。UnityAgent内へ美的Definition本文を複製しません。

## Core operating model

複合依頼は、固定された`仕様 -> 実装 -> 検証 -> PR`の一本道ではなく、Supervisorが状態遷移として管理します。

```text
Goal / Constraints / Observability / Recovery
                    ↓
            Supervisor State
                    ↓
       必要な専門Skillだけを選択
                    ↓
      実装・観測・証拠評価・回復
                    ↓
          Human Decision / Approval
```

重要な変更点:

- コード生成やファイル更新を完了扱いしない
- Compile、Runtime、Visual、Performance、Scopeの失敗を分離する
- 失敗分類に応じて別のStateと専門Skillへ戻す
- 現在Stateに必要なToolだけを使用する
- 指定Task完了後に次Taskへ自動で進まない
- 破壊的契約変更、品質判断、ファイル削除、PR Mergeは人間判断へ分離する
- 技術検証と美的受入を分離し、Human reviewなしに`VISUAL_ACCEPTED`としない

正本:

- `SkillReferences/UNITY_AGENT_SUPERVISOR_MODEL.md`
- `.agents/skills/unity-production-workflow/SKILL.md`
- `SkillReferences/UNITY_SKILL_ROUTING.md`
- `SkillReferences/BEAUTIFUL_DEFINITION_INTEGRATION.md`

## Main workflow

1. `AGENTS.md`を読む。
2. `Specs/ProjectProfile.md`と`Specs/ProjectConstitution.md`を読む。
3. 複合依頼、自走依頼、実装と検証が混在する依頼は`unity-production-workflow`をSupervisorにする。
4. `Goal / Constraints / Observability / Recovery`をExecution Contractとして確定する。
5. 現在Stateを一つ選び、必要なPrimary Skillだけを読む。
6. 美的成果を含む場合は`unity-visual-direction`でBeautiful-Definitionを取得し、Visual Intent Contractを先に作る。
7. 原因不明の不具合は`unity-incident-investigation`で観測と仮説を固定する。
8. 新機能は必要な規模に応じて`Specify -> Plan -> Tasks -> Implement -> Review`を使用する。
9. 監査と修正を分離する。
10. 性能変更は`Audit -> Single Hypothesis -> Minimal Patch -> Runtime Evidence`で進める。
11. 失敗時はCompile / Runtime / Visual / Performance / Scope / Contractへ分類して遷移する。
12. Before / After、未検証事項、Recovery、Revert条件を記録する。
13. 生成した製品コードと製品Specは`UnityAIGC-Archive`へ保存する。

小さな局所修正へ形式的なSpec一式を強制しません。一方、複数Subsystem、互換性変更、Migration、Rendering Pipeline変更はSpec駆動で扱います。

## Supervisor states

```text
INTAKE
  ├─ CONTEXT_REQUIRED
  ├─ READY
  │    ├─ PLANNING
  │    ├─ INVESTIGATING
  │    └─ IMPLEMENTING
  └─ BLOCKED

IMPLEMENTING
  → STATIC_VALIDATION
  → UNITY_VALIDATION
  → DOMAIN_VALIDATION
  → VISUAL_OR_RUNTIME_VALIDATION
  → EVIDENCE_REVIEW
  → AWAITING_HUMAN_APPROVAL
  → ACCEPTED
```

失敗時は原因に応じて`IMPLEMENTING`、`INVESTIGATING`、`CONTEXT_REQUIRED`、`AWAITING_HUMAN_DECISION`、`REVERT_REQUIRED`へ戻します。

## Production entry skills

| Skill | Responsibility |
|---|---|
| `unity-production-workflow` | Supervisor状態遷移、Execution Contract、Primary Skill選択、Recovery、Evidence review、人間への引き渡し |
| `unity-incident-investigation` | コンパイルエラー、例外、回帰、描画破綻、Editor / Player差の原因調査 |
| `unity-specify` | 検証可能な要件、Goal、非目標、受け入れ条件 |
| `unity-plan` | 責務、依存、所有権、互換性、Migration、Rollback |
| `unity-tasks` | 安定Task ID、変更境界、依存、Done条件 |
| `unity-implement` | 選択TaskまたはConfirmed Fixの最小差分実装 |
| `unity-review` | Correctness、Compatibility、Scope、Performance Evidence、受入判定 |
| `unity-rendering` | Unity 6 URP、RenderGraph、RendererFeature、Shader固有Gate |
| `unity-visual-direction` | Beautiful-Definition取得、Visual Intent、構図・Lighting・Color・Atmosphereの美的契約、Beauty Review |

詳細なルーティングは`SkillReferences/UNITY_SKILL_ROUTING.md`を参照してください。

## Tool policy

万能MCPへ全操作を集約するのではなく、現在Stateと専門領域ごとにToolを絞ります。

- Context Tools — Search、Read、Metadata
- Compile Tools — Unity compile、Console
- Scene Tools — Play、Hierarchy、Screenshot
- Test Tools — Validator、EditMode、PlayMode
- Shader Tools — Shader compile、Keyword、Variant
- Evidence Tools — Profiler、GPU Capture、Target-device結果
- Git Tools — Diff、Review、Commit、PR

使用できないToolの結果を推測で補いません。

## Skill authoring

新規Skillと大幅更新は、`Unity-Technologies/skills`の公開Skill構造を参考にした`SkillReferences/UNITY_SKILL_AUTHORING_STANDARD.md`へ従います。

主要原則:

- `description`は`Use when ...`から開始し、発火条件と非対象を明示する。
- Flow ownerは順序、State、Gateを所有し、専門Skillの手順をコピーしない。
- Audit、Modifier、Evidenceを分離する。
- 長い共通知識は`SkillReferences/`へ置く。
- `Output contract`、`Checklist`、`Common mistakes`を持つ。
- `Tests/SkillRouting/`で発火、誤発火、Scope、Evidence、Recoveryを回帰確認する。

Template: `Templates/Skills/SKILL_TEMPLATE.md`

## Validation

外部Package不要のValidatorを実行できます。

```bash
python Tools/SkillValidator/validate_skills.py
```

既存Skillを含むadvisory確認では、構造Errorだけが失敗になります。

```bash
python Tools/SkillValidator/validate_skills.py --strict
python Tools/SkillValidator/validate_skills.py --json
```

`--strict`はAuthoring QualityのWarningも失敗扱いにします。既存Skillは段階的に移行し、新規・大幅更新Skillはstrict通過を目標にします。

## Current systems

- Supervisor State Machine / Execution Contract / Failure Routing
- C# Anti-pattern Audit / Safe Patch / Runtime Evidence
- Shader Performance Audit / Refactor / Variant Governance / Runtime Evidence
- Unity 6 / URP / RenderGraph / STP / TAA向け規約
- Beautiful-Definition連携 / Visual Intent Contract / Beauty Review / Human feedback loop
- Production Workflow / Incident Investigation / Skill Routing Tests
