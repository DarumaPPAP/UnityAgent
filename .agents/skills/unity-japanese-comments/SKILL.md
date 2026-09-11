---
name: unity-japanese-comments
description: Use when adding or reviewing Japanese comments in Unity code to preserve non-obvious reasons, constraints, ownership, lifecycle timing, compatibility, or measured performance context without changing runtime behavior. Produces only maintenance-relevant comments and removes stale or self-evident wording. Does not refactor code.
---

# Unity Japanese Comments

- 理由、制約、所有権、実行タイミング、互換性を説明する。
- コードの逐語説明や自明なコメントは追加しない。
- コメント追加と同時にコード動作を変更しない。
- 古くなったコメントや未計測の性能断定を残さない。

## Output contract

- コメントを追加・更新したファイルと対象箇所
- コメントが残すべき理由 / 制約 / Ownership / Lifecycle情報
- 削除した古い・自明なコメントと理由
- Runtime behaviorを変更していないこと
- 性能・実機・互換性について未検証の断定を追加していないこと

## Checklist

- [ ] コメントは「何をしているか」ではなく「なぜ必要か」を補足している
- [ ] Unity Lifecycleや実行順序の罠がある場合だけタイミングを説明している
- [ ] Ownership、互換性、Platform制約などコードだけでは分かりにくい情報を優先している
- [ ] 自明な代入やMethod名の逐語説明を追加していない
- [ ] コメント編集にコード動作変更を混ぜていない
- [ ] 未計測の性能改善や未確認の実機挙動を断定していない
- [ ] 実装と矛盾する古いコメントを残していない

## Common mistakes

- `count++` に「カウントを1増やす」のような逐語コメントを付ける。
- `Awake` / `OnEnable` / `Start` の順序に依存する理由を説明せず、処理内容だけを書く。
- コメント整理のついでに変数名や制御フローまで変更する。
- 「高速化のため」と書くがBefore/After計測が存在しない。
- Editor限定の確認を「実機でも安全」とコメントする。
- 仕様変更後も古い制約コメントを残し、コードとドキュメントを矛盾させる。
