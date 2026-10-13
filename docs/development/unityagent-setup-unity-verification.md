# UnityAgent Setup — Control Plane更新とUnity検証（Editor UI）

この機能の操作入口は **Unity Editor > UnityAgent > Setup** の既存Windowだけです。
新しい独立Window、Hub Runtime、Provider/Installerは追加しません。

## 1. UnityAgent UPMを現在のソースへ更新する

この変更はGitHub mainへ統合された後に、利用中のUnity ProjectのUPM Packageを更新して初めて表示されます。
Unity Editorの画面が `v0.0.7-beta` のままの場合、Projectが旧Packageを参照しています。
Control Planeの更新だけではUnity Editor Package自体は更新されません。

開発検証では、Unity Package ManagerのGit Package参照を、
`https://github.com/DarumaPPAP/UnityAgent.git?path=/Packages/com.darumappap.unity-agent#<reviewed-commit-sha>`
に合わせます。既存Projectの `Packages/manifest.json` 内の依存関係とLockを確認したうえで作業し、
旧Packageを強制削除したり、承認なくmain追従へ切り替えたりしないでください。
既存のRelease tag `v0.0.8-beta` は今回の開発変更を含むとは限りません。タグは改変しません。
`<reviewed-commit-sha>` は必ず検証対象のGitHub mainフルコミットSHAに置き換えてください。

## 2. Control Planeを診断・更新する

Setup画面の `1. UnityAgent Control Plane` は、管理runtimeのversion Pathを確認します。

- `READY`: インストール先のバージョンが現在のUPM channelと一致（実行・機能のPASSではありません）
- `STALE`: 古いバージョンPathが存在
- `VERSION UNKNOWN`: Pathからバージョンを断定できない。Doctorを使って確認
- `ACTION REQUIRED`: 実体が見つからない

検出済みの場合も `更新 / 修復` / `再インストール / 修復` が使えます。
操作前に確認ダイアログを表示し、既存SHA-256検証付きBootstrapで
`%LOCALAPPDATA%/UnityAgent/ControlPlane/<release>/venv` に導入します。
更新が成功した場合はUnity Editor内の古いprocess環境変数も新しいruntimeへ切替えます。
`Manual override` は無断変更せず、必要なら画面で明示的に解除してください。

`4. Unity Environment` で現在のEditor/UPM/Control Planeのバージョンを表示し、
既存の `全Toolchain Doctor` と `全Toolchain Plan` を利用できます。
Doctorはoptional SubAgentのInstalled/Bind/Compatibilityを別途評価します。

## 3. P9 Unity検証の実行

`5. Unity Verification` に、手動Hub checkoutを指定する欄はありません。
`検証環境を取得・更新` を押し、Source Lockに固定された `DarumaPPAP/UnitySubAgentHub` の
正確なCommitを承認して取得します。取得はUnityAgent管理のユーザーキャッシュ
`%LOCALAPPDATA%/UnityAgent/VerificationHub/<commit>/` に限定されます。
Gitが使用できない、通信失敗、Pin不一致、キャッシュ汚染の場合はBLOCKED_NOT_RUNです。
Hubの現在のmainや、ユーザー選択の未検証コードを実行しません。

取得完了後、Fixtureを選択してEditor内で実行してください。認証済みライセンス、
必要に応じGPU/Displayの確認を行い、別Unity Editorのプロセスで実行します。
Control PlaneやProviderのInstallは行いません。

## 4. Evidenceと制約

検証結果はシステム一時ディレクトリの
`UnityAgentVerification/<run-id>/` に保存され、Setupから開けます。
`evidence.json`, `results.xml`, `editor.log`, `packages-lock.json`,
描画テストの場合は`pipeline-smoke.png`等を記録します。

ExitCode 0かつ`evidence.json`の`status=PASS, observation=observed`のみPASS。
ExitCode 2かつ`status=BLOCKED_NOT_RUN, observation=not_observed`はBLOCKED。
証跡なし・矛盾した結果はFAILです。Host Testや合成Evidenceを実Editor PASSと判断しません。

現行UIは**Windows Editor用**で、P9 Linux入口は引き続きHubのShellスクリプトです。
Canary、UnityAgent Control Plane → 実EditorのFull E2E、Player/実機は別検証Gateです。
Public RepositoryのPRからライセンス済みPCをSelf-hosted Runnerとして実行させないでください。

## 5. 既知の未検証部分

CIのPython静的契約やHost Testが成功しても、**実Unity Editorでこの新しいUIがコンパイル・起動し、
別EditorのP9検証を実際に完了することは独立した観測が必要**です。
未実行は`BLOCKED_NOT_RUN`として記録し、フルE2E完了とは扱いません。
