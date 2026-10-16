# Production E2E 実行報告（2026年10月16日）

**全体Goal: 未完了 / BLOCKED。** Host実装・回帰・配布検証は進めたが、必須のProduction E2Eを観測していない。実環境不足に加え、ProductionのUnity Import/QA/適用後Rollbackへの連結にも未完成部分がある。Phase 0の文書やFixture成功を全体完了の根拠にしない。

比較基準のCommitは `4747fd3f82e5a9c0be191d606f7827a16c8eef90`。作業当時のmainと既存CIを確認し、SubAgent配布統合および動画証拠取得機能を重複実装していない。元の `/workspace/UnityAgent` に残っていた未コミット変更は維持し、隔離した作業領域と短命ブランチを使用した。段階ごとの実装Revisionと検証結果は以下に記録する。

## 段階別の実装と判定

|段階|実装・検証内容|実装Revision|残る必須の検証|
|---|---|---|---|
|0|承認済みDecision正本、Baseline/Definition Revision、Gap Matrix、Architecture、計画、Regression Matrixを保存|`d95b4a2`|Phase 0成果物は完成。全体E2E成功とは別|
|1|既存DAG計画をControl Planeの実行へ接続。固定Task Acceptance、永続Evidence、Revision照合、State-only Checkpoint、再開拒否、限定Staging/Hash条件付きRollback。既存Semantic Loop/Budgetで事前固定修正候補を有限実行し、同じ失敗・未観測・権限拒否で停止|`84c672e`、修正候補の接続は `661512c`|Hostで検証済み。並列実行/速度向上は未計測。適用後Editor副作用とRollback統合、実Editor手動競合は未検証|
|2|QAへ正本ID移行、旧ID明示Alias、Performance分析維持、決定的Acceptance補助。Blender MCP stdio/Session/Job/固定岩Template/Broker/承認/Evidence接続。Template digest拘束、Timeout再送禁止、FBX検査、Optional Doctor/手動Setup Plan|`0790a8d`|Host/Fixture経路は検証済み。実MCP接続、Addon/Protocol実互換、汎用QA reasoning経路、Productionの制作→Unity Handoffは未完了|
|3|独立G1 Fixture: Unity `6000.3.12f1` / URP `17.3.0`。Editor APIによるImport/Prefab/Scene/Material/再Import/GUID/参照/Render Capture/Undo検証を用意。UPM検証Bundleに内包。Windows Self-hosted Workflowと誤PASS拒否Collector追加|`067fdb3`|**実Editor CompileからすべてBLOCKED_NOT_RUN**。Fixture C#も未Compile。FixtureはProduction RuntimeのImport実装を代替しない|
|4|Optional `editor.hot_reload` Adapter。承認Source/Project/Runner Hashを固定、Play/接続確認、部分/Skipped/Failed/fallback拒否。通常Compile/Play動作/QAを未観測として分離。同一Task/環境のペア比較器とmedian/p95/完了率/Retry/Fallback/Regression/Token集計|`661512c`|実Loop適用・通常Compileとの比較・G2/G3は **BLOCKED_NOT_RUN**。Hot Reload常時利用は有効化していない|

完全なSHA、Definition Fingerprint、実行結果は [execution-results.json](execution-results.json)、変更対象は [changed-files.tsv](changed-files.tsv)。実装APIと制限は [Runtime説明](../../architecture/production-e2e-runtime.md)。

## 実行した検証と保存済みの証拠

- `PYTHONPATH=src python tools/validate_all.py`: **725実行、724成功、1 skip**（13 unittest suite）と標準のContract/Architecture/Policy/Golden/Layout検証が通過。[原ログ](evidence/host-validation.log)。
- 作業コピー外のvenvへwheelをインストールし、CLI起動・Context・Profile・全258 Resource Hash・Doctorを検証。[結果](evidence/installed-wheel.json)。CIで見つかった共有Alias Moduleのwheel内包漏れを修正済み。
- Blender **4.3.2** を `--background --factory-startup` で実行し、固定TemplateからFBX Export後、別Processで再Importした。**42頂点 / 80三角形 / UV 1層 / Scale 1 / 外部Texture依存なし**。FBX SHA-256は `b79d0237a8ecd453447db7a2f12d09992e1d213aeb71137d99789ce6f502038c`。[FBX](evidence/blender-template/Rock.fbx)、[Manifest](evidence/blender-template/artifact.json)、[再Import](evidence/blender-template/fbx-reimport.json)、[Exportログ](evidence/blender-template/export.log)、[Importログ](evidence/blender-template/fbx-reimport.log)。
- 上記Blender実行は **Template/FBX検証**。Production MCP経由の成功ではない。MCPの実Process stdio試験とBroker統合はFixture serverで検証した。
- Optional Doctorは Blender MCP / CLI Loop とも `unavailable`。[結果](evidence/optional-doctor.json)。他のCore Capabilityを無効化しない。
- Hot Reload preflightはレビュー済みの導入済みRunnerがなく `BLOCKED_NOT_RUN`。[結果](evidence/hot-reload-preflight.json)。通常Compileとの実測ペアは **0件**、Latency/median/p95/Tokenは **unmeasured**。[比較結果](evidence/hot-reload-comparison.json)。
- Unity Editor / Player / Target Deviceは実行していない。[独立Gate結果](evidence/acceptance.json)。既存のPlay・Timeline録画機能についても、デコードと実画面品質を未観測。

