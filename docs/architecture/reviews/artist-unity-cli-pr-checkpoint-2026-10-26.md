# Artist Unity CLI統合のPR時点の完了範囲と残作業

## 判定

全9コマンドのUnity CLI統合、旧Provider／独立HostのProduction経路撤去、承認境界・Scope・失敗時Undo・SDK互換修正を実装した。確認済み部分をレビュー可能なDraft PRにまとめ、移行全体のDoDは未成立として扱う。Merge／Release／Tagは行わない。

最新の確認根拠は[PR時点のEvidence索引](../../../tests/unity/evidence/artist/unity-cli-pr-checkpoint/index.json)。以前のtreeに対するPASSは[履歴の検証記録](artist-unity-cli-integration-progress-2026-10-25.md)へ残し、現在のコードへ無条件に流用しない。各テストは変更を含むworking treeで実行し、実際のソースHash／入力Hashを保存している。テスト開始時のHEADが基準Commitでも、cleanな基準Commitを実行したという意味ではない。

## 実装完了範囲

- Entry → Control Plane → Policy／Context → Broker → typed Adapter → Unity CLI → Editor → Mapper → Persistenceによる全9コマンドの経路。
- 旧Artist Providerと独立Hostのソース・選出・Installer・Setup・Release／CIの実行／配布経路の撤去。旧IDは履歴Snapshot／Receiptの読取互換と拒否テストに限定。
- Project／Run／受領Context／Scope／Revision／Exact Diff／期限／取消／単回消費を束縛する承認。直接Pipeline Mutationも実行直前に認可する。
- Camera／Lightの同名候補拒否、削除再生成を検出する実体Revision、LookDev検証失敗時のUndo、Scope外Sceneをdirtyにしない処理。
- 6000.6以降の `GetEntityId()` と旧版APIの条件コンパイル。Cinematic Revisionは実体IDとraw JSONを保持し、旧Planを新実体へ移送しない。
- `UNITY_ARTIST_TEST_FAULTS` 指定時だけの非公開例外注入点。通常assemblyからは除去し、認可・Undo登録・適用成功より前には実行しない。
- 全8 Cinematic kindと両shot更新の計10ケースを扱うControl Plane E2E runner。
- 固定マトリクスのScene／meta同梱、実SDK同梱SRPのVersion／stream／meta完全性確認、厳密な解決後Version照合。

## 確認済みの検証

| Gate | 結果 | 範囲 |
|---|---|---|
| 最終LTSの全9コマンド | PASS | 6000.3.12f1、Built-in。CP → CLI → Editor → durable Evidence、Host不在、再利用拒否、実行前後ソースHash一致 |
| 例外注入 | PASS | 適用済みLightを確認後に例外、Undo、失敗応答、成功Evidence不在、再認証拒否 |
| LTS Editor回帰 | PASS | 35件、失敗0・skip0。通常assemblyの注入hook不存在を含む |
| 固定マトリクス | PASS | 7 Fixture。6000.3 minimal 1件／P9 URP 1件、6000.6 minimal 1件／full 35件／Built-in・URP・HDRP smoke各3件。実GPU readbackとPackage lock照合を含む |
| Artist Python回帰 | PASS・一部skip | 104件、103件成功・1件skip |
| CP失敗後の単回消費 | PASS | 実Approval Storeは認可後のProvider失敗でも消費記録を維持し、再利用を拒否。関連9件成功 |
| 独立レビュー | 機能上の阻害所見なし | Critical／Important 0件。Mirror末尾空行のMinorは正本同期で修正 |
| 全Runtime | FAIL_BASELINE_REPRODUCED | UTF-8条件で現在720件中failure 2・error 11・skip 6。13問題は開始Commitの648件でも再現、current-only 0。追加CP単回消費テストは別途成功 |
| 末尾空行 | PASS | 正本とMirrorを同期し、staged差分の `git diff --check` を確認 |

6000.3.12f1／6000.6.0f1は短い専用パスへ公式CLIで追加導入した。長い配置では260文字以上のmetaが展開されず、同一installerの短い配置で復旧した。SDKへmetaを自作・補完していない。Core Packageは公式Editor同梱版を使い、Registryに存在しない17.xのURLやVersionを推測しない。

## 残作業

1. **Cinematic最終全10ケース：FAIL。** 互換修正前の先行10ケースは成功したが、最終再実行はsignal Apply後のInspectで `Artist Pipeline discovery is unavailable` となった。最終全体成功には数えず、Discoveryの再現調査と全10ケースの再実行が必要。
2. **最終LTSのURP／HDRP全9コマンド・Volume／Fog実Mutation：BLOCKED_NOT_RUN。** 過去treeの成功とは分離して再実行する。
3. **最終Development配布物のRevision／内容照合・分離実行：BLOCKED_NOT_RUN。** wheel生成・189ファイルMirror同期は実装済みだが、PR時点の最終内容に対するwheel／両UPMの同一Revision確認を完了させる。
4. **GitHub CI：not_observed。** PR起票後の実結果を確認する。既存Runtime失敗とWindows symlink権限で実行できないテストはPASS扱いにしない。
5. **Human visual acceptance・性能・Player／実機Build：not_observed。** EditorのCaptureやGPU readback成功と、人による見た目の承認を混同しない。

以前の専用FixtureのCaptureキャッシュはLibrary再生成時に消去したため、旧画像実体を再検証できない。Repository内の歴史的Evidenceは保持した。今回の最終LTS CaptureはLibrary外のZIPにも退避し、抽出内容のSHA-256一致を確認している。

## Git運用

作業Branchは `feature/artist-unity-cli-integration`、baseは `main`。PRは実装済み部分のレビュー単位であり、完全統合完了やMerge承認を意味しない。残Gateが成立するまではDraftとする。
