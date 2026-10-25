# Artist Unity CLI統合の独立再レビュー

2026-10-25、独立Reviewerが変更前後の正本コードを読み取り専用で確認した。対象コードの検証用Git treeは `584a7def1c64df58c4b79a397cbe913ec1e9ce2d`。Commit、Merge、Release、Tagの作成を意味しない。

## 初回所見と対応

| 重要度 | 所見 | 修正と確認 |
|---|---|---|
| Important | 名前と値だけのCamera／Light Revisionでは、同名候補や削除・再生成した別実体へ承認が移る | 名前指定は一意の場合だけ採用。RevisionへGlobalObjectIdとInstance IDを含める。Volumeにも実体IDを追加 |
| Important | LookDev適用後の検証例外で `applied = true` が残り、Undoを通らず成功経路へ進む | catchで `applied = false` を設定し、finallyのUndoへ進める |
| Minor | Fog／Volume変更が全loaded Sceneをdirtyにする | Built-inはactive Scene、URP／HDRPはVolume所属Sceneに限定。全Scene helperを除去 |

実Editorの修正前テストは33件中29件成功・4件失敗。追加したCamera／Lightの同名・差替え拒否4件が失敗した。最初の修正では同名拒否が通った一方、削除・再生成後もGlobalObjectIdが再利用され、差替え2件が失敗した。Instance IDを含めた最終修正で、Scope外Scene dirty防止を加えた34件すべてが成功し、失敗0・スキップ0となった。

Scene reload／Editor restartで実体が変わった場合、旧未消費Planも失効し得る。承認対象を別実体へ自動移送しないための安全側の契約である。

## 再レビュー結果

独立Reviewerの判定は、未解決Critical 0件・Important 0件・Minor 0件。上記3所見の修正を正本コードで確認した。承認経路のProject／Run／受領Context／Scope／Revision／Exact Diff／期限／取消／単回消費、Editorの直接Mutation拒否、旧Provider／HostソースとInstaller／Release経路の撤去について、確認範囲で追加の問題は見つからなかった。

Reviewerは `identity-final-green.xml` の34件成功と、`live-builtin-reviewed/summary.json` の全9コマンド・再利用拒否・Host不在・ソースHash不変を読み直した。テストをReviewer自身が再実行したという意味ではない。

## 検証上の限界

- LookDev適用後の検証処理への例外注入は実Editorで未実行（`not_observed`）。例外経路の修正はコードレビューによる確認。
- この再レビュー時点では、別実行の最終Cinematic Mutation、URP／HDRP、配布物生成の結果をReviewerは確認していない。これらは[統合検証記録](artist-unity-cli-integration-progress-2026-10-25.md)と[Evidence索引](../../../tests/unity/evidence/artist/unity-cli-integration/index.json)の各Gateで判定する。
- 同一OSユーザーによる任意ファイル改竄・任意C#実行を防ぐsandboxの監査ではなく、型付きCLI／Pipeline境界の承認・実行契約を確認した。