## 自動検証の記録

初期実装Commitに対する **4本すべてのCanonical ValidationとWindows Project Leaseが成功**。完全なSHAとRunは `execution-results.json#ci`。CIは実Unity E2Eとは別である。

|実装Revision|成功したCI実行|
|---|---|---|
|`84c672e`|[実行記録](https://github.com/DarumaPPAP/UnityAgent/actions/runs/38805286894)|
|`0790a8d`|[実行記録](https://github.com/DarumaPPAP/UnityAgent/actions/runs/38807469893)|
|`067fdb3`|[実行記録](https://github.com/DarumaPPAP/UnityAgent/actions/runs/38807521141)|
|`661512c`|[実行記録](https://github.com/DarumaPPAP/UnityAgent/actions/runs/38807711945)|

初回の配布・検証処理はPython配布物へのファイル内包漏れで失敗し、修正後に成功した。CIにはwheel配布、Artist CLI Compile、既存P9 Fixture/Runner、PowerShell/UPM検証も含まれる。新規G1 Workflowは手動・Self-hostedのみで、ここから未確認RunnerへDispatchしていない。追加のSession Binding強化（`7e02b62`、HostのMCP関連6件と標準検証725件で検証）と報告文書Commitについては、最新CI状態をGitHub Actionsの実行記録で確認する。

## 既知の制限と未解決のリスク

1. **Productionの連続経路は未完成。** `rock apply` はStaging生成まで。FixtureのImport/Prefab/Scene検証を、既存Control Plane/Broker/承認/Context/Lease/Evidence経路で連続実行するEditor Handoffは残っている。CLIの独立操作を実行しただけで複数SubAgent E2E成功としない。
2. **QAは段階的再編。** 旧Performanceの実行能力と決定的Acceptance補助はあるが、テスト計画・再現・修正候補生成・再検証を汎用QA reasoningとして一貫Dispatchする新経路は未完成。現在の意味的修正は開始時に固定した候補のみ。
3. **Rollbackは限定Helperまで。** 他者編集のAsset/metaを上書きしないが、Unity Import後に新しく作られた`.meta`等は照合不一致で止まる。Editor生成物の所有権/Hash/GUIDを署名付きReceiptへ拘束して、安全な適用後Rollbackへ接続する必要がある。CheckpointからAssetを復旧しない。
4. **G1のC# / URP pinは未検証。** Unity Package Registryへの照会はHTTP 403。`17.3.0`の解決とRenderGraph API互換を実Editorで確認し、実UPM解決前にpackages-lockを捏造しない。
5. **Optional SetupのApplyは未自動化。** Blender MCP/Loopの追加Doctorは導入状態を観測する。Install/Updateは明示承認とレビュー済み導入手順が必要で、現状は`manual_required`。Addon versionは`unmeasured`。制作には実Blender Session identityの観測が必要で、MCP Client側のUUIDだけでは実行しない。未対応ServerはUnavailableのままにし、別State Rootでも共有Session排他を維持する。
6. **G2/G3未実行。** 許可された実Project/Player/Device/SDKを観測していない。Editorの結果をPlayer/実機の結果へ流用しない。

## 残る実環境での確認

1. 利用可能なライセンス付きWindows RunnerとUnity **6000.3.12f1**、実Graphicsを接続する。Runner一覧APIは認証権限不足のHTTP 403で、存在/不在を断定できない。
2. レビュー済みBlender MCP Server/AddonとSession、CLI Loop V3 Project Runner/Packageを明示承認のSetup経路で準備する。未承認インストールや外部生成課金はしていない。
3. 上記未接続のProduction Handoff/QA/適用後Rollbackを結線し、G1でCompile→Import→Prefab→Scene→QA→再Export/再Import→故意失敗/競合→Rollbackを観測する。既存の録画機能も、デコードと映像品質まで別の検証項目として確認する。
4. 同じTask/環境で通常CompileとHot Reloadの測定ペアを収集する。改善が実証できるまでOptionalを維持する。G2/G3は別途許可された対象で実行する。

必須の検証項目に未観測のものが残るため、この報告では全体目標を完了扱いしない。
