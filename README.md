# UnityAgent

Unity向けAI Agent、Skill、コーディング規約、レンダリング規約、Rule Catalog、Prompt、検証Toolを管理する正本リポジトリです。

## Source of truth

- GitHub: Agent、Skill、Standards、Specs、Prompt、Rules、Templates、Tools、Tests
- Google Drive: PDF、PowerPoint、画像、動画、GPU Capture、Profiler Capture、外部調査資料、大容量バイナリ

Google Drive上のコード・規約文書は閲覧用または移行履歴であり、今後の編集正本はこのリポジトリです。

## Main workflow

1. `AGENTS.md`を読む。
2. `Specs/ProjectProfile.md`と`Specs/ProjectConstitution.md`を読む。
3. 複合依頼または入口不明の依頼は`unity-production-workflow`でPrimary laneを選ぶ。
4. 原因不明の不具合は`unity-incident-investigation`で観測と仮説を固定する。
5. 対応する`.agents/skills/<skill>/SKILL.md`だけを読む。
6. 新機能は必要な規模に応じて`Specify -> Plan -> Tasks -> Implement -> Review`を使う。
7. 監査と修正を分離する。
8. 性能変更は`Audit -> Single Hypothesis -> Minimal Patch -> Runtime Evidence`で進める。
9. Before / After、未検証事項、Revert条件を記録する。

小さな局所修正へ形式的なSpec一式を強制しません。一方、複数Subsystem、互換性変更、Migration、Rendering Pipeline変更はSpec駆動で扱います。

## Production entry skills

| Skill | Responsibility |
|---|---|
| `unity-production-workflow` | 複合依頼の分類、Primary Skill選択、Gate、委譲、最終報告 |
| `unity-incident-investigation` | コンパイルエラー、例外、回帰、描画破綻、Editor/Player差の原因調査 |
| `unity-specify` | 検証可能な要件と受け入れ条件 |
| `unity-plan` | 責務、依存、所有権、互換性、Migration、Rollback |
| `unity-tasks` | 安定Task ID、変更境界、依存、Done条件 |
| `unity-implement` | 選択TaskまたはConfirmed Fixの最小差分実装 |
| `unity-review` | Correctness、Compatibility、Performance Evidence、受入判定 |
| `unity-rendering` | Unity 6 URP、RenderGraph、RendererFeature、Shader固有Gate |

詳細なルーティングは`SkillReferences/UNITY_SKILL_ROUTING.md`を参照してください。

## Skill authoring

新規Skillと大幅更新は、`Unity-Technologies/skills`の公開Skill構造を参考にした`SkillReferences/UNITY_SKILL_AUTHORING_STANDARD.md`へ従います。

主要原則:

- `description`は`Use when ...`から開始し、発火条件と非対象を明示する。
- Flow ownerは順序とGateを所有し、専門Skillの手順をコピーしない。
- Audit、Modifier、Evidenceを分離する。
- 長い共通知識は`SkillReferences/`へ置く。
- `Output contract`、`Checklist`、`Common mistakes`を持つ。
- `Tests/SkillRouting/cases.yaml`で発火、誤発火、Scope、Evidenceを回帰確認する。

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

- C# Anti-pattern Audit / Safe Patch / Runtime Evidence
- Shader Performance Audit / Refactor / Variant Governance / Runtime Evidence
- Unity 6 / URP / RenderGraph / STP / TAA向け規約
- Production Workflow / Incident Investigation / Skill Routing Tests
