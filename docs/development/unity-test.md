# UnityAgent テスト運用（旧Regression撤去後）

## 現行正本

- 日常のHost Smoke: `tests/smoke/` のCLI起動・Project/Editor接続・読取と失敗検出。
- Host実行: `python tools/validate_all.py --profile smoke`。
- 静的Repository検証: `python tools/validate_all.py --profile full`。現行ValidatorとSmokeを実行するが、削除した旧Regressionに相当する保証はしない。
- 実Editor接続とHierarchy取得: `python tests/smoke/live_connection.py --project <UnityProject> --cli unity`。未接続は `BLOCKED_NOT_RUN`。
- Unity Release P9検証正本: `Packages/com.darumappap.unity-agent/Editor/Verification~/tests/unity/`。UPM Source Manifestで同一性を検査。旧 `tests/unity/` と内容が同一のため重複Copyを削除。
- 開発用Unity ProjectとしてRepository自体を利用する。旧 `tests/UnityAgentTest/`の独立Projectは廃止。

## 安全性とリスク

Host Smokeや静的ValidatorのPASSは、Approval / Mutation Scope / Orchestration / Persistence / Evalなどの削除済みRegressionを再実行した証明ではない。これらの機能の変更時にはRiskに応じてTask限定Testを作成し、必要な永続Testは既存のTest Lifecycle Skillで採用審査する。実Unity Editor/Player/Target Device/Visual/Performanceは証拠を別に保存し、未観測をPASSにしない。ReleaseのHuman-gated P9実Unity Evidence要求は維持。

## 旧テストの復元

一括撤去前のGit Commit SHA: `77483d6ecc656b8842954cd509de5d9ce7224c2f`。必要なSourceはそのRevisionから部分復元できる。削除したテストの実行結果を新Revisionの検証成功として流用しない。
