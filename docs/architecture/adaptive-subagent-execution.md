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

`plan_task_batches` はDAGと競合を計画します。`execute_tasks` は依存と固定Acceptanceを持つTaskを**直列**で既存executeへ接続します。完了TaskのResumeは再送せず、不確定副作用は照合を要します。計画のparallel判定は並列実行の許可や実測速度向上を意味しません。動的Task Plan更新は下記の明示opt-inで利用できます。実並列化・Worktree分割は実装していません。

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

読取は `orchestration.routing.strategy_application.read_strategy_application` を使用します。Schema・snapshot digest・chain順・準備の出所・初期選択・親判定・Runtime receipt・固定Acceptance境界を再検証します。同じTask／Attemptの再出現を拒否し、確定済み適用履歴と境界の実行済みAttempt集合を一致させます。準備時のProject revisionは直前のAcceptanceと今回のdispatch境界へ結び付けます。ResumeではさらにcurrentのTask状態・子結果・Evidence集合・Attempt履歴・予算・固定実行順・最新境界を確定履歴と照合します。既存のFact／出所／判定読取検証も維持します。

opt-in時は従来のTask開始時Project走査を、`dispatching` 保存後・Provider呼出し前へ移します。準備や保存中に変わったAssets／Packages／ProjectSettingsも拒否し、不確定なdispatchをResumeで再送しません。修復なしの通常実行では全走査回数を増やしません。固定修復Attemptにも送信直前の走査を行うため、修復ありの実行ではそのAttempt分の検証が加わります。

専門処理の `world.plan` は出力Schema・意味契約・Context binding・変更観測を通ったArtifactだけを `world_plan` のEvidenceとして正規化します。読取時も同じ子Run内のArtifact存在・digestを検証します。このEvidenceだけでEditor／Player／実機／VisualのGateは通りません。

## Root契約を保持する動的直列Plan

`execute_tasks(..., root_contract=root, plan_proposer=propose)` は `TaskState.schema_version: 2.0` を作成します。`root_contract` を省略した固定DAGの形式・既定動作は維持します。`adaptive_strategy_enabled=True` と併用でき、同じ親Runで現在PlanのTaskを既存executeへ直列に渡します。Planの有効／無効、最初のTask契約、Root、DefinitionFingerprintをResumeで変更できません。

Rootは `goal`、最終Gateの対象 `project_root`、許可Projectごとの `projects: {path: {read_set, write_set}}`、`required_gates`、`approval_conditions: [existing_policy]` を持ちます。必要なら `allowed_entry_kinds` でTyped Intentを限定します。現在のEntry準備はProject全体のFactを読むため、各Taskの `read_set` と対応するRootのread Scopeには `.` の明示が必要です。限定読取を保証できると推測して狭いScopeを許可しません。Taskの変更Scopeは実際の準備済みHandoffにも照合し、既存ApprovalとToolBrokerを維持します。未知の承認条件は受理しません。

`propose` はTaskの全AttemptとAcceptanceが確定した境界だけで呼びます。引数は現在の `plan`、`plan_digest`、`completed_task_id`、Project revision、確定した子Runの `evidence_refs` です。更新が不要ならNoneを返します。更新時は次の契約を返します。

```python
{
    'base_digest': boundary['plan_digest'],
    'tasks': replacement_tasks,
    'reason': 'additional_inspection',
    'evidence_refs': boundary['evidence_refs'],
}
```

`replacement_tasks` は継続する実行済みTaskと次に実行する未実行Taskの全体です。未実行Taskの追加、取消、分割、置換、依存調整を検証してから実行側が消費します。完了・実行中・停止済みTaskの変更、取消IDの再使用、修復Attemptと衝突するTask ID、cycle、未知依存、Root Gateの弱化、Scope拡張、古いbaseを拒否します。新TaskのRuntime引数は呼出し側の `task_parameters` に必要で、既存承認を自動複製しません。提案Callbackのためにモデル・Provider・未来TaskのContextを追加実行しません。

親Runの予算は受理更新2回、全revisionを通じてTask ID最大32件、提案4回です。Task修復予算とは別に保存し、拒否も提案予算を消費します。上限後は提案Callbackを呼びません。Rootの `required_gates` は各Taskの最低Gateとしても保持します。

Plan Schemaは `src/unityagent/orchestration/contracts/plan.schema.yaml`、純粋検証は `orchestration/graph/plan.py`、snapshotとactive切替は `persistence/state/plan.py` が所有します。検証snapshotを保存しただけではactiveになりません。active切替は既存親Run lock内でbaseを再照合し、Task集合・契約参照・active参照を一度のatomic TaskState保存で切り替えます。過去Planはprevious digestとjournalに保持します。Task確定・提案拒否にも別のappend-only journalを持ち、本文とcurrent参照の同時切詰め、予算巻戻し、切替途中の失敗を検出します。保存失敗・提案中断・不確定AttemptをResumeで再送しません。

