# UnityAgent 適応型ハーネス P0〜P1 実装計画

> 実行方式: Cloudタスク内での直接実装。利用可能な適用Skillに従ってタスク単位で検証する。
**Goal:** 現行経路を変更せず、途中戦略の観測と保存済み実行のBaseline集計を追加する。

**Architecture:** 既存の初期selectorを維持し、Orchestrationに純粋な観測判定を追加する。Control Planeの結果確定境界で呼び、既存Persistence snapshotへ保存する。オフライン集計は保存済み参照だけを読み、実行を起動しない。

**Tech Stack:** Python >=3.10、既存PyYAML/jsonschema、unittest。

**Spec:** この依頼に同梱したP0〜P1設計。Repository保存先は既存文書構成に従う。

## Global Constraints

- 対象revisionは`466eb6aa8267d479e9aa272fcb1f05b3c342d499`。開始時にmainが進んでいれば関連差分を照合して基準を更新する。
- `fast / standard / orchestrated`を維持する。Complexは説明上の呼称だけとする。
- Policy、Approval、Scope、必須Evidence、Project binding、Guard、Leaseを変更しない。
- 既存の初期選択、CapabilityRequest、Runtime Handoff、Retry Budget、Task契約digest、Resume判定を変更しない。
- 観測のための追加Model呼出し、Tool呼出し、SubAgent、Worktree、Project全体再走査を行わない。
- 推定Context Tokenとモデル実usageを区別する。未計測を0に変換しない。
- Golden期待値や評価用データをProduction Contextに注入しない。
- Python >=3.10、現行PyYAML/jsonschemaを利用し、新規依存を追加しない。
- 日本語ドキュメント・意図コメント、既存命名・改行規約、ユーザーの早期return／波括弧規約を適用する。
- 実際の途中昇格・降格、動的Plan更新、実並列化、汎用変更Capabilityは後続段階とする。

## Review Focus

1. 権限／環境／リソース不足を、戦略昇格で解消したように扱わない。Task 1で各停止理由をテストする。
2. 観測の追加がProvider実行順序やGate結果を変更しない。Task 2で実行前後の差分を比較する。
3. Resume／修復Attemptで観測記録を重複・上書きしない。Task 2で同じ完了Taskの再開と別Attemptをテストする。
4. 観測保存失敗を隠さず、Provider再送も起こさない。Task 2で保存失敗を注入し、実行済みEvidence保持と補助診断を検証する。
5. 異なる定義・欠測・壊れた参照をBaselineへ無言で混ぜない。Task 3で分離／欠測／失敗を検証する。

## 作業開始条件

- [ ] 最新mainと基準SHAを照合する。
- [ ] Cloudタスクのcheckoutを使用し、Git状態と既存変更を確認する。別のローカルcheckoutへアクセスしない。
- [ ] checkout内の適用AGENTS.md、User Policy、Branch Policy、コメントSkill、対象領域の規約を読む。
- [ ] 既存テスト`tests.orchestration.test_adaptive_execution`、`tests.runtime.test_control_plane`、`tests.runtime.test_task_dag_execution`を実行して開始時の結果を保存する。
- [ ] この依頼の範囲で、Cloudタスク内での直接実装を開始する。

## Task 1: 観測判定とデータ契約

**Files**

- Modify: `src/unityagent/orchestration/routing/adaptive_execution.py`
- Create: `src/unityagent/orchestration/contracts/strategy-observation.schema.yaml`
- Modify: `tests/orchestration/test_adaptive_execution.py`

**Interfaces**

- Consumes: 現在の`select_execution_path(**kwargs)`が要求する型付き条件。
- Produces: `observe_execution_strategy(*, current_path: str, selection_inputs: dict[str, Any], failure_class: str | None = None, uncertain_side_effects: bool = False) -> dict[str, Any]`。
- 戻り値は`recommendation / current_path / proposed_path / reason_codes / applied`。`applied`は常にfalse。完全な永続recordはTask 2でRunとEvidence参照を付ける。
- 正常な入力は既存selectorへ委譲。既存selectorそのものの挙動は変更しない。不完全な入力は`not_evaluated`、環境・権限・競合・不確定副作用は`blocked`で`proposed_path: null`。

