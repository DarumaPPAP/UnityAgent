# UnityAgent 標準テストProject

Unity **6000.3.12f1** / URP **17.3.0** / Test Framework **1.6.0**。
本番UPMを `file:../../../Packages/com.darumappap.unity-agent` で参照します。
別のRunner、Dispatcher、Project Pinは使いません。旧 `tests/unity/` Fixtureは互換性・P9検証用に維持します。

## Unity Editorでの手動確認

1. Unity Hubの「Add」でこの `tests/UnityAgentTest` フォルダを登録し、6000.3.12f1で開きます。
2. Package Managerの解決・Import完了を待ち、UnityAgent、URP 17.3.0、Test Framework 1.6.0を確認します。
   Manifestは準備済みですが、Package解決はCloudで未観測です。初回の `packages-lock.json` はEditorが生成します。
3. ConsoleのCompile Errorを確認し、`UnityAgent > Setup` メニューが表示されることを確認します。
4. `Window > General > Test Runner` を開き、EditModeの `Run All` を実行します。
   本番Editor Assembly / SetupWindowとAssetDatabaseのURP Material往復を検証します。
5. PlayModeの `Run All` を実行します。専用の一時SceneでGameObjectとMonoBehaviourのAwake / Startを観測します。
   Smoke Testは専用の一時Asset / Sceneを後処理し、Full E2Eや描画品質の合格を証明しません。
6. ConsoleとTest Runner結果を確認し、結果XML、Editor.log、Unity / OS / PackageのVersion、対象Commit SHA、再現手順を共有してください。
   エラー時は最初のCompile Errorとスタックトレースも含めます。

ルートの開発Projectは同じUnity Versionを使用し、`Packages/com.darumappap.unity-agent` をEmbedded Packageとして読み込みます。
SceneやURP Pipeline Assetはまだ生成していません。描画設定が必要ならEditorでURP Pipeline Assetを生成し、Graphics / Qualityへ設定してください。

## CLIとFull E2E

Repositoryルートで本番CLIをインストールします。

```powershell
python -m pip install -e .
cd tests/UnityAgentTest
uagent doctor
uagent setup plan
uagent e2e plan
```

`setup apply` には既存契約の `--approved-plan`、`--expected-plan-id`、`--approval-ref` などが必要です。
別Projectは `uagent doctor --project-p D:\Projects\MyGame`。旧 `--project-path` と `unity-agent` も互換利用できます。
CWDから親方向に最寄りのProjectを探し、接続中Editorを理由にProjectを切り替えません。

Full E2Eを実行する場合は [既存手順](../../docs/architecture/full-e2e-capability.md) に従います。

- Editorで新規Sceneを作成し、`Assets/Scenes` などへ保存しておきます。未保存Sceneを残さず、Compile / PlayMode中は実行しません。
- `Assets/UnityAgentE2E` とその `.meta` は不存在である必要があります。
- 同じProjectを開いたEditorのBridge接続を確認し、`--state-root` はProject外に置きます。
- Planの差分を確認し、MutationとScene保存をそれぞれ承認します。自動承認は行いません。
- `uagent e2e approve --plan-id <id>`、`uagent e2e approve-save --plan-id <id>`、
  `uagent e2e apply --plan-id <id> --approval-ref <ref> --save-approval-ref <save-ref>` を同じProject / State Rootで使用します。
  CWDを別Projectへ変更した場合はPlan不一致として拒否されます。

Developmentではレビュー済みCommit SHAのCheckoutからCLIとUPMを利用します。
`uagent --help` の解決先、EditorのPackage Source、EvidenceのRevision / Fingerprintを確認してください。
Git SHAの記録や同一Checkoutだけでは、既存インストール済みHostと実行中EditorのRevision一致を証明できません。
Editor再Import / CLI再インストールと実行結果の照合を手動で確認する必要があります。
Releaseは [既存P9 Release Gate](../../docs/development/p9-release-qualification.md) を維持します。

## 検証状態

Cloudでの準備時点では次はすべて `BLOCKED_NOT_RUN` です。実測後にGateごとに結果を記録してください。

| Gate | 初期状態 |
|---|---|
| Unity Package Import / Package解決 | BLOCKED_NOT_RUN |
| Unity Compile | BLOCKED_NOT_RUN |
| Unity EditMode | BLOCKED_NOT_RUN |
| Unity PlayMode | BLOCKED_NOT_RUN |
| Unity Full E2E | BLOCKED_NOT_RUN |

Host / Static合格や `READY_FOR_MANUAL_TEST` は、これらのUnity Gateの合格を意味しません。