Task結果は実行時Plan、Task定義digest、入力／結果Project revisionへ結び付け、歴史的AcceptanceとEvidenceを保持します。最終Gate直前に実Projectを再走査し、最終Root Projectの同一revisionに対するGateだけを採用します。古い結果は `evidence_validity: stale` とし、現在の最終PASSへ転用しません。検証が必要なら別IDの検証Taskを現在Planへ追加します。

動的DAGの境界は `dag-decision.schema_version: 2.0` とPlan参照を持ち、固定の辞書順ではなく実際の確定済み実行prefixを検証します。既存の1.0 readerは維持します。ResumeとBaselineは全Plan chain、提案の再検証、Task確定receipt、実行済み集合、Evidence、現在契約を照合します。不完全な動的記録はBaselineの品質成功に数えず、有効Planに存在する欠落Taskを分母から落としません。

この入口は既存のinspection／planning等を使うHost契約経路です。限定C#修正、別Workspaceのworker、統合後Gateは以下の別入口で扱い、実Unity／実モデル／性能採用判定は契約検証と区別します。

## 別Workspaceのworkerと承認済み直列統合

`execute_workspace_tasks(tasks, run_id=..., definition_fingerprint=..., task_parameters=..., root_contract=..., parallel_enabled=False)` は同じRoot／Plan契約を使います。`parallel_enabled=True`でも、依存成立・`parallel_safe`・独立したProjectと出力・非競合Host claimを確認できた最大2 Taskだけをworkerで処理します。Rootには原Projectと全workerの許可Scopeを初期から明示します。Taskは限定C#修正またはinspectionに限定し、暗黙の修復候補を受け付けません。

Projectと子のdev／inode、全配下のsymlink・junction・hardlink、Git管理領域、EnvironmentのProject bindingとEditor状態、実際のNative Providerの出力先を検査します。共有Gitや不明なEditorでは直列化し、原Project別名や未知のNative出力は拒否します。Projectの置換は同じ内容でもResumeを拒否します。通常の単一Fast Taskは既存の直列入口を使います。

出力分離は、今回未選択・完了済みのworkerも含む全Root Projectへ照合します。出力先の既存物理ancestorと未作成部分を束縛し、準備barrier直前にも再確認します。原Projectへの直列統合もこの検査を使います。`parallel_execution`とWorkspace観測の形式は2.0で、出力束縛を確認できない旧並列履歴は照合が必要です。従来の固定DAG・P2形式の読取は維持します。

各workerは既存`execute`で自分の子Runだけを保存します。親が全workerの準備を検証してから解放し、全workerの停止後に結果を受理します。子Run・Task・Attempt・実行Plan・Task定義・入力revisionをimmutableな`dispatching → settled → accepted`履歴へ結び付け、親だけがTaskStateとPlanを更新します。取消・期限・停止未確認・結果欠落・孤立記録は照合が必要で、自動再送しません。Plan更新は停止barrierの後だけです。`observed_worker_overlap_ns`は準備barrier解放後の観測区間の重複で、モデルやUnityそのものの並列成功を単独では証明しません。

承認済みP4 patch Planを持つ2 workerが検証済みになったら、`create_integration_plan(run_id=...)`で差分2件の正確な統合案を作ります。元のRootで許可した原Projectの同一base、非重複target、子のContext・patch・Evidence・確定receiptを照合します。原Projectはまだ変更しません。表示された案を明示承認する`approve_integration(integration_plan_id=...)`は既存Approval StoreへPlan digest・base・Scope・期限・取消epochを束縛します。

`integrate_workspace_results(run_id=..., integration_plan_id=..., approval_ref=...)`はその承認を各patch直前に再検証し、1回のPlan更新で原Projectの直列patch Task 2件と最終検証Taskを追加します。各patchは既存ToolBroker／File Providerを使い、モデルを再実行しません。importしたPlanはモデル提案元の子Contextと親実行Contextを別々に保持します。最後の原Project revisionでstatic review・新しいCompile観測・両対象のEditMode Testを取り直し、この最終検証TaskだけをRoot Gateへ採用します。子や途中TaskのPASSは最終Gateの代わりになりません。

実環境の段階実行は`python tools/parallel_csharp_e2e.py --help`と同名の`.schema.json`を参照してください。`prepare → propose → workers → integrate`の順で、新規所有Fixtureだけを使います。`workers`は確認した2件の`approved_plan_ids`、`integrate`は確認した`approved_integration_plan_id`を必要とします。モデル提案段階は現在直列で、worker適用段階だけを並列化します。Unity 6000.3.15f1／Test Framework 1.3.9／Codex接続が必要です。実行不能・0件Test・古いXMLを成功にしません。

## 実行計測と比較

