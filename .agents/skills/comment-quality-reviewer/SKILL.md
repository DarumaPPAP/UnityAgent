---
name: comment-quality-reviewer
description: Use when reviewing Japanese comments in Unity, C#, Shader, HLSL, or Editor code for accuracy, missing intent, redundancy, contradictions, stale claims, maintenance cost, or unsupported assertions. Produces comment-only findings and applies the Production or Learning profile. Does not change code logic or hide design defects behind comments.
allowed-tools:
  - Read
metadata:
  version: "2.1.0"
  kind: user-policy-operation
  policy_owner: user
  policy_source: Policy/User/user-policy.yaml#comment_system
  protected: true
  entrypoint: conditional
---

# Comment Quality Reviewer

日本語コメントをRead-onlyで監査し、不足、冗長、矛盾、陳腐化、誤断定を検出する。

## Required references

1. `Policy/User/user-policy.yaml`
2. `SkillReferences/JAPANESE_CODE_COMMENT_STANDARDS.md`
3. `SkillReferences/COMMENT_REVIEW_CHECKLIST.md`
4. 本番用なら`Production`、学習用なら`Learning`プロファイル
5. 対象分野に応じた既存Standards

## Workflow

1. 対象プロファイルと読者を確定する。
2. コメントと実コードの意味を照合する。
3. 正確性、保守性、理解容易性を評価する。
4. 不足、冗長、矛盾、誤断定、陳腐化Riskを分類する。
5. コメントだけで解決できない設計問題はFindingとして分離する。
6. CheckListのSeverity、Output Format、Auto-fix Policyに従う。

## Output contract

- Profile
- Finding severity
- File and location
- Current comment problem
- Code evidence
- Proposed comment action
- Logic issue that requires a separate code task

## Scope — what this Skill does not do

- コード本体を変更しない。
- コメント数の多さを品質としない。
- 設計問題をコメント追加だけで解決扱いしない。
- APIや性能を根拠なく断定しない。

## Checklist

- [ ] `Policy/User/user-policy.yaml`のコメントPolicyを適用した
- [ ] Profileを確定した
- [ ] コメントとコードを照合した
- [ ] 不足と冗長を両方確認した
- [ ] 誤断定と陳腐化Riskを確認した
- [ ] コード問題を別Findingにした
- [ ] ファイルを変更していない

## Common mistakes

- コメントが多いほど高品質と判定する。
- コードと矛盾するコメントを文章だけ整える。
- 学習用コメント密度を本番コードへ要求する。
- `高速`や`安全`という根拠なしの断定を見逃す。
