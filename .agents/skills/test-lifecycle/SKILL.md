---
name: test-lifecycle
description: Use when creating, changing, consolidating, promoting, or removing UnityAgent tests, including one-off diagnostic probes. Reuse existing test and evaluation mechanisms, assess permanent tests through risk-proportional review, and clean up task-scoped temporary tests.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
metadata:
  version: "1.0.0"
  kind: operation
  entrypoint: false
  user_policy: src/unityagent/policy/user/user-policy.yaml
---

# Test Lifecycle — Reuse, Review, Promote or Discard

UnityAgentの既存テストを最小限かつ検出力のある形に保つための**実装用Skill**。新しいTest Framework、独立したApproval Authority、専用DBを作らない。Taskを超える設計変更はしない。

## When to use

- 新機能・修正に付随してTest、Fixture、診断Probeを追加・変更・削除するとき
- 過去のRegressionを参照しつつ現行製品契約から新規Testを設計するとき
- 一時テストを恒久Regressionへ採用するか判定するとき
- Taskの終了時・セッション終了前に今回作成した一時Testを片付けるとき

単純な説明、既存Testの結果を読むだけの相談には本Skillを自動起動しない。

## Authority and reuse

1. **Policyの正本**は `src/unityagent/policy/approval/approval-policy.yaml`。このSkillは実行・承認・EvidenceのAuthorityを持たない。ユーザーの既存の明示承認はScope内で維持し、追加の承認を機械的に要求しない。
2. Test実行には既存のPython `unittest`、Unity Test Framework、`tools/validate_all.py`、必要時のEvalと `tools/run_regression_gate.py` を使う。テスト結果・Capture・Static Validator・実Editor/Player/実機Evidenceは別物。
3. Evalから派生した改善提案は `eval/change_proposals/change_proposal.py` の `build_change_proposal` と既存Schemaを再利用する。戻り値 `status: proposed`、`applies_change: false`、`requires_human_review: true` を守る。通常のTest追加にEval実行やChangeProposalを強制しない。
4. Testコードの責務は保護する振る舞い／Failureごと。同一責務は既存Fileへまとめる。実行環境・所有者・Fixture・失敗原因が独立する場合だけ分離。ファイル数や行数そのものを合格基準にしない。
5. 旧Regressionは固定Git Revisionから参照できるが、現行の`tests/UnityAgentTest/`だけでは製品回帰は検証されない。CIの静的Validator PASSをRegression PASSと解釈しない。

## Step 1 — Scope and reuse gate（毎回・短い）

- Task ID、期待するBehavior、Failure class、対象SHA／Project、許される変更Scopeと必須Gateを固定。
- 既存Test、Validator、Fixture、Eval、過去のRegressionを検索する。同じFailureが既存の安価なTestで検出できるなら**新規ファイルも新規Testも作らない**。
- 新ファイルを求める場合は `Purpose / Reuse attempted / Separation reason / Cost / Retirement condition` を短く示す。「SOLIDだから」「将来使うから」は理由と認めない。
- まだ仮説段階の調査Testは**Temporary**を選び、恒久Testへ自動登録しない。

## Step 2 — Temporary Test: task-scoped probe（通常は最短）

- 1回限りの検証コードとFixtureは**Run所有**の別作業領域を使う。Pythonなら `tempfile.TemporaryDirectory(prefix="unityagent-test-")` をコンテキスト管理し、途中失敗でも `finally` 相当の解放を行う。Unity Editorが必要なら専用の複製Projectや短命Worktreeを使い、共有Editor／ProjectのLease・排他・Mutation Scopeを維持する。
- 既存のtracked testやFixtureを診断用Testで上書きしない。Rootに `temp_test_*.py` を放置しない。Probeを成功のために改変して本来の不具合を隠さない。
- 例外・Cancel時にも cleanup を実行する構造でコードを書く。強制終了や環境喪失では完了保証がないため、その場合は `cleanup=not_verified` と報告し、次回の所有者確認なしで他者のTempやWorktreeを一括削除しない。
- Task完了**および観測可能なセッション終了前**に、作成した一時テスト・Fixture・ログ・短命Worktreeの残存を確認する。削除は**このRunが新規作成したと証明できる対象だけ**。既存未コミット変更、`tests/UnityAgentTest/`、他Runのファイル、ユーザーAssetを削除しない。
- `git status --porcelain` と作業時の初期差分を比較する。既存差分を復元／stash／clean／resetしない。残存があればパスと理由を報告し、勝手に完了と宣言しない。

## Step 3 — Conditional multi-stage permanent-test review

多段階**評価**であり、3回の独立した人間承認ではない。小TaskにはFast Pathを適用。

