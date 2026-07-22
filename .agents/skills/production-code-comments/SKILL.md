---
name: production-code-comments
description: Unity、C#、Shaderコードへ本番運用向けの日本語コメントを追加または修正する。
---

# Production Code Comments

Read:

1. `SkillReferences/JAPANESE_CODE_COMMENT_STANDARDS.md`
2. `SkillReferences/COMMENT_REVIEW_CHECKLIST.md`
3. 対象分野に応じた既存Standards

`Production`プロファイルを使用する。

コードから自明な処理は説明しない。設計理由、制約、所有権、寿命、実行順序、副作用、破綻条件を優先する。原則としてコード本体の挙動を変更しない。

変更後はProduction向けチェックリストで自己レビューする。
