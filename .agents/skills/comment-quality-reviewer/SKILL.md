---
name: comment-quality-reviewer
description: Unity、C#、Shaderコードの日本語コメントを監査し、不足、冗長、矛盾、誤断定を検出する。
---

# Comment Quality Reviewer

Read:

1. `SkillReferences/JAPANESE_CODE_COMMENT_STANDARDS.md`
2. `SkillReferences/COMMENT_REVIEW_CHECKLIST.md`
3. 対象が本番用なら`Production`、学習用なら`Learning`プロファイル
4. 対象分野に応じた既存Standards

コメント数ではなく、正確性、保守性、理解容易性を評価する。原則としてコード本体は変更せず、コメントだけでは整合しない場合はFindingとして報告する。

チェックリストのSeverity、Output Format、Auto-fix Policy、Completion Reportに従う。
