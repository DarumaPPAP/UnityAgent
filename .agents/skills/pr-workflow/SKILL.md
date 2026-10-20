---
name: pr-workflow
description: Use when drafting, creating, editing, or validating a UnityAgent pull request, selecting Japanese purpose-specific templates and collecting task-scoped evidence; also supports explicitly approved pre-merge checks without assuming merge permission.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
metadata:
  version: "1.0.0"
  kind: operation
  entrypoint: false
---

# PR Workflow

目的：PRを読みやすい検証記録にする。記述正本は docs/development/pull-request-standards.md、Branch正本は .github/branch-policy.json。User Policy／現在のTask指示を優先し、UnityAgent Control Plane、Approval、Runtime、EvidenceのAuthorityは変更しない。

## When to use
PR作成／更新／レビュー前のEvidence整理、または明示指示のあるMerge前確認時。

## Workflow
1. main、Base／Head SHA、Open PR、Diff、GoalとTask Acceptanceを確認。既存差分と重複実装を避ける。
2. 主分類feature / fix / performance / visual / qa / infrastructure / maintenanceを1つ選ぶ。明示目的→Acceptance→Diff→Path／Branchの順。独立GoalはPR分割を検討。
3. 追加Evidence performance / visual / security / migration / platformを必要分だけ選ぶ。QA名だけで性能Evidenceを強制しない。
4. 必要な時だけunity-review、unity-runtime-evidence、shader-runtime-evidenceに委ねる。小PRにGraphやSubAgentを無駄に起動しない。
5. .github/PULL_REQUEST_TEMPLATE の該当種類から、共通5見出しと機械可読な pr-type、evidence、evidence-status を記載。本文は日本語、API名等は英語のままでよい。
6. Performance主張は同条件Before/After値・Sample・Build／Platform・Commit SHA・ログで根拠を確認。Visual変更は実画像を比較し、必要なら実動画。機密Asset・SDKを無断公開しない。
7. Evidenceがなければ値を捏造せず、not_observed または blocked_not_run を記載。Editor／Player／Device、Host CIと実Unity E2Eを混同しない。
8. python tools/pr_quality/validate_pr.py --title TITLE --body-file FILE を実行し、形式FAILを修正する。Evidence警告は事実・未検証理由を残し、誤PASSのまま進めない。
9. PRを作成・更新し最新HeadのCI、レビュー、依存PRを確認。Merge・Release・Tag・Archive・破壊的削除はそれぞれ明示指示がある時のみ実行する。

## Output contract
- PR URL、日本語タイトル、主分類、追加Evidenceの状態。
- Base／Head SHA、実施したテスト、CI／証拠URL。
- 未実行・未計測Gate、残るリスクと必要な次の操作。
- 記述CIのPASSを実装・QAやProduction E2Eの合格と呼ばない。

## Checklist
- [ ] 主分類1つ、変更Goal1つを確認
- [ ] Evidenceは必要なものだけ選択し状態を記録
- [ ] 日本語タイトル／共通5見出しを記入
- [ ] 主張と計測・画像・CIのRevisionが一致
- [ ] Unity EditorとTarget Deviceの証拠を分離
- [ ] BlockedをPASSにせず、未実行理由を記載
- [ ] Merge権限を別途確認

## Common mistakes
- ファイル拡張子だけからPR主分類を決める。
- performance改修に実測値や計測条件がないまま成功と主張する。
- 実画像の代わりに生成したイメージ図をPRの成功Evidenceに使う。
- 形式ValidatorのPASSを実Unity／Player／実機検証済みと誤認する。
- PR作成時点で無断Mergeを実行する。
