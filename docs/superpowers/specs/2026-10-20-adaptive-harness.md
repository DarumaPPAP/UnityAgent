# UnityAgent 適応型ハーネス P0〜P1 設計

作成日: 2026-10-20 JST
状態: このCloud実装依頼の設計基準。適応型ハーネスの最初の導入単位。
基準: DarumaPPAP/UnityAgent `466eb6aa8267d479e9aa272fcb1f05b3c342d499`

## 目的

現行の安全契約・実行経路を維持しながら、適応戦略を評価するための観測と比較材料を作る。今回の実装対象は、現行説明の整合、途中戦略判定の観測、実行済み記録からのBaseline集計まで。実際の途中昇格・降格、動的Plan更新、実並列化、汎用変更Capabilityは後続段階とする。

## 正本と確認済みの制限

- Control Plane: `src/unityagent/control_plane/unity_agent_control_plane.py`
- 初期戦略: `src/unityagent/orchestration/routing/adaptive_execution.py`
- 直列Task DAG実行: `src/unityagent/control_plane/task_execution.py`
- Resource計画: `src/unityagent/orchestration/graph/resource_planning.py`
- Context: `src/unityagent/context/assembly/materialize_context.py`
- Evidence: `src/unityagent/persistence/evidence/evidence_store.py`
- Runtime観測: `src/unityagent/runtime/telemetry/runtime_telemetry.py`
- 現在の説明: `docs/architecture/adaptive-subagent-execution.md`

`select_execution_path`は初期選択として接続済み。Task DAGも依存と固定Acceptanceを持って実行できるが、現在は直列である。Runtime leaseとControl Plane Run lockは存在する。未確認の手動Editor操作・Device排他・性能改善を実装済みと記載しない。

## 維持する契約

1. UnityAgentが唯一のControl Plane。Orchestrationは意味判断、Runtimeは実行、Persistenceは永続記録を所有する。
2. `fast / standard / orchestrated`を維持する。Complexは説明上の呼称だけとする。
3. 戦略、既存execution profile、Context budget profileを混同しない。
4. Policy、Approval、Scope、必須Evidence、Project binding、Guard、Leaseを変更しない。
5. 既存の初期選択、CapabilityRequest、Runtime Handoff、Retry Budget、Task契約digest、Resume判定を変更しない。
6. 観測のための追加Model呼出し、Tool呼出し、SubAgent、Worktree、Project全体再走査を行わない。
7. 推定Context Tokenとモデル実usageを区別する。未計測を0に変換しない。
8. Golden期待値や評価用データをProduction Contextに注入しない。
9. Python >=3.10、現行PyYAML/jsonschemaを利用し、新規依存を追加しない。
10. 日本語ドキュメント・意図コメント、既存命名・改行規約、ユーザーの早期return／波括弧規約を適用する。

## 観測方式

既存初期選択関数を変更せず、同じRoutingモジュールに純粋関数`observe_execution_strategy`を追加する。入力は現在の経路、既存selectorと同じ型の確認済み条件、直前結果の分類。出力は観測専用の提案であり、Runtimeへの命令ではない。

判定結果は、`keep / promote / demote / blocked / not_evaluated`。`proposed_path`は三つの既存経路またはnull。必ず`applied: false`を記録する。

- 確認済みのTask数・専門担当・Review・再計画必要性などから、既存selectorで候補経路を計算する。
- 外部副作用不確定、環境不足、権限拒否、リソース競合、Context不足は、それを解決したと見なす戦略提案を出さない。停止理由として記録する。
- 必須入力が欠ける／不正な場合は`not_evaluated`と理由を記録する。推測値で補完しない。
- 候補経路は調整コストの提案であり、ApprovalやGateを削減できるという意味を持たない。
- 観測関数は渡された入力を変更しない。現在の戦略の順序は`fast < standard < orchestrated`とする。

現行Runtimeから得られない「残作業の分解」や「新たなScope」は、この段階では自動推論しない。入力がないため提案できないこと自体を測定対象とする。架空の途中適応能力を作らない。

## 永続記録と接続境界