- [ ] 失敗テストを書く。`test_observe_keep_fast`は`keep / fast / false`、`test_observe_promote_specialist`は`promote / standard / false`、`test_observe_promote_multiple_tasks`は`promote / orchestrated / false`、`test_observe_demote_single_remaining_task`は`demote / fast / false`を期待する。
- [ ] `test_observe_blocked_failure_never_promotes`でapproval／scope／environment／resource／不確定副作用を列挙し、提案pathがnullで理由を保持することを確認する。
- [ ] `test_observe_missing_and_invalid_facts`で欠落、boolをtask_countに渡す、unknown経路／riskを検証する。`test_observe_does_not_mutate_inputs`で入力が不変であることを確認する。
- [ ] `python -m unittest tests.orchestration.test_adaptive_execution -v`を実行し、追加機能が未定義で失敗することを確認する。
- [ ] 最小実装とSchemaを追加する。Schemaは余分なフィールドを拒否し、`applied`をfalseへ固定する。汎用Manager／State Storeは追加しない。
- [ ] 同じテストを再実行し、既存初期selectorの全テストと新規テストの成功を確認する。
- [ ] 差分と規約を自己レビューする。Commitはユーザーの実行範囲・Repository Policyに従う。

## Task 2: Control Planeへの観測のみの接続

**Files**

- Modify: `src/unityagent/control_plane/unity_agent_control_plane.py`
- Modify: `src/unityagent/control_plane/task_execution.py`
- Modify: `tests/runtime/test_control_plane.py`
- Modify: `tests/runtime/test_task_dag_execution.py`

**Interfaces**

- Consumes: Task 1の`observe_execution_strategy`、既存Context manifest／execution_plan／Runtime結果／Acceptance。
- Produces: 結果に追加する`strategy_observation_refs: list[str]`と、観測失敗時だけの構造化補助診断。
- 永続化は既存`write_immutable_json / relative_ref / sha256_json`とlayout snapshotを利用。recordはTask 1のSchemaで検証する。既存のOrchestration proofやEvidenceを上書きしない。
- 単一RunはRuntime結果とEvidence append後、DAGは各AttemptのAcceptance確定後に記録する。利用可能な確認済み条件だけを入力する。推測でrequires_replan等を立てない。

- [ ] 追加テストを書く。`test_observation_preserves_dispatch_and_handoff`で既存CapabilityRequest、Handoff、Provider回数・順序、status、Gate結果が同じことを比較する。
- [ ] `test_fast_observation_does_not_load_graph_or_spawn_worker`、`test_observation_is_diagnostic_not_acceptance_evidence`、`test_missing_optional_observation_does_not_fabricate_context`を書く。
- [ ] DAGに`test_attempt_observations_are_distinct`、`test_resume_does_not_duplicate_completed_observation`、`test_observation_proposal_is_never_applied`を書く。提案pathが違っても実行経路・依存・Retry予算が変わらないことを確認する。
- [ ] `test_observation_persistence_failure_does_not_replay_provider`でsnapshot保存失敗を注入する。Providerは一回、既存Evidenceは残り、補助診断が返ることを確認する。
- [ ] 関連3suiteを実行し、追加契約がないため新規テストが失敗することを確認する。
- [ ] 最小接続を実装する。既存の承認・Guard・Leaseの前後関係と早期blocked処理を維持する。新規の環境探索やモデル呼出しは追加しない。
- [ ] 関連3suiteを再実行し成功を確認する。Lease／権限／Evidence／Resumeの既存テストも実行する。
- [ ] 保存recordと参照のdigest、別Run／別AttemptとのBindingを検査する。

## Task 3: 保存済みRunからのBaseline集計

