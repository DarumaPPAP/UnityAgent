---
name: production-code-comments
description: Use when adding or revising Japanese comments in production Unity, C#, Shader, HLSL, or Editor code while preserving behavior. Explains non-obvious intent, constraints, ownership, lifetime, execution order, side effects, and failure conditions at low maintenance cost. Does not add tutorial-style line-by-line narration or change code logic.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "2.0.0"
---

# Production Code Comments

本番運用コードへ、保守に必要な日本語コメントだけを追加または修正する。原則としてコード本体の挙動を変更しない。

## Required references

1. `SkillReferences/JAPANESE_CODE_COMMENT_STANDARDS.md`
2. `SkillReferences/COMMENT_REVIEW_CHECKLIST.md`
3. 対象分野に応じた既存Standards

`Production`プロファイルを使用する。

## Workflow

1. 対象コードの責務、所有権、寿命、実行順序を読む。
2. コードから自明な処理の説明を除外する。
3. 設計理由、制約、副作用、破綻条件を優先する。
4. APIや実装から保証できない内容を断定しない。
5. コメントだけを変更し、ロジック差分がないことを確認する。
6. Production向けチェックリストで自己レビューする。
7. 必要時に`comment-quality-reviewer`へ渡す。

## Output contract

- Changed files
- Added / removed comment categories
- Behavior-preservation status
- Ambiguous code that comments alone cannot resolve
- Review result

## Scope — what this Skill does not do

- ロジックを変更しない。
- 全行へ逐語コメントを付けない。
- API名の日本語言い換えだけを書かない。
- 推測した性能やThread安全性を事実として書かない。
- 学習用の長い背景説明を混ぜない。

## Checklist

- [ ] 自明な処理を説明していない
- [ ] 理由、制約、所有権、寿命を優先した
- [ ] コードと矛盾していない
- [ ] 将来変更で腐りやすい値を重複していない
- [ ] ロジック差分がない

## Common mistakes

- `Updateで毎フレーム呼ばれる`などコードから明白な内容だけを書く。
- 現在の実装詳細を仕様として断定する。
- RenderGraph resource lifetimeを誤って説明する。
- コメント追加と一緒にrenameや整形を行う。
