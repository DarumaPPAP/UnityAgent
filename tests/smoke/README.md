# Tests — bootstrap, connection and read-only observations

このフォルダで継続して実行するのは `smoke/` の27件と、実Unity環境で明示実行する `smoke/live_connection.py` のみ。

## 削除の範囲と検証レベル

- 旧 `tests/` 配下309ファイル（Runtime, Approval, Mutation, SubAgent, Eval, Unity Fixture/C#/Scene/metaを含む）は、ユーザーの明示依頼で撤去した。復元元は `77483d6ecc656b8842954cd509de5d9ce7224c2f`。テストファイルだけではなく、Unity用FixtureとAssemblyも削除対象である。
- 旧テストが担っていた安全性、Approval、Mutation Scope、Lease、E2E等の回帰保証は**失われた**。CIのPASSを製品全体の品質保証と解釈しない。
- `python tools/validate_all.py --profile smoke`: Hostの起動・接続・情報取得の27ケースを実行。
- `python tests/smoke/live_connection.py --project <UnityProject>`: 実Unity CLI/Editor経由の手動確認。実環境がない場合は `BLOCKED_NOT_RUN`。
- 旧`--profile full`は廃止した。Fullを要求した場合は失敗する（偽のPASSを防ぐ）。
- `.github/ProductionSmoke/`、`tools/`、`eval/`にある正本ツール・Host検証、`Packages/`内の配布物はこの削除の対象外。ただしそれらの一部は旧`tests/`に依存する可能性があるので、必要なEnvironmentで個別に検証する。

今後の一時テストはTask終了時に削除し、長期採用は `.agents/skills/test-lifecycle/SKILL.md` の審査を経る。