**Files**

- Create: `tools/adaptive_execution_baseline.py`
- Create: `eval/regression/adaptive-baseline.schema.yaml`
- Create: `tests/eval/test_adaptive_execution_baseline.py`

**Interfaces**

- Consumes: 明示されたPersistence root、run id、source revision。既存Run state／manifest／observation参照をread-onlyで取得する。
- Produces: `build_adaptive_baseline(persistence_root: Path, run_ids: list[str], *, source_revision: str) -> dict[str, Any]`。
- CLI: `python tools/adaptive_execution_baseline.py --persistence-root <root> --run-id <id> --source-revision <sha> --output <path>`。`--run-id`は複数指定可能。
- 出力はSchema付き。record digest、定義別group、経路／提案分布、Gate状態、取得済みlatency／Context推定量、モデル実usageの未観測状態、観測欠落を含む。

- [ ] `test_group_by_definition`、`test_missing_usage_is_not_zero`、`test_context_estimate_is_not_billed_tokens`、`test_blocked_and_unavailable_are_reported_separately`を書く。
- [ ] `test_corrupt_or_cross_run_reference_is_rejected`、`test_duplicate_run_is_not_counted_twice`、`test_export_does_not_modify_inputs`、`test_no_runtime_or_model_is_launched`を書く。
- [ ] `python -m unittest tests.eval.test_adaptive_execution_baseline -v`を実行し、集計機能が未定義で失敗することを確認する。
- [ ] 純粋集計とCLIを実装する。fixture計測をProduction性能値へ変換しない。既存Frozen BaselineとComparatorを変更しない。
- [ ] 同テストと既存Baseline Comparatorテストを実行する。CLI出力を新Schemaで検証する。
- [ ] 実Runが利用可能なら明示した入力から集計し、計測環境と対象revisionを保存する。なければfixture検証のみとし、実Baselineは`not_observed`として報告する。

## Task 4: 現行ドキュメントの整合と全体検証

**Files**

- Modify: `docs/architecture/adaptive-subagent-execution.md`
- Modify: `docs/architecture/specialist-context-assembly.md`
- Modify: `docs/architecture/architecture.md`の関連説明だけ
- Add: 上記spec／planのRepository配置

**Interfaces**

- Consumes: Task 1〜3で実装・検証した現在の挙動だけ。
- Produces: 初期選択、観測のみの途中提案、直列DAG、未実装の途中変更／Queue／並列化を分けた説明。

- [ ] 実コードに合わせて同居SubAgent正本・QA alias・Task DAG実行状態を修正する。Hub Repositoryや履歴自体は変更しない。
- [ ] 再現可能な集計コマンド、観測保存失敗の扱い、推定／実測の区別、実Unity未検証を記載する。
- [ ] `python tools/validate_all.py`を実行する。失敗した場合は今回の差分と既存問題を切り分ける。
- [ ] `python -m build`と`python tools/verify_installed_wheel.py --wheel <生成wheel>`を実行する。Schema同梱とインストール後のresource解決を確認する。
- [ ] `git diff --check`と変更箇所の規約・Authorityレビューを行う。
- [ ] 現在の成果物に対する成功・失敗・未実行項目、実Baselineの有無、変更ファイルを報告する。古いCI PASSを変更後の検証結果に流用しない。

## 実行方式とGit範囲

Cloudタスク内で直接実装する。Git操作の範囲はこの依頼冒頭に従う。PR作成・Merge・Releaseは追加実行しない。

## 計画の自己レビュー

- 対象はP0〜P1だけ。戦略の実適用、動的Task Plan、Device leaseは含めていない。
- 新しい関数はTask 1、接続はTask 2、集計はTask 3で定義済み。
- Review Focusの5項目はそれぞれ対応テストを指定済み。
- 観測不足から架空の昇格理由を生成しない。
- 計測基盤のテスト成功と実モデル／UnityのBaseline取得を別状態として報告する。
