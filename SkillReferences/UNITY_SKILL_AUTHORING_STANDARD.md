# Unity Skill Authoring Standard

UnityAgentで追加・更新するSkillの設計規約。
`Unity-Technologies/skills`の公開構造を参考にしつつ、本リポジトリのSpec駆動、最小差分、実測証拠、Console実機対応へ合わせる。

Reference: `https://github.com/Unity-Technologies/skills`

## 1. Core model

Skillは長大な知識集ではなく、次のどれかを所有する実行可能な入口である。

1. **Flow owner** — 質問、順序、Gate、専門Skillへの委譲を管理する。
2. **Specialist procedure** — 一つの専門作業を再現可能な手順として管理する。
3. **Read-only auditor** — 変更せずFindingと確度を返す。
4. **Safe modifier** — 確定した対象だけを互換性付きで修正する。
5. **Evidence gate** — Before/After、Player、実機などの証拠を判定する。

一つのSkillへ複数の所有責務を詰め込まない。

## 2. Folder structure

```text
.agents/skills/
  <skill-name>/
    SKILL.md
    references/        # Skill専用の長い参照資料が必要な場合のみ
    examples/          # 実例がトリガー精度や出力形式に必要な場合のみ
```

共通規約は`SkillReferences/`へ置く。Skill固有の資料はSkill配下へ置く。
同じ規約を複数Skillへコピーしない。

## 3. Required frontmatter

```yaml
---
name: unity-example-skill
description: Use when ... Triggers on ... Does not ...
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "1.0.0"
---
```

### `name`

- フォルダ名と完全一致させる。
- kebab-caseを使う。
- `unity-`はUnity全般のFlowまたは境界処理に使う。
- C#やShaderなど明確な専門領域は、既存命名体系を優先する。

### `description`

AgentがSkillを読む前に参照するルーティング契約である。
本文の要約ではなく「いつ発火し、いつ発火しないか」を書く。

必須要素:

1. `Use when ...`で開始する。
2. 代表的なユーザー表現または状況を含める。
3. Skillが所有する成果を明示する。
4. 隣接Skillとの境界を`Does not ...`で示す。

悪い例:

```yaml
description: Unityコードを改善する。
```

良い例:

```yaml
description: Use when reviewing Unity C# for ownership, lifetime, AOT, Burst/Jobs, allocation, or API compatibility without changing files. Produces evidence-ranked findings and delegates confirmed fixes to csharp-safe-patch. Does not implement features.
```

### `allowed-tools`

- 本当に必要なToolだけを書く。
- Read-only監査へWrite/Editを許可しない。
- GitHub、Drive、Unity CLIなど環境依存Toolを無根拠に要求しない。
- 対応Agent間の互換性を損ねる場合は省略してよい。

### `metadata.version`

- 新規Skillは`1.0.0`。
- トリガー、出力契約、手順の互換性を変える場合は更新する。
- Git履歴が正本であり、version値だけで配布管理しない。

## 4. Required body sections

全Skillで以下の意図を満たす。見出し名は用途に応じて調整可能。

### Purpose

- Skillが所有する一つの責務。
- 生成する成果物。
- 変更を行うかRead-onlyか。

### When to use

- 代表的な依頼。
- 入力状態。
- 発火の境界。

### Delegates to / Related skills

- 専門手順を再実装せず、既存Skillへ委譲する。
- 「読めるものを全て読む」ではなく、条件付き委譲を書く。
- 循環委譲を作らない。

### Workflow

- 実行順序を番号付きで書く。
- 各Stepに入力、判断、出力、停止条件を持たせる。
- Unity固有の境界、互換性、検証階層を含める。

### Scope

- 何をしないか。
- 隣接Skillへ渡す範囲。
- 勝手に追加してはいけないシステム。

### Output contract

Agentの最終報告に必要な項目を固定する。
例:

- Task / Incident / Rule ID
- Changed files
- Evidence and confidence
- Compatibility impact
- Validation performed
- Unverified items
- Revert condition

### Checklist

実行漏れを防ぐ最終Gate。手順の全文を繰り返さない。

### Common mistakes

実際に起きやすい誤実装、誤診断、過剰実装を書く。
一般論ではなくUnity固有の失敗を優先する。

