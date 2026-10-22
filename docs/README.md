# UnityAgent ドキュメント案内

このページは、現在の仕様を調べるための入口です。**現在有効な設計・実装契約**と、作成当時の状況を記録した**履歴資料**を区別します。

## 利用を始める

| 目的 | 資料 |
|---|---|
| 公開Releaseを導入する・Developmentを固定する | [導入とRevision](getting-started/installation.md) |
| Projectを診断し、Setup Planを読む | [最初のTask](getting-started/first-task.md) |
| 専門担当と利用条件を調べる | [SubAgentガイド](guides/subagents.md) |
| 実装と検証状態・対応環境を調べる | [機能の状態表](references/capability-status.md) |
| 仕組みを短時間で知る | [3分で分かる全体構造](architecture/three-minute-architecture.md) |

公開Releaseの説明とDevelopmentの機能・構文を区別します。説明上の計画、コードの実装、対象Revision・環境・Gateに一致する検証成功はそれぞれ別です。Setupの詳細は [既存のEditorガイド](development/unityagent-setup-unity-verification.md)、承認とScopeは [ローカル開発ガイド](local-project-development.md) を再利用します。

## 現在の構造と機能

| 内容 | 資料 |
|---|---|
| 製品の責務と実行経路 | [全体構造](architecture/architecture.md) |
| ツール実行と権限境界 | [実行処理の構造](architecture/production-tool-runtime.md) |
| 初期戦略・直列DAG・観測とBaseline | [適応実行方針](architecture/adaptive-subagent-execution.md) |
| 専門SubAgentの情報構築と推論の引き継ぎ | [専門SubAgentの情報構築](architecture/specialist-context-assembly.md) |
| ArtistSubAgentの責務 | [ArtistSubAgentの境界](architecture/artist-subagent-boundary.md) |
| 一連の実行機能と制約 | [一連の実行機能](architecture/full-e2e-capability.md) |
| カタログの取り込み制限 | [カタログ取り込みの検証](architecture/catalog-import-gate.md) |
| ローカルの参照資料検索 | [ローカル参照検索](architecture/local-reference-navigator.md) |
| 構造の短い説明 | [3分で分かる全体構造](architecture/three-minute-architecture.md) |
| Production E2Eの実装と未検証範囲 | [一連の実行処理](architecture/production-e2e-runtime.md) |

## 開発・検証環境

Contributorは [Branch運用](development/branch-policy.md)、[PR記述規約](development/pull-request-standards.md)、[Release資格確認](development/p9-release-qualification.md) を確認してください。CI Runnerの詳細は [ci/README.md](../ci/README.md) を参照します。

- [ローカルUnityプロジェクトでの開発](local-project-development.md)
- [Unity開発・検証環境仕様](development/unity-test.md)
- [標準Unity Projectの手動検証](../tests/UnityAgentTest/README.md)
- [Unity環境への適応](unity-environment-adaptation.md)
- [情報探索画面](context-explorer.md)
- [Unity CLIの参照資料](references/unity-cli-reference.md)
- [仕様一覧](architecture/specifications/INDEX.md)
- [Blender制作物のUnity取り込み](development/production-rock-import-handoff.md)
- [非公開CIの承認と再開](development/private-production-ci.md)

## 実装上の正本

実際の挙動を決めるのは、説明文書ではなく次の機械可読な定義と実装です。

- `src/unityagent/policy/`
- `src/unityagent/orchestration/`
- `src/unityagent/context/`
- `src/unityagent/runtime/`
- `src/unityagent/persistence/`
- `src/unityagent/operations/`
- `eval/`
- `src/unityagent/contracts/unityagent-layer-contract.yaml`

文書と実装が矛盾する場合は、正本の契約・コード・テストを確認して文書を修正します。[Authority Mapに残る外部Hub宣言と同居実装の不一致](references/capability-status.md#正本の既知の不一致) は既知事項として区別し、この文書整理で契約を書き換えません。

## 履歴資料

次は作成当時の判断と証拠を保管する領域です。現在の挙動をそのまま保証する資料ではありません。

- `migration/`：移行時の構造・実行・比較記録
- `decisions/`：設計判断と決定事項
- `superpowers/`：過去の計画・仕様案
- [Unity環境整備の実装指示](development/unity-setup.md) と `development/plans/`：当時の実装計画。現行の操作ガイドと区別する
- `architecture/reviews/`：時点監査
- 日付を含む `*-audit-YYYY-MM-DD.md`、`*-decision-YYYY-MM-DD.md`

履歴に記載された古いパス・バージョン・対応環境を、現行仕様として読み替えません。

## ドキュメントの執筆規則

1. **説明文・見出し・表・図のラベル・操作手順は日本語で記述する。** 英語の文章を混在させない。コード、API、型・関数・プロパティ名、ファイルパス、コマンド、環境変数、GitHub上の正式名称は正確な表記を維持する。
2. **ドキュメント名・見出し・本文・表の識別にプルリクエスト番号やそのタイトルを使わない。** 開発途中の変更申請番号や依存順序を、永続的な仕様に持ち込まない。必要な根拠は設計文書、正本ファイル、Commit SHA、検証証拠へのリンクで示す。
3. 「現在の作業目標」など短期間で古くなる進捗情報は、恒久的な仕様説明と分ける。
4. 実装済み機能を未登録・試験段階のまま説明したり、過去の対応環境を現行対応と混同したりしない。
5. 定義ファイルへの登録を、実環境での検証成功と読み替えない。未実施の検証は明示する。
6. READMEと構造資料で、同じ実行契約を別々に定義しない。

機能や契約の変更時には、実装・テスト・機械可読な定義の整合を確認し、関連する現行文書とこの案内を更新します。
