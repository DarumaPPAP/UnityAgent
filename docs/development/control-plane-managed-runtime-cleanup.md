# Control Plane旧バージョンの安全な自動削除

Unity Editor > **UnityAgent > Setup** の「更新 / 修復」または既存の `scripts/install.ps1` から
新しいControl Planeを導入した後、UnityAgent管理下の旧バージョンのPython仮想環境を整理します。

## 削除対象

`%LOCALAPPDATA%\\UnityAgent\\ControlPlane\\v<semver>\\venv` 以下の、
**新しいバージョンより古い**UnityAgent管理Runtimeのみ対象です。
`pyvenv.cfg` と `venv\\Scripts\\unity-agent.exe` が揃っていないもの、
未知の名前、管理外のPython、Codex、Unity Package、Hub、別のユーザーデータは削除しません。

`v0.0.6-beta` / `v0.0.7-beta` → `v0.0.8-beta` は削除候補です。
現在の `v0.0.8-beta` と、将来のより新しいバージョンは保持します。
同じ数値の旧プレリリース段階（alpha → beta 等）も古いものとして扱います。

## 実行順序

1. GitHub Releaseから取得したwheelのSHA-256検証に成功する。
2. 新しい専用venvへpip installし、新しい `unity-agent.exe --help` に成功する。
3. stable shimとUser環境変数 `UNITY_AGENT_CONTROL_PLANE` を新Runtimeへ更新する。
4. 旧Runtime削除を**best effort**で実施。結果をSetupのCurrent StatusとDiagnosticsへ記録する。

**失敗したインストールから旧Runtimeを削除する経路はありません。**
古いRuntimeがプロセスで使用中、CIM経由の実行中プロセス判定ができない、
またはフォルダの途中にjunction/symlinkを含む場合は、削除せず警告します。
既存のユーザーファイルを移動・再利用していないため、削除できない場合は使用中のプロセスを終了し、
Unity Editorから再度「更新 / 修復」を実行してください。
**強制削除や再起動後の自動削除予約はしません。**

対象外の旧 `pip --user` Runtime（`AppData\\Roaming\\Python` 等）は、他の
pipパッケージを巻き込む危険があるため自動削除しません。
この方式の移行が必要なら、検出結果を確認して別途明示的なアンインストール手順を使ってください。

## 検証と制限

- `tests/packaging/test-managed-runtime-cleanup.ps1` は本物のインストーラーからcleanup関数を読み込み、
  隔離された一時ディレクトリ内で削除可否、実行中保持、将来Version保持、未知ファイル保護、
  処理中エラー時の保護と2実装の一致を検証します。
- `.github/workflows/windows-bootstrap-smoke.yml` は実Releaseインストールの前に
  模擬旧managed Runtimeを作り、インストール完了後だけ消えることを確かめます。
- Windows CIでは実行できますが、手元のUnity Editorでの導入確認は別Gateです。
- 表示上の `READY` はバージョン/存在の判定であり、接続Full E2E PASSを保証しません。
