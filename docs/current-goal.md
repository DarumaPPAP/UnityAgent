# Current Goal: Local Reference Navigator

## Goal statement

MyResourceCenterとUnityAgentを、常時稼働する外部検索基盤・自動同期に依存せず、必要時の一度のSource確認で生成したローカルReference Snapshotを中心に運用できる状態にする。

通常の質問はSnapshotから上位3〜5件を選び、不具合相談は一度の候補探索から仮説・確認項目・切り分け順を作成する。その後はUnity Projectの読み取り、Test、Console、Profiler、Visual observationを優先し、Snapshot外の情報や原文確認が必要な場合だけ明示的な再確認を行う。

## Non-goals

- 個人運用での常時稼働外部検索サービス
- 埋め込みAPI、ベクトルDB、常時同期worker
- 参照文を命令として実行すること
- 優先順位を測定済みの原因確率と誤認すること

## Completion

- Local Reference NavigatorがネットワークなしでSnapshotを読み込める
- 通常質問は最大5候補・最大8,000文字に収まる
- 不具合は最大5仮説と読み取り専用の確認手順を返す
- 空結果・古さ・矛盾・原文確認必要時は推測せず再確認を提案する
- 既存UnityAgent全体Validationと新規Navigator testsが通る
