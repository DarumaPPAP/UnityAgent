# 適応型ハーネス P0〜P1 実装・検証記録

対象: DarumaPPAP/UnityAgent。基準／HEADは `466eb6aa8267d479e9aa272fcb1f05b3c342d499`。GitHubコネクターで確認したmainも同じSHA。shellのfetchはproxy接続不可だったため、最新mainの照合はコネクターを使用した。開始時の作業ツリーはclean。

## 実装結果と判断

- 既存selectorを変えず、同じRoutingに純粋な `observe_execution_strategy` を追加。戦略順序に基づく観測提案と、停止／入力不足を区別する。`applied` はfalse固定。
- Control Planeの結果・Evidence確定後と、直列DAGの各AttemptのAcceptance確定後に、既存immutable snapshotへ観測を保存する。元のOrchestration decisionやEvidenceを置き換えない。
- 実行済みEvidenceを保持し、観測保存失敗を固定分類の補助診断として返す。Providerは再送しない。完了TaskのResumeで過去の観測を再生成しない。
- 現行Runtimeに残作業・再計画要否の確認済みFactがないため、初期選択の値を途中Factに再利用せず、空の `selection_inputs` で入力不足を記録する。正常境界の提案は `not_evaluated`。昇格・降格の実適用は追加しない。
- Baselineは明示した保存済みRunのみ読み取る。定義・source revision別にgroup化し、digest、Run／Task／Attempt、Context／Orchestration／Evidenceの参照を確認する。欠測・壊れた参照・保存失敗を残し、品質成功・全対象数・評価可能数・blocked／unavailable・実行完了を分ける。
- Runtime blocked＋Gate passedを品質成功にしない。既存Runtimeの停止理由を保持し、環境失敗の語彙をunavailableとして分離する。最終レビューで失敗テストを追加してから修正した。
- Context Token推定と実モデルusageを区別し、実usageと未取得latencyはnull。Task合計latencyは最終Attemptへ一度だけ付ける。既存Frozen Baseline／Comparatorを変更しない。
- 初期経路、CapabilityRequest、Handoff、Providerの回数・順序、Scope、Gate、Retry budget、Task契約digest、Resume条件、Policy／Approval／Project binding／Guard／Leaseは維持する。

## 適用手順と例外の判断

添付の設計・計画と直接実装の指示に従い、再承認では停止しなかった。Cloud checkoutを利用し、追加Worktree・SubAgentを作らなかった。`using-superpowers`、`brainstorming`、`executing-plans`、TDD、`systematic-debugging`、検証・レビュー・終了手順、managed cloud環境手順とRepositoryの日本語コメント規約を確認した。

Python基盤に直接対応するTask Routeがないため、generic-planningのContextを試行した。budgetは `unmeasured` であり、読み取り専用のgeneric-planning契約を実装権限の正本には使っていない。変更範囲・権限は今回の明示実装依頼に従う。Policy provenanceはUser Policyの `evidence_scoped_claims` を保持する。

追加SubAgent禁止の明示指示を優先し、レビュー手順の別Agent要求は実行せず、著者の自己レビューを行った。独立レビュアーの検証は未実施。延期した軽微項目はない。

## 現在の差分に対する検証

作業用venv: `/workspace/adaptive-venv`。製品依存の追加なし。既存 `setup.py build_resources` で配布resourceを生成。初回のmodule／resource未準備を解消後、既存Project Leaseのユーザー領域への書込みを許可した実行で基準42件がPASS。権限回避のための製品コード変更は行っていない。

| 検証 | 結果 |
|---|---|
| 観測判定・Control Plane・DAG・Baseline・既存Comparatorの関連suite | 最終85件PASS |
| `PYTHONDONTWRITEBYTECODE=1 python tools/validate_all.py` | PASS。計790件を実行（既存skip 1件を含む） |
| `python -m build` | 最終コードからsdist／wheelのビルド成功 |
| `python tools/verify_installed_wheel.py --wheel dist/unityagent_control_plane-0.0.8b0-py3-none-any.whl` | checkout外の一時venvでPASS。261 resourceのhash、CLI、Fingerprint、新戦略Schemaの同梱・妥当性を確認 |
| `git diff --check` | PASS |

最終validatorの途中実行では、前回テストが生成した `tests/unity/verify/__pycache__/collect_evidence.cpython-312.pyc` を既存packagingテストがfixtureとして列挙し、1件失敗した。この作業で生成された該当cacheだけを削除し、bytecode無効で再実行して全体PASSを確認した。既存fixture／testの変更は行っていない。

新規関数・集計の未実装失敗、保存失敗、別Run参照、欠落digest、不正失敗入力、Runtime blockedの品質誤成功、Runtime停止理由の欠落をそれぞれテストで確認し、修正後に成功を確認した。fixtureの時間はUnity性能やProduction改善の値として使っていない。

## 未実行・未観測

実Unity Editor／Player／実機／Visual／Performanceの検証は環境利用条件がなく `unavailable`。実モデルを使う追加の計測は実行していない。実Baselineは `not_observed` で、検証はfixtureと保存形式・集計基盤に限定する。今回生成したfixtureの結果を実Baselineとして保存・公開していない。

実際の途中戦略変更、動的Task Plan、並列実行、Queue、Device lease、汎用変更Agent、UIは対象外。外部UnitySubAgentHubのRepositoryや履歴は変更していない。

## 実装完了時のGit状態（追加のPR作成依頼前）

以下は実装完了時点の記録。後続の明示依頼でCommit・Push・PR作成が許可された。

branchは `feature/adaptive-harness-observation`。HEADは基準SHAのまま、成果物は未コミット差分として保持。Commit・Push・PR作成・Merge・Releaseは実行していない。

## 変更ファイル

- `docs/README.md`
- `docs/architecture/adaptive-subagent-execution.md`
- `docs/architecture/architecture.md`
- `docs/architecture/specialist-context-assembly.md`
- `docs/superpowers/plans/2026-10-20-adaptive-harness-plan.md`
- `docs/superpowers/reports/2026-10-20-adaptive-harness-validation.md`
- `docs/superpowers/specs/2026-10-20-adaptive-harness-design.md`
- `eval/regression/adaptive-baseline.schema.yaml`
- `src/unityagent/control_plane/task_execution.py`
- `src/unityagent/control_plane/unity_agent_control_plane.py`
- `src/unityagent/orchestration/contracts/strategy-observation.schema.yaml`
- `src/unityagent/orchestration/routing/adaptive_execution.py`
- `src/unityagent/persistence/contracts/execution-state.schema.yaml`
- `tests/eval/test_adaptive_execution_baseline.py`
- `tests/orchestration/test_adaptive_execution.py`
- `tests/runtime/test_control_plane.py`
- `tests/runtime/test_task_dag_execution.py`
- `tools/adaptive_execution_baseline.py`
- `tools/verify_installed_wheel.py`
