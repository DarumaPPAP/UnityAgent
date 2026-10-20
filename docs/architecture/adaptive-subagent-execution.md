# 適応実行・SubAgent統合実行方針

UnityAgentが唯一のControl Planeです。同居SubAgentの正本は `subagent/<id>/manifest.yaml` と参照先、Runtime Profile・Activation・Contextの正本は `src/unityagent/runtime/reference_implementation/subagent-catalog.yaml` です。QAの正本IDは `qa_subagent`、現在の性能分析Capabilityは `performance.analyze` です。

## 初期戦略と直列Task DAG

`select_execution_path` はControl Planeの初期選択へ接続済みです。戦略は調整コストの判断であり、実行許可ではありません。

| 経路 | 選択条件と現在の挙動 |
|---|---|
| `fast` | 単一・低リスク・既知Scope／Project・Review不要。inspectionは追加Agent／ParentGraph／Worktreeなしで直接実行 |
| `standard` | 単一専門Task、追加Review・検証・Contextが必要なTask |
| `orchestrated` | 複数Task／専門担当、リソース調整が必要な計画 |

Complexは説明上の呼称に限ります。既存execution profile、Context budgetの `tight / standard / wide` とは別の概念です。

`plan_task_batches` はDAGと競合を計画します。`execute_tasks` は依存と固定Acceptanceを持つTaskを**直列**で既存executeへ接続します。完了TaskのResumeは再送せず、不確定副作用は照合を要します。計画のparallel判定は並列実行の許可や実測速度向上を意味しません。動的Task Plan更新・実並列化・Worktree分割は実装していません。

## 途中戦略の観測

`observe_execution_strategy` は既存selectorを再利用する純粋関数です。確認済みの選択条件が揃った場合だけ `fast < standard < orchestrated` の順で `keep / promote / demote` を提案します。環境・権限・Scope・競合・Context不足や不確定副作用は理由付きの `blocked`、必須入力の欠落／不正は `not_evaluated` とします。`proposed_path` があっても `applied` は常にfalseです。

現在のRuntimeには残作業の分解や再計画要否を再確認するFactがありません。結果確定時の接続では、初期選択の値を残作業と見なさず空の `selection_inputs` を渡します。正常実行でも `not_evaluated` となり、入力不足自体を記録します。新しいScopeや昇格理由を推論せず、追加のモデル・Tool・SubAgent呼出しやProject全体走査も行いません。

単一executeはRuntime結果とEvidence appendの後に一回、DAGは各Task／AttemptのAcceptance確定後に保存します。早期blockedではContext／Handoffを捏造しません。観測は既存Persistenceのcontent-addressed snapshotへ保存し、戻り値とExecutionState／TaskStateの `strategy_observation_refs` から参照します。元の `orchestration_decision_ref` は維持し、観測参照をEvidenceやAcceptanceの成功証拠へ混ぜません。

記録Schemaは `src/unityagent/orchestration/contracts/strategy-observation.schema.yaml` です。Run・Step・Task／Attempt・実行子Run・DefinitionFingerprint・入力digest・Evidence参照に結び付けます。Provider引数、承認Token、Source全文は記録しません。

観測保存失敗は `strategy_observation_diagnostics` へ固定分類で明示します。既存の結果・Evidenceを保持し、Providerを再送しません。参照保存の失敗も診断します。補助観測の失敗と、既存Evidence／権限の失敗を混同しません。Resumeでは完了済みTaskの観測を再生成しません。

## 親DAGの境界判定情報

`build_dag_inputs` は固定Task契約とAcceptance確定後の状態から、完了Task、残Task、依存成立Task、失敗／利用不可／依存阻害／実行中Task、意味的修復Attemptと残予算を区別します。残Task数は実行可能Task数とは別で、失敗や依存阻害を残作業から消しません。残作業ゼロは終了境界として記録し、既存selectorへ0を渡しません。

`dag_decision_refs` は従来の子Run用 `strategy_observation_refs` とは別の親DAG記録です。Control Planeは各AttemptのEvidence・Acceptanceと意味的継続判定が確定した後だけ呼び出します。`dag-boundary` snapshotにその時点の入力・出所を保存し、`dag-decision` snapshotを固定Task契約、親DefinitionFingerprint、Project revision、Run／Task／Attemptへ結び付けます。後から更新されるcurrentファイルを当時の根拠には使いません。

現在Taskのrisk・Review・専門担当・Context profile・binding／Scopeは、検証済みのOrchestration proof、Context manifest、同一Project revision、既存の意味的継続判定から取得できる項目だけを記録します。Evidenceは `EvidenceStore.verify_record` でevent chainとRun・定義を確認します。Project変更後のFactは有効扱いせず、欠測と参照不整合は別に診断します。生の結果・Provider引数・Source全文を新しいsnapshotへ複製しません。