Operationsの`operations/metric.jsonl`には`adaptive.*`の固定数値を追記します。準備、Context構築、調整、lease取得、Provider／Gate、モデル、統合を単調時計で区別し、Context選択byte・推定tokens、Evidenceの実読取／再検証、event chain検証、実際に新規保存したsnapshot byte、Plan提案／拒否数を記録します。workerには親Run・Task・Attempt・Plan digestの出所を付けます。時間は各phaseの包含時間で、入れ子phaseを合算して総時間にしません。再開後に実際に行った読取は新しい計測になり、以前の計測を再作成しません。

通常の計測保存失敗で確定処理を再送しません。承認・適用・Evidence・制御履歴の保存失敗は従来どおり実行を停止します。適用履歴readerは同じ読取呼出し内で検証済み境界を共有し、次の呼出しでは再検証します。プロセスをまたぐ検証cacheは持ちません。

Codexの構造化`turn.completed.usage`から取得できる実tokensは、出所・単位・設定model・reasoning effort・観測turn数とともに保存します。cache tokensはinputの内数です。未取得usageと未観測の実model revisionはnullで、推定tokensと合算しません。Source全文やPrompt全文は追加保存しません。

`python tools/adaptive_comparison.py --help`と同名の`.schema.json`は、測定前の`freeze`、固定commandによる`collect`、全記録の`evaluate`を定義します。Fast／動的更新／並列の各シナリオで、同一の正式adapterへvariantだけを渡します。commandは現在のPython実行パスと`tools/adaptive_scenario.py --conditions {conditions} --scenario シナリオID --variant {variant} --workspace {workspace} --report {report}`の引数配列に限定します。任意の外部commandによる品質自己申告を採用しません。

Aは途中更新なし、Bは適応有効・直列、CはBに並列だけを追加し、Workspace作成から最終Gateまでを総時間へ含めます。adapterはFastの単一inspection、初回Evidence後の許可Project追加調査、実モデルとUnityを使う2件C#修正を実行します。並列シナリオには固定条件の`authorize_owned_fixture_patches: true`を明示し、専用Fixtureの既知の算術return修正2件とそのunionだけを承認します。モデルの任意差分は承認しません。

条件digest・Source SHA・model／設定・Unity／Package／OS／Hardware・固定品質Gateを固定し、観測したHost情報も保存します。3 warmup後の30組をABC／CBA交替で記録します。各sample前後・収集終了・評価時のclean SHAを照合し、変更した測定は無効です。記録は内容hashを含む名前で保存し、評価時も今回のWorkspace・Run・Root・必要Gate・モデル提案元・Native Evidence・並列時間を再検証します。中断後は自動再送せず、欠測を0にしません。

判定はFast p95の5%以内、並列総時間中央値C／Bが0.85以下、p95(C)がp95(B)以下、対応する30比の中央値bootstrap 95%区間上限が1未満を必要とします。全失敗・unavailableを分母に残し、成功自己申告だけを採用せずPersistenceの品質Evidenceを再検証します。条件を満たしても、実環境と安全性の独立確認は別途必要です。既存Frozen Baselineは変更せず、並列を既定化しません。

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
- Contextの `estimated_tokens` は推定量です。この旧Baseline集計は新しいpatch Planの実usageを合算せず、`model_usage.status: not_observed`、`total_tokens: null` を維持します。patch Planの出所付きusageと区別し、欠測を0へ変換しません。

出力は `eval/regression/adaptive-baseline.schema.yaml` で検証します。Persistence内への出力と既存ファイルの上書きを拒否し、既存Frozen Baseline／Comparatorは変更しません。fixtureの実行時間をProduction latencyやUnity性能改善として報告しません。

## 排他・権限と未実装範囲

小さいTaskでもPolicy／Approval／Project binding／Scope／Guard／必須Evidenceを維持します。戦略提案からGateを省略できません。

Control PlaneのRun lockは同一Host／userの物理Projectを排他し、Evidence保存まで保持します。Runtimeの `resource_lease.py` はEditor利用CapabilityとMutationのProvider実行中を保護します。取得順はProject Run lock → 必要なHost資源claim → Provider単位Editor leaseです。親Coordinatorは原ProjectのRun lockを保持してworkerを待ちません。期限切れによる自動奪取や別ProviderへのFallbackで競合を回避しません。

これらはUnityAgent経由の協調処理の排他です。手動Editor操作、Unity自身のProject Lockとの統合、Queue、Device lease、汎用変更Agentは未実装です。固定DAGの途中戦略は上記opt-inのdispatch前監査、動的Planと別Workspaceの実行はそれぞれ明示した入口に限定します。外部Hubの履歴や互換Source Lockは変更しません。

## 検証範囲

Hostのunit test・fixture・Schema・validator・wheel resource検証と、実Unity／実モデルの検証は分けます。今回のfixture成功は実Baseline取得や性能改善を意味しません。実Unity Editor／Player／実機／実モデルの利用条件がない場合、検証は `unavailable`、実Baselineは `not_observed` と報告します。

現在の挙動の正本はコード・Schema・テストです。
