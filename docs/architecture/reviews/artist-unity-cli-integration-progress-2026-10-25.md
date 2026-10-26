# Artist Unity CLI統合の検証記録

> この文書は2026-10-25の検証treeに対する履歴です。現在の完了範囲と残Gateは[2026-10-26のPR時点記録](artist-unity-cli-pr-checkpoint-2026-10-26.md)を参照してください。以降の変更後に、以下のPASSをそのまま流用しません。

## 判定

コード統合と旧Provider／HostのProduction経路撤去を実装し、最終コードでUnity 6000.3.2f1のBuilt-in／URP／HDRP全9コマンド、Cinematic／Volume／Fog Mutation、Editor 34件、独立再レビュー、Development配布物を検証しました。Repository固定Editorマトリクスは必要Version未導入で `BLOCKED_NOT_RUN`、全Runtimeには基準Commitでも再現する失敗があるため、移行全体のDoDは保留します。Merge／Release／Tagは実行していません。

## 現在の実装

`artist_subagent` の実行Backendを `unity_cli` へ統合しました。旧Providerパッケージと独立Hostソースを撤去し、Installer／Setup製品は任意UPMの `artist_subagent` へ変更しました。Release／CIはHostを生成・配布しません。履歴Snapshot／InstallReceiptの旧IDは読取互換、Provider登録における旧IDは拒否検査として保持します。

既存Adapter／Result Mapper／Broker／Context Assembly／Approval Store／Evidence Storeを使用します。変更実行には実Editor Plan、Revision、Exact Diff、実対象Scene／Assetパス、Project／Run／受領Context、承認期限／取消状態を束縛し、Editor側で実行直前に認証します。永続Storeの単回消費で再利用を拒否します。ファイルScopeは物理的包含とjunction差替も再検証します。

Camera／Lightの名前指定は一意の場合だけ採用します。削除・再生成でGlobalObjectIdが再利用される実例を検出したため、Camera／Light／VolumeのRevisionにInstance IDも含めました。Scene reload／Editor restartで実体が変われば未消費Planも失効し得ます。LookDev検証例外はUndoへ戻し、Sceneのdirty設定は実対象だけに限定します。[独立再レビュー記録](artist-unity-cli-final-code-review-2026-10-25.md)で重要所見2件・軽微所見1件の解消を確認しています。

## 実行した検証

| Gate | 結果 | 範囲 |
|---|---|---|
| 全9コマンド | PASS | Unity 6000.3.2f1、Built-in／URP 17.3.0／HDRP 17.3.0。公式CLI 1.0.0-beta.14、Control Plane → Broker → Editor → durable Evidence。各環境でHost不在・再利用拒否・ソースHash不変 |
| Cinematic Mutation | PASS | 同環境。Activation TrackのPlan／Preview／承認／Apply、Exact Diff／実パス、再利用拒否、保存Scene／Timeline Hash不変 |
| URP／HDRP Mutation | PASS | URP ColorAdjustmentsの生成／active／override／値、HDRP Fogのactive／override／meanFreePath。承認Diff一致・実対象Scene／Profile・保存Hash不変 |
| Editor Test | PASS | 最終34件、失敗0、スキップ0。全Cinematic kindの差分、実Camera参照、Scope、Context、直接Apply拒否、同名／差替え拒否、Scope外Sceneのdirty防止 |
| 関連Python回帰 | PASS・一部skip | 185件実行、183件成功・2件スキップ。別途Artist 98件実行、97件成功・1件スキップ。対象PythonソースHashが以前の185件実行時と同一であることを照合。数値は合算しない |
| C#／Python承認Interop | PASS | 実C#クライアント、署名／nonce／session／予約、Python Storeによる永続再利用拒否 |
| Editor／Control Plane再起動 | PASS | 再起動前に消費済みの承認を、再起動後の永続Storeから拒否 |
| UPM内包ソース | PASS | Git blobと185ファイルの内容・サイズ・Hash一致。内包／Setup配布検証9件成功 |
| Development配布物 | PASS | tree `584a7def1c64df58c4b79a397cbe913ec1e9ce2d` からwheelと2つのUPMを生成。231 Pythonモジュール・266リソースと正本内容一致。旧Hostなし |
| 分離wheel実Editor実行 | PASS | 最終wheelを分離展開し、import元とリソースRootを確認。URP／HDRP全9コマンド・Mutation、追加Inspectのdurable Evidence。旧Provider import不可 |
| 全Runtime回帰 | FAIL・既存再現 | 現在715件中、失敗9・エラー18・スキップ6。開始Commitでも同じ27問題が再現。今回だけの新規失敗は0 |
| Authority／五層／製品Identity静的検査 | PASS | Repository authority 0 errors、five-layer PASS、Artist identity PASS |
| 最終独立コードレビュー | PASS | 再レビューで未解決Critical／Important／Minorは各0件。Reviewer自身のテスト再実行ではなく、修正コードと実行済みログの独立確認 |

数値は各スイートの結果であり、重複するテストを合算しません。Capture Reviewはsynthetic `needs_refine`で、Human visual acceptanceは `not_observed` です。性能は計測していません。

## 残るGate

- [Repository固定マトリクス](../../../tests/unity/matrix.yaml)：`BLOCKED_NOT_RUN`。指定Version 6000.3.12f1／6000.6.0f1は未導入です。6000.3.2f1での3 Pipeline成功を、この固定マトリクスの成功へ読み替えません。
- LookDev適用後の検証処理への例外注入：`not_observed`。catchで失敗へ戻しUndoへ進むことは独立コードレビューで確認しましたが、例外注入を伴う実Editor検証は未実行です。
- Cinematic全kindはEditor回帰で検証し、Control Planeからの最終Mutation E2EはActivation Trackを使用しました。全kindそれぞれのControl Plane E2Eを実行したとは扱いません。
- 全Runtimeスイート：上記の既存失敗があるためPASSとは扱いません。比較対象は開始SHA `6288cd106614913e0466a71ed539fe11ea5c0411` です。
- Release／Tag／Merge、公開Release成果物のインストール：未実行。利用者の別指示に従います。Development wheelは分離展開して実行済み、UPM tarballは同一treeの内容一致を検証済みです。

証拠は [当時のEvidence索引](https://github.com/DarumaPPAP/UnityAgent/blob/806783ced882494a238de770eeda82502f53af6a/tests/unity/evidence/artist/unity-cli-integration/index.json) に保存しています。履歴EvidenceのPASSを現在の成功として転用していません。Development配布物の記録にあるGit treeは検証対象内容を示し、mainへのMergeや公開Releaseを示しません。