保存参照の読取検証はPersistenceの `read_dag_record`、Fact・入力・判定結果の再計算はOrchestrationの `adaptive_execution.read_dag_decision` が担当します。利用側は後者を通し、出所の存在だけでなく値の一致も確認します。境界snapshotには再計算に必要な最小Task状態を保持し、Task単位の停止理由からRunner／環境の利用不可を実行失敗と区別します。

未実行Taskや別の修復候補には完了TaskのFactを転用しません。将来TaskのContext生成や追加Project走査も行いません。残作業に必要な選択条件は項目ごとの不足理由を持ち、全項目が確認済みの場合だけ既存selectorで候補を求めます。この観測形式の親DAGには比較可能な戦略値がないため `current_path` はnullです。子Taskのfastと親DAGの調整を比べて昇格・降格とは記録しません。実行への適用は引き続きfalseです。

補助保存失敗は `dag_decision_diagnostics` にTask／Attempt付きで記録し、Provider・モデルを再送しません。Resumeで完了済み境界を再生成しません。Baselineの任意 `dag_decisions` に親の観測完全性を出し、従来の子Attemptの品質分母・経路分布は維持します。P0〜P1形式だけのRunも従来どおり読めます。適用履歴を持つRunでは、任意の `strategy_applications` に状態別件数・未完了・不正参照を出します。`accepted` と `finalized` を分け、Gate成功率へ混ぜません。

## opt-inによる親Runの調整モード適用

`UnityAgentControlPlane.execute_tasks(..., adaptive_strategy_enabled=True)` で有効にします。既定値はfalseで、無効時には適用Callback・追加監査・適用履歴を生成しません。旧形式Runは無効のままResumeできます。開始後の有効／無効切替は拒否します。

適用対象は一貫して `{kind: parent_dag, run_id: 親Run}` です。このモードは**次の準備済みAttemptをdispatchする前の監査の深さ**を制御します。子Taskの初期経路や残Task全体の複雑度とは区別します。残Task数の減少だけで昇格を作らず、未来TaskのFactも代入しません。子の初期selector・CapabilityRequest・専門担当・Context予算は変更しません。

| 今回確認した条件 | 次の親モード | 実行側が行う処理 |
|---|---|---|
| 通常の準備済み単一Attempt | 既存selectorの経路（低リスクinspectionは `fast`） | 準備と固定契約・Project／定義／Scopeの束縛、Contextが読んだFactの鮮度を検証 |
| 直前の固定Acceptanceが失敗し、既存の意味的判定が `continue`、読取処理、固定修復候補・残予算あり | `standard` | 共通検証に加え、直前AcceptanceのEvidence・履歴・予算・子結果と現在状態を監査 |
| 今回Taskの固定契約に依存・リソース要求・write setあり | `orchestrated` | Standardの監査に加え、固定DAGと依存成立、準備済み変更Scopeとwrite setの包含を監査 |

初回は `initialize`、同じモードは `keep`、同じ親Runで `fast < standard < orchestrated` の順に上がれば `promote`、下がれば `demote` です。各条件が実際に変われば三モード間の遷移を許可します。例えば通常inspection → 承認済み読取修復 → 次の通常inspectionでは `fast → standard → fast` となります。専門計画 → 通常inspectionでも降格できます。環境・権限不足・不確定副作用を修復可能と扱わず、既存の停止・修復予算を維持します。未確認入力、契約外Scope、参照改変、依存不成立、保存失敗ではdispatchを開始しません。

Control Planeは既存のRoute・CapabilityRequest・Context・Handoffを一度だけ準備した後、同じ値を適用処理へ渡します。適用のための追加モデル／Provider呼出しやProject全体走査はありません。Runtimeの `execution_control.strategy.consume_strategy` が選択モードに応じて監査を呼び、拒否時は既存Runtime処理へ進みません。全モードでPolicy・Approval・Scope・必須Gate・Evidence・Retry Budget・Run lock・Editor leaseを維持します。DAGは直列のままです。必須Observationの後に専門Contextを再構築する既存経路では、receiptは最初のdispatch準備を指し、更新後のContext・成果は最終Acceptance境界の出所で追跡します。

記録は既存の `strategy_observation_refs`・`dag_decision_refs` と別の `strategy_application_refs` です。既存観測の `applied:false` は上書きしません。`strategy-preparation` に準備の出所を保存し、`strategy-application` に次の状態をimmutableな参照chainで保存します。

| 状態 | 意味 |
|---|---|
| `prepared` | 適用前の入力・契約・判定を保存。`applied:false` |
| `accepted` | Runtimeが実際の監査を受理し、receiptを永続化。`applied:true`。Provider成功の意味ではない |
| `dispatching` | Provider等へ進む直前の耐久境界。結果未確定なら副作用を推測しない |
| `finalized` | 固定Acceptance確定後の検証済み親境界へ結合。Gate失敗も失敗として確定する |
| `rejected` | 実行側の事前監査で拒否。`applied:false` |
| `interrupted` | dispatch開始後に例外／中断。副作用不確定としてResumeで自動再送しない |

