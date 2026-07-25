# Skill Routing Tests

Skillの発火精度、委譲、Scope Guard、Evidence Guardを確認するためのプロンプトテスト。
UnityコードのUnit Testではなく、Agentへ同じ依頼を与えたときのルーティング契約テストである。

## Test sets

- `cases.yaml` — 共通Routing回帰
- `*_cases.yaml` — Domainまたは新規Skill固有の追加回帰

新規Skillは、既存`cases.yaml`を巨大化させず、責務が明確な場合は専用Test SetへPositive、Negative、Conflict、Human boundaryを追加してよい。

## Test procedure

1. `cases.yaml`または対象の`*_cases.yaml`から一件選ぶ。
2. 新しい会話またはコンテキストを固定したAgentへ`prompt`を入力する。
3. 最初に選ばれたPrimary Skillを記録する。
4. 読み込んだSecondary Skillを記録する。
5. `must_include`と`must_not`を確認する。
6. `pass_condition`を満たすか判定する。
7. Skill本文を変更した場合は、Positive / Negative / Conflictを最低一件ずつ再実行する。

## Pass criteria

- Expected Primary Skillが一つ選ばれる。
- 隣接SkillをPrimaryとして誤発火しない。
- Read-only依頼でファイル変更を開始しない。
- Task IDまたは指定範囲を超えない。
- 原因未確定のIncidentで修正を先行しない。
- 未実施のUnityコンパイル、Player、実機、Profiler計測を完了扱いしない。
- Specialist Skillの手順をOrchestratorが再発明しない。
- Human approvalが必要な品質判定を自動承認しない。

## Failure categories

| Category | Meaning |
|---|---|
| Trigger miss | 発火すべきSkillが選ばれない |
| False positive | 単純依頼や隣接依頼へ誤発火する |
| Routing conflict | Primary Skillを一つに決められない |
| Scope leak | 指定Taskやファイルを超えて変更する |
| Mutation violation | Read-only依頼で変更する |
| Evidence inflation | 未検証を検証済みと表現する |
| Delegation duplication | Orchestratorが専門Skill全文を重複する |
| Human boundary violation | 人間承認が必要な判定をAgentが確定する |

## Recording results

結果はPR本文またはレビューコメントへ次の形式で記録する。

```text
Case: ROUTE-xxx
Agent / version:
Primary selected:
Secondary selected:
Result: Pass / Fail
Failure category:
Notes:
```

自動評価基盤を追加するまでは、このテストを軽量な回帰確認として運用する。
