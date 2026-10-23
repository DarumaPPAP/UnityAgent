# Artist Command Adapterと厳密な結果変換の実装計画

目的：既存Unity CLI Provider配下へ型付きArtist Adapterを追加し、Sceneを変更しない経路と拒否境界を検証する。

仕様：利用者が確定した「Artist Host CLI廃止・Unity CLI統合」と[既存段階計画](2026-10-22-artist-cli-cutover.md)。本計画の実行方法は同じセッションでの順次実装と独立レビューとする。

## 制約と判断

- Control PlaneだけをAuthorityとし、Registry、Resolver、Catalog、5/5要求、既存Unity CLIの4/4宣言を変更しない。
- Adapterは現在のProduction経路へ接続しない。既存Host、Provider、Installer、Setup、配布物を維持する。
- ApplyとCinematic Applyは承認Tokenの有無にかかわらずTransport前に拒否する。認証されたEditor→既存Approval Authorityの通信と直接Pipeline拒否の実証がないためである。
- CaptureとEvaluate／Refineの実行も保留する。Captureの画像Hashを含む検証契約、認証されたHuman Decision／Context Receiptの境界が未完了である。
- Receiptは要求から生成しない。現在Editorが受信しないContextを受信済みと申告しない。必須Receiptが欠けた結果は失敗とする。
- Read-onlyはScene／Asset変更なしの意味で使う。Planは既存EditorのLibrary内Session状態を更新するため、純粋なファイル読取ではない。

## Task 1：入力とTransport拒否

- [x] `tests/runtime/test_artist_command_adapter.py`へ9コマンド／Cinematic操作の型付き入力、操作別引数、任意argv／Host専用オプション拒否、Apply拒否を追加し、未実装で失敗することを確認する。
- [x] `src/unityagent/runtime/tooling/providers/unity_cli/artist_command_adapter.py`に不変`ArtistCommand`と`build_artist_pipeline_command()`を実装する。既存`build_pipeline_command()`を再利用し、shellへ渡さない。
- [x] 同じテストを再実行する。

## Task 2：結果の厳密な変換

- [x] 外側成功／内側失敗、不正JSON、不明Status、異なるCommand／Project／Revision／Plan、欠落Evidence、偽Receipt、Capture証拠不足の拒否テストを先に追加する。
- [x] 同ディレクトリの`artist_result_mapper.py`で既存JSON処理を再利用し、Editorの既知Schemaと操作別証拠を検査する。Plan／RefineからMutation Evidenceを作らない。Captureや評価をVisual受入へ昇格しない。
- [x] Source由来Fixtureとの比較と拒否テストを再実行する。

## Task 3：既存Providerへの非公開接続と検証

- [x] 既存`UnityCliProvider`へ`run_artist_read_only()`を追加するテストを先に書く。Project／Policy／Read-only Scope／Package／Pipeline／Catalog／runtime_only／取消とTransport拒否を検証する。
- [x] 既存DiscoveryとDispatcherを使って実装する。広告CapabilityやEntry／ToolBrokerの経路は追加しない。
- [x] 対象テスト76件、Packaging 31件、全Static Validatorと全体検証を実行し、Windowsの阻害を分離する。独立レビュー指摘を修正して再検証する。全体検証の確定結果は変更申請のCIを参照する。
- [x] 実装状態と未検証Gateを[検証記録](../../architecture/reviews/artist-command-adapter-2026-10-23.md)に残す。

## 検証台帳

開始Commit：`5cb98eee6b3cd48d1225746027c419410c38304d`。新規Clone内の専用作業Branchで変更する。Baseline関連31テストは統合前の同一内容HEADで成功し、統合後の現在状態は追加変更後に再検証する。

実Unity CLI `1.0.0-beta.14`は最新で、別Project「軽量化テスト」のUnity `6000.3.12f1`／URP `17.3.0`／Pipeline `0.8.0-exp.1`を観測した。明示Project指定のArtist検索は0件だった。対象RevisionのArtist検証Fixtureではなく、ユーザーのProjectを代用しない。実Editor E2Eと認証境界は`BLOCKED_NOT_RUN`とする。

Ruling：参照会話の本文は取得APIから参照記号だけが返った。現在の明示要求、統合済み段階計画、既存正本を根拠とし、未取得の詳細を推測せず、接続・撤去Gateを保留する。

Ruling：`domain.workflow`の正本Policyは`editor_mutation`および`domain_result, mutation_evidence`を必須にする。Read-only成功をこのCapabilityの成功へ変換しない。非接続の検証入口は`scene.inspect`の観測だけを受け付け、Inspect／History／Cinematic Inspectに限定する。既存`run_scene_inspect()`のAllowlistは変更しない。Plan／Previewは構築と変換を実装するが、現契約ではdispatchしない。

検証：新規21テストを含む対象76テスト成功。Packaging 31テスト成功。全32 Static Validatorのうち31本とYAML／Graph検査成功。LayoutはWindowsのcase-insensitive判定で失敗。全体Resource再生成はWindows ACL、既存Receiptテストは長いパスで阻害。ローカル全体をPASSにせず、同一CommitのCIで全体を確認する。独立レビューの各指摘はRED→GREENで修正した。
