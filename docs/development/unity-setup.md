# UnityAgent 起動・接続・情報取得のセットアップ

現行Host検証の正本は `tests/smoke/`。旧 `tests/UnityAgentTest/`、Host Regression専用Project、重複する `tests/unity/` は全面撤去済み。詳しくは [テスト運用](unity-test.md) を参照。

## 必要条件

- Python 3.12（依存は `pyproject.toml` に従って導入）
- 開発用のUnity Project（Repositoryルート、またはユーザーが指定したProject）
- 実Editor接続を検証する場合のみ、対象Projectに合ったUnity EditorとUnity CLI。UnityAgentのControl PlaneをAuthorityとし、MCPは必須依存にしない。

## 通常のHost検証

```bash
python -m pip install -e .
python tools/validate_all.py --profile smoke
python tools/validate_all.py --profile full
```

`smoke` は起動・接続・Read-onlyの28件、`full` は既存Static ValidatorとSmoke。どちらも実Unity Editor成功や削除済みRegressionの同等性を証明しない。

## Unity Editorへの実接続

```bash
python tests/smoke/live_connection.py --project /path/to/UnityProject --cli unity
```

対象Projectの完全一致、単一Ready Editor、実Hierarchy取得を要求する。環境不足は `BLOCKED_NOT_RUN` であってPASSではない。実Unity変更やApprovalが必要な検証は既存PolicyとTask限定Testで扱う。

## Release時のP9検証

同梱 `Packages/com.darumappap.unity-agent/Editor/Verification~/tests/unity/` が正本で、UPM内Source ManifestがHash整合を守る。実Unity 6.3、URP、TargetのEvidenceはPrivate P9の手動Gateを使う。Host Smokeからの推測は禁止。

## 旧資料

旧テストProject構築手順とRegressionの履歴はGit SHA `77483d6ecc656b8842954cd509de5d9ce7224c2f` を参照し、現行手順として再利用しない。
