# Production E2Eの実行構造

確定済みの要件は [Production E2Eの決定事項](../decisions/production-e2e/approved-goal.md) に記載する。この文書は実装済みのホスト側処理と制約を説明するものであり、実環境での検証成功を保証するものではない。

## Task実行とQA

`UnityAgentControlPlane.execute_tasks(tasks, run_id=..., definition_fingerprint=..., task_parameters=..., resume=False)` は、既存のDAG計画器が求めた依存順序に従い、Control Planeの `execute` を経由してTaskを実行する。

Taskは `id`、`workspace`、`goal`、`depends_on`、`write_set`、`resource_claims`、`entry_request`、`required_gates` を持つ。`required_gates` は必須の検証項目と証拠の種類を固定する。実行時引数はホストが管理し、Entry側でProviderを直接指定することはできない。

- 再開によって必須の検証項目を削除することはできない。証拠はTaskの実行IDと有効な定義Revisionに一致する必要がある。
- QAの `assess_task` は保存済みの証拠を決定的に評価するだけで、ツール実行権限を持たず、合格条件も緩和しない。
- 既存の性能分析能力は `qa_subagent` に継承し、旧 `performance_subagent` は明示的な入力互換名として扱う。
- 初期の実行制御は直列処理であり、並列実行を想定したBatchであっても同時には実行しない。並列化の速度向上は `unmeasured`。単一Task用のFast Pathは変更していない。

Taskは事前に固定した `repair_candidates` と `semantic_repair_limit` を持てる。意味的修正回数の初期候補は2回だが、無制限の再実行ではない。既存の `RuntimeBudgetLedger` と `decide_semantic_loop` が制限し、すべての候補で必須検証項目を維持する。

同じ失敗の反復、観測不能、Policy/Approvalの拒否、外部変更の結果不明が起きた場合は修正処理を止める。変更を伴うTaskで失敗した場合、次の修正に進む前に副作用の照合が必要である。自動修正は、検証済みの読み取り・分析失敗から開始する。通信などの再試行はBroker内の別予算で管理し、Task履歴に実行・担当引き継ぎ・再試行を残す。

実行チェックポイントは、既存のワークフロー状態から不変のTaskスナップショットを参照する。チェックポイントから戻るのは**実行状態だけ**で、Unity Assetは復旧しない。再開時には定義Revisionとプロジェクト内容を照合し、中断時に `running` だったTaskは外部副作用の確認が終わるまで拒否する。

## 制作物の一時保管と復旧

`StagedAssets` が扱える入力は、FBXと画像の取り込み元に限定される。既存の変更許可範囲評価を使い、Assetと `.meta` の変更前・変更後のデータとハッシュを保存する。

書き込み前には対象ファイル全体の変更前状態を確認する。ディレクトリ外参照、シンボリックリンク、壊れたバックアップ、競合する手動変更は拒否する。`.unity`、`.prefab`、`.mat` を生ファイルのまま直接変更しない。RuntimeはProject Leaseを保持し、信頼済みの承認を再確認する必要がある。

この処理だけでは、Unity Editorによる変更後の完全な復旧にはならない。Editorが新たに生成した `.meta` などで変更後の状態が一致しない場合は停止する。所有者不明のファイルを勝手に消したり、任意のユーザーAssetやGitの履歴を巻き戻したりしない。

取り込みと受領記録の具体的な手順は [Blender制作物のUnity取り込み](../development/production-rock-import-handoff.md) を参照する。

## Blender MCPとの接続

```sh
unity-agent rock plan --project-path PROJECT --state-root EXTERNAL_STATE --job-id rock-g1
unity-agent rock approve --project-path PROJECT --state-root EXTERNAL_STATE --plan-id PLAN
unity-agent rock apply --project-path PROJECT --state-root EXTERNAL_STATE --plan-id PLAN --approval-ref APPROVAL --mcp-executable INSTALLED_SERVER
```

計画には、レビュー対象の固定Python処理全体を提示する。そのダイジェスト、プロジェクトRevision、定義Revision、承認の期限・取消状態、変更対象範囲を、MCPツールを呼び出す前に確認する。任意のPythonコードを呼び出し元から受け取らない。