## 5. Progressive disclosure

Skill本文には実行判断と主要手順を置き、長い資料は参照先へ分ける。

本文に残すもの:

- 発火条件
- 判断順序
- 安全境界
- 出力契約
- よくある失敗

参照へ分けるもの:

- 大規模Rule Catalog
- API一覧
- Platform別Matrix
- 長いサンプルコード
- テンプレート全文
- 調査資料と出典

Skillから参照するパスは相対パスまたはリポジトリルート基準で一意にする。
存在しないファイルを参照しない。

## 6. Delegation rules

### Flow Skill

- 順序とGateを所有する。
- 専門コマンドや専門規約をコピーしない。
- Primary Skillを一つ選び、Secondary Skillを必要時だけ呼ぶ。

### Audit Skill

- 原則Read-only。
- Findingへ確度、重大度、根拠、条件、提案を付ける。
- 修正はSafe Modifierへ渡す。

### Modifier Skill

- Rule、Task、Confirmed Hypothesisのいずれかを入力契約にする。
- 対象外の改善を混ぜない。
- 互換性契約とRevert条件を返す。

### Evidence Skill

- Scene、Platform、Build、Quality、warm-up、sample countを固定する。
- Missing evidenceを推測で補わない。
- Adopt / Rework / Revert / Inconclusiveの判定を返す。

## 7. Unity production requirements

Skillの対象に応じて次を明示する。

- Unity version
- Render Pipelineとpackage version
- Editor / Player
- Mono / IL2CPP
- Development / Release
- Target platform / graphics API
- Burst / Jobs / Entities
- public API / serialization / Prefab / Scene / Save Data
- Shader Property / Keyword / Pass / LightMode / RenderState
- Static / Unity compile / Editor / Player / target-deviceの検証状態

性能を扱うSkillは、静的予測と実測結果を分離する。

## 8. Ceremony budget

実案件では、作業規模に合わない文書量が逆に品質を落とす。

### Small fix

条件:

- 単一原因
- 局所ファイル
- 要件と受け入れ条件が依頼文で明確

対応:

- 回答内の実装契約またはIncident記録でよい。
- 形式的なSpec/Plan/Tasksを強制しない。

### Feature or cross-cutting change

条件:

- 複数責務
- public/serialized契約変更
- Migrationが必要
- Renderer/Shader/Platformへ波及

対応:

- Spec → Plan → Tasks → Implement → Reviewを使う。

### Performance change

規模に関係なくBefore/After条件とRevert条件を先に持つ。

## 9. Routing test requirements

新規または大幅更新したSkillは、最低限次をテストする。

1. **Positive direct** — 明確に発火すべき依頼。
2. **Positive paraphrase** — 別表現でも発火すべき依頼。
3. **Negative adjacent** — 隣接Skillへ行くべき依頼。
4. **Negative simple** — Skill不要の単純説明。
5. **Conflict** — 複数候補がある依頼でPrimaryを一つ選べるか。
6. **Scope guard** — 禁止された追加実装を行わないか。
7. **Evidence guard** — 未計測を計測済みと断定しないか。

テストケースは`Tests/SkillRouting/`へ追加する。

## 10. Review gate

Skill追加・更新時に確認する。

- [ ] nameとフォルダ名が一致する
- [ ] descriptionが`Use when`で始まる
- [ ] 発火条件と非対象が具体的
- [ ] 一つの責務を所有している
- [ ] 既存Skillの手順を重複していない
- [ ] Read-onlyと変更Skillを分離している
- [ ] Unity固有の互換性契約を扱っている
- [ ] Output contractがある
- [ ] ChecklistとCommon mistakesがある
- [ ] ルーティングテストがある
- [ ] 未検証の動作や性能を断定しない

## 11. Anti-patterns

- descriptionを本文要約として書く。
- 一つのSkillへ設計、実装、監査、計測を全て詰め込む。
- 参照資料を全文コピーしてSkillを巨大化する。
- 「必要に応じて確認する」だけで具体的な判断条件を書かない。
- すべての作業へ同じSpec一式を強制する。
- Tool名やCLI構文を検証せずハードコードする。
- 対象外機能を親切心で追加する。
- Editor結果だけでPlayerまたはConsole実機を保証する。