| Stage | 判定・証拠 | 不採用条件 |
| --- | --- | --- |
| A: Necessity（AI/開発者の下調べ） | 現行Behavior／失敗経路、既存Testとの差分、新規FileのSplit Reason | 既存Testと重複、過去Migrationのみの期待、単なる実装行やString固定 |
| B: Evidence（既存CI/Validator） | 偽陽性でない再現可能な失敗、修正後PASS、対象SHA・コスト・正常/拒否系、Scope | PASSだけ、Mockだけで実E2Eを主張、`not_observed`を成功扱い、旧Testの検出能力後退 |
| C: Admission（必要時のみ既存PR/Human Review） | 既存PRに`Invariant / Reuse / Failure prevented / Cost / Evidence / Retirement`を記載。必要なら既存Policyによる人間承認 | PR・Policyの判断前の自動採用、AI自己承認、Scope拡大、Approval Decisionの偽造 |

- **Temporary / no promotion**: Stage Aで終了。Stage Bは調査に必要な範囲のみ実行し、Task終了時に破棄。人間承認を増やさない。
- **Permanent low risk**: Stage A → B → 既存PRの通常レビュー。独立したChangeProposalや複数人承認は不要。
- **Security / Approval / Mutation Scope / Evidence / Editor E2E / Breaking change**: Stage A → Bで関連する失敗系と対象Gateを実行し、Stage Cで既存R2–R4 PolicyとPR Reviewに従う。必要な実Unity観測がなければ `BLOCKED_NOT_RUN`。
- **Eval起点の自己改善**: 提案→人間レビュー→PR→Regression/Baseline比較という既存順序に従う。SkillはProposalを承認・適用しない。
- 人間の正式承認をSkillの文章やLLM回答で代行しない。PR reviewとRuntimeのExecution Approvalも区別する。

## Step 4 — Promote / Freeze / Delete

- 恒久採用時は既存の所有フォルダ・Test Moduleへ統合し、追加は検出能力の差分で説明する。もし複数Fileに分けるなら責務、Fixture、実行環境を根拠にする。
- 旧Testの再導入は原本を機械復元せず、固定BaselineのFailureとInvariantを検証し、現行コードに必要な最小Caseだけ設計する。
- 新スイートが元Baselineの重要な拒否／失敗系を守ったと分かるまで旧Testは実行対象に残す。凍結旧Testは新正本のPASSに混ぜない。比較が終わり不要と確定すれば旧Fileを後続の整理PRで削除する。
- 凍結フォルダを恒久的な二重Test保管庫にしない。新規Testの採用によってFile数とRuntimeが増えた場合は、増分の独自検出価値を説明する。

## Step 5 — Completion and cleanup gate（必須）

- このTaskで生成した一時Testの全パス、作業所有者、削除結果を記録し、**最終回答前**に残存確認する。次回も使用する恒久TestをTemporaryのまま残さない。
- 結果は `PROMOTED / DISCARDED / FROZEN / BLOCKED` のいずれかとし、`cleanup=verified / not_verified / not_applicable` を区別する。未観測・停止・キャンセルはPASSにしない。
- 途中停止時に作業ディレクトリごと消せない場合は安全に停止し、残余と手動Clean手順を提示する。ログにはSecrets、私的Asset、Prompt本文を永続化しない。
- Test結果は `Static / Python Unit / Unity Compile / Editor / Player / Target Device / Visual / Performance` を別々に報告する。取得できなかったGateは `not_observed` または `BLOCKED_NOT_RUN`。

## Output contract

- Task／Source SHA、保護Invariant、実施したTest、観測されたFailureとPASS
- Reuse済みのTest/Validator・新規Fileの必要性／分割理由（新規作成時）
- Stage A/B/Cの結論、実際に必要だったHuman Review・PR・ChangeProposal参照
- Temporary作成物、cleanup対象、cleanup実施／未検証状態
- 永続採用／凍結／削除されたFile、Token・実行時間のBefore/After（実測可能時）
- 完了したGateと未実施の実Unity Gate、残るリスク

## Checklist

- [ ] 現行Testを検索し、重複した永続Testを追加していない
- [ ] 新規FileのPurpose・Reuse・Separation・Cost・Retirementを説明できる
- [ ] Stage A/B/Cを危険度に応じて使い分け、AIをHuman Approvalにしていない
- [ ] Existing Approval、Mutation Scope、Evidence Authorityを維持した
- [ ] TemporaryをTask完了時に片付け、最終回答前に残存を確認した
- [ ] 差分・凍結Test・他RunのFileを一括削除していない
- [ ] 現行Baselineと新正本を比較し、未観測をPASSと呼んでいない

## Common mistakes

- 調査用の一時テストを`tests/UnityAgentTest/`へ恒久保存する。
- Cleanupを会話セッションが終了するイベント一つに依存し、途中例外で取り残す。
- `git clean -fdx`、`git reset --hard`、広域の`rm -rf`で既存のユーザー変更を消す。
- 全TestにAI→別AI→人間の承認を強制し、Fast Pathを遅くする。
- Skill/CIの形式PASSをHuman Approvalと読み替える。
- 成功EvidenceだけでApproval偽造・Mutation Scope逸脱の失敗系を削除する。
- `tests/UnityAgentTest/`を完全なRegression Gateとして再利用する。
