# UnityAgent｜常設Smoke正本

常設Hostテストは起動・接続・読取のみ。以下を既存Python `unittest` で実行する。

```bash
python tools/validate_all.py --profile smoke
python tools/validate_all.py --profile full
python tests/smoke/live_connection.py --project /path/to/UnityProject --cli unity
```

| File | Purpose | Reuse・独立の理由 |
|---|---|---|
| `test_bootstrap.py` (8) | CLI入口・Project Binding・Version読取 | 公開CLIと既存Project Identityを再利用。実Unityではない |
| `test_connection.py` (12) | Provider登録・CLI構造化応答・接続拒否・OS排他 | Registry、Unity CLI Command Builder、Result Mapper、既存Project Leaseを再利用。File Readとは故障モードが異なる |
| `test_read.py` (8) | 実File・Project設定・Read Evidence・Policy拒否 | FileProviderと既存Evidence projectionを再利用。Run所有のTemporaryDirectoryだけ使用 |
| `live_connection.py` | 実Unity CLI + 接続EditorによるHierarchy取得 | 既存CLI Command Builder/Result Mapperを再利用。環境依存のため別入口とし `BLOCKED_NOT_RUN` を明示 |
| `README.md` | 上記の責務・費用・検証境界 | 複数Testファイルに同じルールを複製しない |

`--profile full` は静的ValidatorとHost Smokeを検証する。旧Regressionテストはユーザー指示で削除したため、Approval、Mutation、Orchestration、Persistence、Eval等の**旧Regressionの検出能力は保証されない**。旧テストの固定SHA: `77483d6ecc656b8842954cd509de5d9ce7224c2f`。

実Unity用のP9検証入力はUPM内 `Packages/com.darumappap.unity-agent/Editor/Verification~/tests/unity/` が正本（削除した `tests/unity/` と同じGit Blob）。手動Live SmokeやPrivate P9で実観測しない限りEditor/Player/実機は `BLOCKED_NOT_RUN`。一時的なテストはTask終了時に削除し、Skillの審査を経て必要な場合のみ恒久採用する。
