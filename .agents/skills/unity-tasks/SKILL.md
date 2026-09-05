---
name: unity-tasks
description: Use when an approved Unity implementation Plan must be decomposed into small, ordered, independently verifiable execution tasks with stable IDs, file boundaries, dependencies, done criteria, and platform verification. Produces `tasks.md`. Does not implement code or combine unrelated hypotheses into one task.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "2.1.0"
---

# Unity Tasks

承認済みPlanを、Agentまたは実装者が一件ずつ安全に実行できるTaskへ分解する。
各Taskは変更境界、依存、検証、完了条件を持つ。
Planの承認は今回の依頼と既存の承認から判断し、形式的に質問し直さない。このSkillはTask分解を返す。実装まで依頼済みなら呼出元が依頼範囲のTaskを順次選択して継続し、Task一覧だけの依頼なら実装しない。

## When to use

- `spec.md`と`plan.md`がある
- 実装Phaseを複数の変更へ分ける必要がある
- Unity設定、コード、Migration、Test、実機確認を分離したい
- Task IDで作業範囲を固定したい

局所修正が一つの明確な変更で完結する場合は、形式的なTask分割を増やさない。

## Inputs

1. Feature `spec.md`
2. Feature `plan.md`
3. `decisions.md`があれば読む
4. Requirement ID、Acceptance Criteria、Phase、Rollback point

## Task design rules

各Taskに次を必須とする。

- Stable Task ID
- Title
- Purpose
- Requirement / AC trace
- Inputs
- Changed files
- Dependencies
- Implementation boundary
- Explicit non-goals
- Validation
- Done criteria
- Revert condition

## Workflow

### Step 1 — Split by causal and ownership boundary

次を別Taskへ分ける。

- Production code
- Editor tool
- Asset / Prefab / Scene migration
- Shader / RendererFeature
- Unit / EditMode / PlayMode test
- Build / IL2CPP
- Target-device measurement
- Documentation

設計変更と性能仮説を同じTaskへ入れない。
一つのTaskへ複数の主要仮説を入れない。

### Step 2 — Order by dependency

原則順序:

1. Contract / data model
2. Core logic
3. Unity boundary integration
4. Migration
5. Tests
6. Player / platform validation
7. Performance evidence

先行Taskが未完了でも実行できるように見せかけない。

### Step 3 — Fix the file boundary

- 変更予定ファイルを列挙する。
- 新規ファイルの責務を書く。
- 読むだけのReferenceを変更対象へ含めない。
- 対象外ファイルを明示する。

実装中に境界を超える必要が判明した場合は、勝手に拡張せずTask更新または別Task化する。

### Step 4 — Define validation per task

各Taskは、その変更契約とDone criteriaを確認するために必要な検証と必須Gateを持つ。以下は候補であり、全区分を一律に要求しない。

- Static check
- Local validator
- Unit / EditMode / PlayMode test
- Unity compile
- Editor reproduction
- Player / IL2CPP
- Target-device measurement

実機確認をコード実装TaskのDone条件へ曖昧に混ぜず、必要なら独立Taskにする。

### Step 5 — Define completion and rollback

Done criteriaは「コードを書いた」ではなく、観測可能な状態にする。

性能Taskは次を持つ。

- Fixed Before condition
- Metric
- Sample count
- Accept / Reject threshold
- Revert condition

### Step 6 — Save

`Specs/<FeatureName>/tasks.md`へ保存する。
Task IDは後続の追加でも既存IDを振り直さない。

## Recommended task format

```markdown
## UXXX-010-001 <Title>

- Purpose:
- Requirements: FR-xxx, AC-xxx
- Inputs:
- Changed files:
- Dependencies:
- Implementation boundary:
- Non-goals:
- Validation:
- Done criteria:
- Revert condition:
```

## Output contract

- Tasks path
- Task ID一覧
- Dependency order
- 各Taskの変更ファイル
- 独立したUnity設定 / Migration / Player / 実機Task
- 最初に実行可能なTask

## Scope — what this Skill does not do

- Production codeを書かない。
- Planにない機能をTask化しない。
- 複数の設計変更や性能仮説を一件へまとめない。
- Unity設定作業とコード変更を曖昧に混ぜない。
- 完了していないTaskより先へ自動的に進まない。

## Checklist

- [ ] 各Taskに安定IDがある
- [ ] Requirement / ACへ追跡できる
- [ ] Changed filesとNon-goalsが明確
- [ ] 依存順が正しい
- [ ] 各Taskが独立して検証可能
- [ ] 実機確認が必要時に分離されている
- [ ] Done criteriaとRevert条件が観測可能

## Common mistakes

- 「機能を全部実装する」という巨大Taskを作る。
- コード、Scene設定、Build、実機計測を一件へ詰め込む。
- Task実行中に別問題を見つけ、そのまま変更範囲へ追加する。
- 完了条件をファイル作成だけにする。
- 後からTask IDを振り直し、履歴と指示を壊す。