JSON-RPC初期化とツール一覧取得のあと、実際のBlenderインスタンスの識別情報を観測する。`get_scene_info.structuredContent.blender_session_identity` のような観測値が必要で、MCPクライアントやプロセスのUUIDだけではBlender本体の識別にはならない。識別できないサーバーでの変更は利用不可とする。状態保存先が異なる場合でも、ホストで共有するUnityAgentのキャッシュ領域を通じてセッションの排他を守る。

固定処理では、指定されたメッシュ・UV・マテリアルを作り、FBXと制作物の情報ファイルを出力する。別の外部生成サービスは呼び出さない。

Blender作業記録は既存の永続化層と排他処理で管理する。生成中はUnity Project Leaseを長時間保持しない。結果が不明な投入済み作業を自動再送せず、セッション変更時は整合性を確認する。

制作物の検証では、FBXの有無とサイズ、ハッシュ、正の頂点・面情報、スケール、UV、外部Texture依存を確認する。通信手順とサーバーの識別情報を保存し、アドオンのバージョンは実際に取得できるまで `unmeasured` とする。

`rock apply` が完了しても、それは制作物の生成完了のみである。`verified: false` と `unity_import: BLOCKED_NOT_RUN` を維持し、G1のEditor検証は別の段階で実行する。現在の一連の実行経路の未接続部分を、完成済みと表現しない。

追加ツールの状態確認は `--product blender_mcp --product unity_cli_loop` に対応する。追加ツールがない場合でも中核の機能は停止しない。実行ファイルが見つかっただけでは導入状態しか分からず、通信手順・紐付け・Revision・実行可能性を実観測するまでは未確認とする。導入計画は `manual_required` で、ここではパッケージ導入・更新を自動実行しない。

## Unity CLI Loopによる差分適用

任意機能の `editor.hot_reload` は、既存のUnity CLI/Pipelineを補助する。操作手順の `hot-reload plan/approve/apply` は、ソースの正確なハッシュ、プロジェクトRevision、レビュー済みローカル `uloop-project-runner` の実行ファイルハッシュを固定する。

全体を管理するコマンドはRunnerのダウンロードや更新を行う可能性があるため、固定済みの導入済み実行ファイルを直接呼び出す。

適用時にはEditorの接続状態とPlay状態を確認し、`hot-reload --files ... --compile-on-skip off --project-path ...` を呼ぶ。部分成功、スキップ、失敗、空結果、通常Compileへの自動切替は拒否する。ソースのハッシュは呼び出し前後で照合する。

差分適用が成功しても、通常Compile、Play中の動作、QAの検証を達成したことにはならない。必要な検証が未観測ならCLIは非ゼロで終了する。ランタイム差分の削除は、Assetやソースの復旧を意味しない。

参照した上流仕様は、検証対象Revisionを固定した以下の資料。

- [V3の差分適用API](https://github.com/hatayama/unity-cli-loop/blob/4b6e8a858bb0608484000b2eb2bf92d8266e020e/.agents/skills/uloop-hot-reload/SKILL.md)
- [適用結果の定義](https://github.com/hatayama/unity-cli-loop/blob/4b6e8a858bb0608484000b2eb2bf92d8266e020e/Packages/src/Editor/FirstPartyTools/HotReload/HotReloadApplyOutcome.cs)
- [プロジェクト固有Runnerの固定方法](https://github.com/hatayama/unity-cli-loop/blob/4b6e8a858bb0608484000b2eb2bf92d8266e020e/docs/project-runner-pin.md)

実際に導入された実行ファイルとの応答契約は、実接続での確認が必要である。ここでは外部の実行ファイル・Unityパッケージを導入していない。

## 比較評価と合否

`eval/production_e2e/compare_iterations.py` は、Taskと環境条件を揃えた比較試行を検証し、中央値、最近接順位による95パーセンタイル、完了率、再試行、通常処理への切替、トークン数、実行時の副作用、回帰率を集計する。

トークン量の測定値がない場合は `unmeasured` とする。比較対象の組が5件未満の場合は、改善案の推奨を確定しない。呼び出し元が提出したサンプルも、保存済みの証拠を別途確認する。差分適用を勝手に常時有効にはしない。

`tests/unity/verify/collect_evidence.py` は、本番実行、Blender MCP、Compile、Editor取り込み、描画、目視、復旧、排他競合、動画のデコード、差分適用比較、G2、G3を分離して集める。

未観測の検証項目は `BLOCKED_NOT_RUN` とする。検証用Fixtureだけの成功で、本番実行を成功扱いしない。