新しい観測recordのSchemaをOrchestration契約下へ追加する。`run_id / step_id / current_path / proposed_path / recommendation / reason_codes / applied / evidence_refs / definition_fingerprint / input_digest`を持つ。Task DAGではTask idとAttemptも記録する。入力はallowlistされた構造化値のみとし、Provider引数・承認トークン・Source全文を保存しない。

記録は既存のimmutable snapshot関数とPersistence layoutを利用する。新しいDatabase、Store、Event Busは作らない。元の`orchestration_decision_ref`を上書きせず、`strategy_observation_refs`として追加参照する。観測recordをEvidenceの成功証拠へ混ぜない。

単一executeではRuntime結果とEvidenceが確定した後に一回評価する。DAGではTask／Attemptの結果とAcceptanceが確定した境界で評価する。Runtime実行中やProvider内部には接続しない。既存の早期blocked結果は無理に正常完了時のContextを捏造せず、Baseline集計で観測欠落理由を保持する。

補助的な観測の保存失敗で、既存のProvider実行を再送しない。既存Evidenceと実行結果は保持し、観測保存の失敗を戻り値の補助診断として明示する。Baselineの観測完全性は失敗扱いにする。エラーを無言で握りつぶさず、権限・Evidenceの既存失敗は従来どおり扱う。

## Baseline集計

保存済みRun／Task State／Context manifest／観測参照を読み取るオフライン集計を追加する。新しいProduction実行やモデル呼出しを開始しない。

出力は対象source revision、DefinitionFingerprint、観測対象id、各記録digest、経路分布、戦略提案分布、Gate状態、取得できたlatency、Context推定量、モデル実usageの取得状態、観測欠落を持つ。品質成功率には評価可能な対象だけを算入し、blocked／unavailableの件数と分母も別に報告する。単純に未観測を除外して全体の完遂率を高く見せない。

取得できる値だけを利用する。現在のRunner metricsに正規化された実Token総量はないため、P0〜P1でモデルToken計測Adapterは追加せず、`not_observed`として明示する。ローカルfixtureの時間をProduction latencyやUnity性能Baselineとは呼ばない。

既存Frozen Baselineと比較形式を上書きしない。異なるDefinitionFingerprint／source revisionのRunを無言で同一集団に混ぜず、別groupとして出力する。速度・Token改善の数値閾値は今回の機能の合否に使用しない。

## 成功条件

- 観測追加前後でCapabilityRequest、Handoff、Provider呼出し数・順序、変更Scope、Gate結果、実行結果statusが同じ。
- 現在の単一inspectionで追加Agent／Graph／Worktreeが生じない。
- 単一Task、専門分析、DAG、失敗、未計測を区別して記録できる。
- 提案を実行に反映しないことをテストで検証する。
- Task観測をResume時に再生成して過去事実へ重ねない。
- 不正／欠落した観測参照を集計時に成功扱いしない。
- 関連テスト、通常validator、wheel検証が通る。
- 実Unity／実モデルの測定を実行できなければ、計測基盤の検証完了と実Baseline未取得を分けて報告する。

## 導入後の判断

実Runの観測で提案頻度、入力不足、調整コストを確認してからP2の途中変更を設計する。昇格提案の存在は品質改善の証明ではない。観測だけで不要なコストが増える場合、機能を無効化または記録粒度を削減し、実経路は従来のまま維持する。

## 一次ソース

- [Control Plane](https://github.com/DarumaPPAP/UnityAgent/blob/466eb6aa8267d479e9aa272fcb1f05b3c342d499/src/unityagent/control_plane/unity_agent_control_plane.py)
- [Task実行](https://github.com/DarumaPPAP/UnityAgent/blob/466eb6aa8267d479e9aa272fcb1f05b3c342d499/src/unityagent/control_plane/task_execution.py)
- [初期経路選択](https://github.com/DarumaPPAP/UnityAgent/blob/466eb6aa8267d479e9aa272fcb1f05b3c342d499/src/unityagent/orchestration/routing/adaptive_execution.py)
- [Context Budget](https://github.com/DarumaPPAP/UnityAgent/blob/466eb6aa8267d479e9aa272fcb1f05b3c342d499/src/unityagent/context/budget/context-budget.yaml)
- [現在mainのCI](https://github.com/DarumaPPAP/UnityAgent/actions/runs/39370178428)
