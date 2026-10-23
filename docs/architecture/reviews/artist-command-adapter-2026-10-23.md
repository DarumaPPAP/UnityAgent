# Artist Command Adapterの実装状態と停止境界

## 対象と責務

基準Commitは`5cb98eee6b3cd48d1225746027c419410c38304d`。[移行Baseline](artist-cli-cutover-baseline-2026-10-22.md)から、既存Unity CLI Provider配下に型付きCommand Adapterと厳密なResult Mapperを追加した。[実装計画](../../superpowers/plans/2026-10-23-artist-command-adapter.md)に判断と作業段階を記録する。

`ArtistCommand`は内部9コマンドとCinematic操作を表す不変入力である。Host専用引数、任意argv、動的実行、Project／runtimeの差替えを受け付けない。既存`build_pipeline_command()`、Discovery、Dispatcher、JSON／NDJSON処理を再利用する。別CLI、承認Store、Authority、Entryは追加しない。

## 実行可能性の区別

| 操作 | 型付き構築／変換 | 新経路のdispatch |
|---|---|---|
| Inspect／History／Cinematic Inspect | 実装 | 非接続の`run_artist_read_only()`からのみ検証可能 |
| Plan／Preview／Cinematic Plan・Preview | 実装 | 停止。現行Workflow PolicyのMutation Evidence要件をRead-only結果では満たせない |
| Capture | 型付き入力を実装、成功変換は拒否 | 停止。画像のCamera・Path・Hash照合と必須Receipt境界が未完了 |
| Evaluate／Refine | 型付き入力を実装、成功変換は拒否 | 停止。認証されたHuman Decisionの連携が未完了 |
| Apply／Cinematic Apply | 入力型は保持するがargv構築を拒否 | 停止。Tokenが非空でも実行しない |

非接続入口はProductionのControl Plane／ToolBroker／Resolverから呼ばれず、新Capabilityを広告しない。既存`scene.inspect`の`run_scene_inspect()`とAllowlistは変更しない。検証入口は有効な`scene.inspect`要求、Policy許可、Mutation Scopeなし、現在Project／Editor、Package／互換性、現在Catalogの非Runtimeコマンドを要求する。

正本`tool-capability-policy.yaml`では`domain.workflow`は`editor_mutation`と`domain_result, mutation_evidence`を要求する。Read-only成功をこのWorkflowの完了へ変換しない。RegistryのSafety／Evidence要求5/5と、`unity_cli`の宣言4/4は変更していない。新Providerが5/5を達成したとは主張しない。

## 結果と証拠の検査

外側CLIの終了コード・terminal success・Command・errorsと、内側EditorのSchema／製品／Command／Status／errors／Boolean型／Revision／Supportを別々に検査する。重複JSONキー、非有限数、不明Status、異なるProject、異なるPlan／Revision、保存の実施、予期しないDiff、欠落Evidenceは失敗にする。

Planには非空Plan ID、Exact Diff、Revision、承認が必要であることの申告と操作別Evidenceを要求する。Plan／PreviewからMutation Evidenceを生成しない。観測結果とHuman Visual Acceptanceを混同しない。

ReceiptはEditor結果の`contextReceipt`だけを検査対象とし、外側Host包装や要求値から生成しない。期待するID／Fingerprintが指定された場合、両方を一致照合し、欠落・不一致なら成功させない。現行EditorはこのReceiptを返す契約を実装していないため、現在の応答でSpecialistの必須Receipt Gateを通過できない。テストのReceiptは合成入力であり、実EditorがContextを受信した証拠ではない。

Captureの現行SourceはCameraと画像Pathを返すが、検証済みHashを含む受入契約がない。成功Mapperを推測で作らず、Capture／Human Review依存操作を明示的に拒否する。

## 実Editorの観測と未検証

2026-10-23にUnity CLI `1.0.0-beta.14`と更新確認で同じ最新Versionを観測した。接続Editorは別Project「軽量化テスト」でUnity `6000.3.12f1`、URP `17.3.0`、Pipeline `0.8.0-exp.1`、UnityAgent Package参照は公開済み`v0.0.8-beta`だった。明示Project指定で`artist`を検索した結果は0コマンドだった。ProjectのScene／Asset／設定は変更していない。

この環境を現在SHAのArtist検証Fixtureとして代用しない。認証されたEditor→既存Approval Authorityの問い合わせも未実装であり、偽承認／別Run／別Project／Plan／Exact Diff／Revision／取消／期限／Scope超過／再利用の直接Pipeline拒否は`BLOCKED_NOT_RUN`である。新しいMutation切替、旧Host／Provider／Installer／Setup／配布物の削除は行っていない。

## 検証状態

新Adapterのテストを先に追加して未実装による失敗を確認した。重複キー・非有限数の拒否テストでも旧JSON解釈での失敗を確認した後、Artistでのみ有効にする厳密モードを追加した。既存のJSON処理の既定動作は維持する。

ローカル検証はWindowsのSandbox一時領域・共有Project Leaseの制限と、長いRepositoryパス下の既存Control Plane Receiptテストで`os.replace`の`WinError 3`に遭遇した。ProductionのLease／Persistence処理を回避・変更せず、通常権限での対象検証とCIを区別して記録する。

現在の変更に対する対象76テストとPackaging 31テストは成功した。後者は新規Cloneの自動改行変換による不一致を、未変更ファイルをGit原本と同じバイト列へ戻して解消した。全32 Static Validatorのうち31本、YAML検査、Graph生成整合検査が成功した。残る`validate_layout.py`はWindowsのcase-insensitiveな存在判定で正規の`eval/tools/tests`を禁止名`Eval/Tools/Tests`として検出した。全体`validate_all.py`はResource再生成のWindows ACLにも阻害され、ローカル全体PASSとはしない。最終Commitの全体検証はCIで確認し、変更申請にURLと状態を記録する。

独立レビューでCamera以外のPlan Evidence、Target要素の型、不正Project識別、巨大整数の有限数検査を修正した。各拒否／回帰テストで失敗を再現し、対象76テストで再検証した。改行、Layout、ACL、長いパスへの対処として製品Policyや保護処理を弱めていない。

Unity Compile／実Artist Read-only／Mutation E2E／旧Hostなし／Domain Reload／Undo／P9／Production G1は`BLOCKED_NOT_RUN`。Visual受入・Performance・Player・実機は`not_observed`。静的検証や合成入力の成功をこれらの成功として扱わない。

## 再開条件

実Editorで使える認証済みApproval照会・失効反映・一回性と実行の結合を既存Control Planeに設計し、ContextのEditor受信とCapture証拠を実装・検証する。対象SHAの専用Fixtureで拒否系、Scene差分、非自動保存、Undo、再起動を実証し、5/5根拠と同一レビュー済みSHAの成果物照合が揃ってからResolver／Registryを切り替える。旧Host撤去はその後とする。
