---
name: learning-code-comments
description: Use when turning Unity, C#, Shader, HLSL, or Editor code into Japanese learning material for code reading or onboarding while preserving behavior. Explains architecture, API purpose, execution flow, data flow, coordinate spaces, trade-offs, and pitfalls using structured comments. Does not modify logic or degrade into a comment on every line.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "2.1.0"
  kind: user-policy-operation
  policy_owner: user
  policy_source: Policy/User/user-policy.yaml#comment_system
  protected: true
  entrypoint: conditional
---

# Learning Code Comments

Unityコードを学習・コードリーディング向けに解説する日本語コメントを追加する。原則としてコード本体の挙動を変更しない。

## Required references

1. `Policy/User/user-policy.yaml`
2. `SkillReferences/JAPANESE_CODE_COMMENT_STANDARDS.md`
3. `SkillReferences/COMMENT_REVIEW_CHECKLIST.md`
4. 対象分野に応じた既存Standards

`Learning`プロファイルを使用する。

## Workflow

1. 対象読者と前提知識を確認する。
2. クラスと主要処理にはSDS、局所的な設計判断にはCRFを使う。
3. API、処理順、データフロー、座標空間、所有権、代替案、注意点を説明する。
4. 一行ごとの日本語化ではなく、理解単位でコメントを配置する。
5. 推測と確定仕様を分離する。
6. ロジック差分がないことを確認する。
7. Learning向けチェックリストで自己レビューし、必要時に`comment-quality-reviewer`へ渡す。

## Output contract

- Changed files
- Target reader assumption
- Explained concepts
- Behavior-preservation status
- Remaining prerequisites or ambiguous code
- Review result

## Scope — what this Skill does not do

- ロジックを変更しない。
- 全行を逐語説明しない。
- 本番コードへ過剰な教材コメントを混ぜない。
- APIドキュメントの転載だけにしない。
- 不明な挙動を断定しない。

## Checklist

- [ ] `Policy/User/user-policy.yaml`のコメントPolicyを適用した
- [ ] 対象読者が明確
- [ ] SDS / CRFを理解単位で使った
- [ ] 処理順とデータフローを説明した
- [ ] 代替案と注意点を必要箇所だけに書いた
- [ ] 逐行コメントになっていない
- [ ] ロジック差分がない

## Common mistakes

- 変数代入を一行ずつ日本語化する。
- Unity lifecycleの順序を誤って説明する。
- World / View / Clip / Screen座標を混同する。
- ShaderのGPU実行をCPUの逐次処理として説明する。
- 学習コメントをそのまま本番用密度として採用する。
