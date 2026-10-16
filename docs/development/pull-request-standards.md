# UnityAgent PR記述規約

## 決定（2026-10-16）

A案：主分類1つと追加Evidence 0〜5種類を組み合わせる。日本語のPRタイトル・共通見出しを形式CIで強制する。Evidence不足は警告、観測していないのにPASSと主張する等の検出可能な矛盾はFAILにする。環境不足で未実行の場合はBLOCKED_NOT_RUNを明記するが、未実行自体をPR形式CIで拒否しない。PR品質CIの成功はProduction E2E／実Unity QAのPASSではない。

本書はPR記述の正本。Branch命名、Squash Merge、Merge後のBranch削除については既存のBranch Policy（.github/branch-policy.json、docs/development/branch-policy.md）が優先する。Policy、Approval、Orchestration、Runtime、Persistence、EvalのAuthorityおよびunity-reviewによる受入判定を変更しない。

## 主分類を1つ選択

| pr-type | タイトル接頭辞 | 目的 |
|---|---|---|
| feature | 機能追加： | 新しい機能／Capability |
| fix | 不具合修正： | 既存動作の不具合修正 |
| performance | 性能改善： | CPU／GPU／Memory／Latencyなどの改善 |
| visual | 表示変更： | UI／Shader／Lighting／VFX等の見た目 |
| qa | テスト整備： | QA・失敗検出能力・回帰テスト |
| infrastructure | 基盤変更： | Backend／CI／Protocol／配布・互換性 |
| maintenance | 保守： | 文書・構成整理・Refactor |

分類はユーザー明示目的 → Task Goal／Acceptance → 実際の差分 → Path／Branch補助情報の順。ファイル名だけで主目的を断定しない。複数の独立Goalを1件のPRへ混ぜず、必要時に分割する。

## 追加Evidence（複数選択可能）

| evidence | 必要な情報 |
|---|---|
| performance | Before/After数値と単位、Commit SHA、計測条件、Scene・Build・Platform、測定回数、Warm-up、元ログ |
| visual | 同条件の実Before/After画像、動画（演出・動作時）、Camera・Exposure・Resolution |
| security | 脅威・Authority境界・拒否テスト・未対応リスク |
| migration | 互換性・Migration手順・RollbackとAsset/meta/GUID影響 |
| platform | Unity／URP／Player／Target Device別の検証状態と対象Version |

QAを主分類としただけでperformanceを要求しない。Shader最適化で見た目も変わる場合はperformance + visual等を選択。ゲームProject固有の事情をUnityAgent製品全体の普遍的な要件へ置き換えない。

## 本文の機械可読な記述

本文にpr-type、evidence、evidence-statusの3つのHTMLコメントを各1回記載する。

    <!-- pr-type: performance -->
    <!-- evidence: performance, visual -->
    <!-- evidence-status: performance=not_observed, visual=blocked_not_run -->

追加Evidenceがなければevidence: none、evidence-status: noneとする。状態はpassed、failed、not_observed、blocked_not_runを使用。状態は個々のEvidenceのみを表し、全体GoalのAcceptanceと混同しない。

全分類に共通する必須見出し：
- 「## 概要・変更目的」
- 「## 主な変更内容」
- 「## 検証結果・Evidence」
- 「## 未検証・既知のリスク」
- 「## 関連Issue・PR・影響範囲」

用途別の追加見出し：performanceは「## 性能比較」（Before、After、計測条件、測定回数、Commit SHA）、visualは「## Visual比較」（Before、After、実画像／動画URL）、securityは「## Security検証」（脅威、拒否テスト）、migrationは「## Migration・Rollback」（互換、Rollback）、platformは「## Platform検証」（Platform、検証状態）。

## Evidenceの扱い

実際に計測していない改善値を推測しない。変更前後の測定条件・Revisionが異なる場合は直接比較しない。Editor結果をSwitch等の実機PASSへ流用しない。画像や動画は変更対象の実データとし、生成した参考イメージを実観測と偽らない。機密ゲームAssetやSDKをPRへ無断公開しない。未観測のGateは理由を明記する。

PR Templateは .github/PULL_REQUEST_TEMPLATE.md（通常）と .github/PULL_REQUEST_TEMPLATE/配下（7分類）。GitHubの複数テンプレートはURLパラメータで選択できる。PR作成・更新のSkillは .agents/skills/pr-workflow/SKILL.md とする。

## CIの責務・限界

tools/pr_quality/validate_pr.py は形式、必須欄、追加Evidence項目の構造、検出可能な誤PASS主張を検査。Evidence不足なら警告。passedと宣言したのに最低限の構造さえなければFAIL。メディア内容の真偽、Profilerの統計品質、Unity Editor／Player／Target Device実動作はCIでは検証不能であり、既存QA／Task Contractが判断する。GitHub Actionsはpull_request、read-only、本文データをShellコマンドとして評価しない。Merge・Release・Archive・破壊的削除は明示指示が必要。

外部参考：GitHub公式 PR Template（https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository）、GitHub CLI Media（https://docs.github.com/en/github-cli/github-cli/attaching-files-with-github-cli）、Unity Profiling（https://unity.com/how-to/best-practices-for-profiling-game-performance）。