拒否・準備不足で受理されなければ後続dispatchも止め、未実行Taskをpendingのまま保持します。受理／dispatch記録の保存に失敗すればProviderへ進みません。実行後の境界・確定保存の失敗では既存Evidenceと結果を保持して後続dispatchを停止します。`dispatching` のままのクラッシュ、中断、孤立snapshot、未完了履歴、参照の欠落・改変は照合を要し、Resumeで自動再実行しません。完了済みRunのResumeでは履歴を再生成しません。

読取は `orchestration.routing.strategy_application.read_strategy_application` を使用します。Schema・snapshot digest・chain順・準備の出所・初期選択・親判定・Runtime receipt・固定Acceptance境界を再検証します。ResumeではさらにcurrentのTask状態・子結果・Evidence集合・Attempt履歴・予算・固定実行順を確定境界と照合します。既存のFact／出所／判定読取検証も維持します。

専門処理の `world.plan` は出力Schema・意味契約・Context binding・変更観測を通ったArtifactだけを `world_plan` のEvidenceとして正規化します。読取時も同じ子Run内のArtifact存在・digestを検証します。このEvidenceだけでEditor／Player／実機／VisualのGateは通りません。

## 保存済みRunのBaseline集計

次のコマンドは明示した保存済みRunだけを読み、Production実行を開始しません。

```sh
python tools/adaptive_baseline.py \
  --persistence-root /path/to/persistence \
  --run-id saved-run-id \
  --source-revision recorded-source-sha \
  --output /path/to/new-adaptive-baseline.json
```

`--run-id` は複数指定できます。同じRunは重複計上しません。DAG親を指定した場合は各Task／Attemptを集計し、子Runは自動追加しません。子Runも別途指定すればそれぞれ独立の観測対象となります。

- `source_revision` とDefinitionFingerprintでgroupを分けます。既存Runにsource revisionがなければ呼出し側の宣言を使用し、`source_revision_provenance` で区別します。記録だけから実際のソースrevisionを推測しません。
- snapshot digest、Run／Task／Attempt、入力digest、Schema、Context／Orchestration／Evidence参照のbindingを検証します。不正・欠落・保存失敗は `observation_completeness: failed` と欠落理由へ残し、品質成功に数えません。
- Evidenceは既存EvidenceStoreのevent chainと保存時record hashを照合します。Contextは観測recordの有効なpolicy／context revision、Routing Proofは対象manifest参照も照合します。
- Reasoning前の再Materializationでは、Proofが示す直前Contextと、必須Observation参照またはCapabilityRequestのCapability／Stepに対応するTool結果だけを旧Contextへ結び付けます。Reasoning結果は再構築後の定義で検証し、任意の過去Contextを許可しません。
- 経路・提案分布、固定Gate状態、観測可能な対象だけの品質成功率と分母、blocked／unavailable、実行完了件数を別々に出します。単一executeの固定Acceptance未定義は品質の `not_evaluated` です。欠測を総対象数から除外しません。
- Taskの既存 `latency_ms` はTask合計の壁時計時間として最終Attemptに一度だけ付けます。未取得はnullです。各記録のdigestも保持します。
- Attemptの戦略観測が欠けた場合、対応する子RunのExecutionStateから実行状態だけを確認します。その状態も読めなければ未観測とし、最終Taskの成功を過去Attemptへ流用しません。
- Contextの `estimated_tokens` は推定量です。正規化された実モデルusageの取得機能は追加せず、`model_usage.status: not_observed`、`total_tokens: null` とします。欠測を0へ変換しません。

出力は `eval/regression/adaptive-baseline.schema.yaml` で検証します。Persistence内への出力と既存ファイルの上書きを拒否し、既存Frozen Baseline／Comparatorは変更しません。fixtureの実行時間をProduction latencyやUnity性能改善として報告しません。

## 排他・権限と未実装範囲

小さいTaskでもPolicy／Approval／Project binding／Scope／Guard／必須Evidenceを維持します。戦略提案からGateを省略できません。

Control PlaneのRun lockは同一Host／userの物理Projectを排他し、Evidence保存まで保持します。Runtimeの `resource_lease.py` はEditor利用CapabilityとMutationのProvider実行中を保護します。取得順はRun lock → Provider単位Editor leaseです。期限切れによる自動奪取や別ProviderへのFallbackで競合を回避しません。

これらはUnityAgent経由の協調処理の排他です。手動Editor操作、Unity自身のProject Lockとの統合、Queue、Device lease、汎用変更Agentは未実装です。途中戦略の適用範囲は上記opt-inのdispatch前監査に限ります。外部Hubの履歴や互換Source Lockは変更しません。

## 検証範囲

Hostのunit test・fixture・Schema・validator・wheel resource検証と、実Unity／実モデルの検証は分けます。今回のfixture成功は実Baseline取得や性能改善を意味しません。実Unity Editor／Player／実機／実モデルの利用条件がない場合、検証は `unavailable`、実Baselineは `not_observed` と報告します。

現在の挙動の正本はコード・Schema・テストです。
