# Unity CIをWindows / Linuxで実行する（P9）

統合済みの [Fixture一覧](../tests/unity/matrix.yaml) と `tests/unity/verify/unity_ci.py` を共通Runnerとして使用します。
Windows開発PCでもLinux CIでも同じEditModeテスト・証跡判定です。UnityAgentのRuntime機能ではなく、
Repositoryの開発用CIです。UnityAgentのSource Lock、UPM、Fixture、Historical Evidenceは変更しません。

## 準備

1. Python 3.12以上と、Fixtureが要求する**完全一致のUnity Editor**を別途インストールします。
2. Unity Hub等でそのEditorのライセンスを有効にします。このRunnerはEditorの自動インストールやライセンス認証をしません。
3. Built-in / URP / HDRPの描画Smokeには、利用可能なGPU / Display / Driverも必要です。
4. URP / HDRP実行には `packages.unity.com` への接続が必要です。既存の公式Registry選択方針を維持し、
   実行時にEditor streamに合う安定版SRP 17を選択します。具体的なPackage Versionは証跡に残ります。

| Fixture ID | Editor | 内容 |
|---|---|---|
| `canonical-full` | `6000.6.0f1` | 既存Artist EditMode全体（接続TransportのE2Eではありません） |
| `minimal-6000.6` | `6000.6.0f1` | Version / Importの最小テスト |
| `minimal-6000.3` | `6000.3.12f1` | Version / Importの最小テスト |
| `builtin-smoke` | `6000.6.0f1` | Built-in Scene / Native API / 描画PNG |
| `urp-smoke` | `6000.6.0f1` | URP Scene / Native API / 描画PNG |
| `hdrp-smoke` | `6000.6.0f1` | HDRP Scene / Native API / 描画PNG |

この表は実行対象の宣言です。実Editorでの成功やProduction Supportの追加を意味しません。

## Windows（PowerShell 5.1 / 7）

Repositoryルートで実行します。Execution Policyがスクリプトを制限する場合は、組織の方針に従って
スクリプトを許可するか、後述のPython入口を使ってください。

```powershell
python tests/unity/verify/validate_unity_fixtures.py
python -m unittest discover -s ci/verify -p 'test_unity_ci*.py' -v

# ライセンス有効化済みの場合のみ設定する（trueでも実行成功を保証しません）
$env:UNITY_LICENSE_READY = 'true'
& .\ci\scripts\run-unity-tests.ps1 -Fixture minimal-6000.6
$LASTEXITCODE

# Hub以外の場所に置いたEditorを明示。空白・日本語を含むPathも引用符で渡します。
& .\ci\scripts\run-unity-tests.ps1 -Fixture canonical-full `
  -EditorPath 'C:\Program Files\Unity\Hub\Editor\6000.6.0f1\Editor\Unity.exe' `
  -OutputDirectory 'C:\Unity CI\成果物\canonical-full' -PythonCommand python

# GPU / Display準備済みの場合のみ設定する
$env:UNITY_GRAPHICS_READY = 'true'
foreach ($fixture in @('builtin-smoke', 'urp-smoke', 'hdrp-smoke')) {
  & .\ci\scripts\run-unity-tests.ps1 -Fixture $fixture
  if ($LASTEXITCODE -ne 0) { throw "$fixture did not PASS (exit=$LASTEXITCODE)" }
}
```

省略時は `py -3`、なければ `python` を使用します。`-PythonCommand`で実行ファイルを指定できます。
`-EditorRoot 'D:\UnityEditors'`を指定すると `<root>\<exact-version>\Editor\Unity.exe` を検出します。
`-TimeoutSeconds`の既定値は3600秒です。Repository以外の作業ディレクトリからも絶対Pathでスクリプトを呼び出せます。
Outputの既定値はRepositoryの `artifacts/<fixture>`、指定した相対Outputは呼び出し元の作業ディレクトリ基準です。

PowerShellスクリプトを使わずに同じRunnerを呼ぶこともできます。

```powershell
python tests/unity/verify/unity_ci.py --fixture minimal-6000.3 --output artifacts/minimal-6000.3 `
  --editor-root 'C:\Program Files\Unity\Hub\Editor'
```

## Linux

```bash
export UNITY_LICENSE_READY=true  # ライセンス有効化後のみ
bash tests/unity/scripts/run-unity-tests.sh --fixture minimal-6000.6 --output artifacts/minimal-6000.6
bash tests/unity/scripts/run-unity-tests.sh --fixture canonical-full --output artifacts/canonical-full \
  --editor /opt/unity/6000.6.0f1/Editor/Unity

export UNITY_GRAPHICS_READY=true  # GPU / Display / Driverの準備後のみ
for fixture in builtin-smoke urp-smoke hdrp-smoke; do
  bash tests/unity/scripts/run-unity-tests.sh --fixture "$fixture" --output "artifacts/$fixture" || exit "$?"
done
```

Linuxでは必要に応じてXvfb等を別途起動し、`DISPLAY`を設定します。Shell入口のPythonは
`UNITY_CI_PYTHON`、省略時は `python3` です。共通Runnerの `--timeout` も3600秒が既定値です。

Editor選択の優先順位は `--editor` / `-EditorPath` → `UNITY_EDITOR` →
`--editor-root` / `-EditorRoot` → `UNITY_EDITOR_ROOT` → OS既定のHub配置です。
Windows既定は `%ProgramFiles%\Unity\Hub\Editor`、Linuxは `/opt/unity`、次に `~/Unity/Hub/Editor` です。
明示指定が無効な場合は他のEditorへフォールバックしません。検出したEditorの `-version` も完全一致で検証します。

既存Canaryは `--canary` / `-Canary` で利用できます。公式ArchiveのRelease選択方針はLinux x86_64のままです。
Windowsは選択されたVersionのインストール済み `Unity.exe` が必要です。
`UNITY_ALLOW_EDITOR_DOWNLOAD=true` による公式Archiveのダウンロード・展開は、従来どおりLinux Canary限定です。
この明示的なDownload許可時に限り、`UNITY_EDITOR_ROOT`内に選択Versionがなければ別の一時配置へ展開します。
CLIの`--editor` / `--editor-root`を指定した実行ではDownloadへフォールバックしません。

## 結果と証跡

| 終了コード | evidence.json status | 意味 |
|---|---|---|
| 0 | `PASS` | 完全一致のEditor、非空NUnit全件成功、Editor Log、Package Lock、必要な描画証跡を確認 |
| 1 | `FAIL` | 起動後の非ゼロ終了、Timeout、Assertion、不正/欠落NUnit、Lock/PNG不整合、入力変更など |
| 2 | `BLOCKED_NOT_RUN` | ライセンス/Editor/Graphics不足、Version不一致、起動不能、実行前の前提条件不足 |

`observation`はPASS/実行後FAILで `observed`、BLOCKEDで `not_observed` です。
入力変更検出によるFAILは実Editorの開始前にも起こり得ます。
`editor_test_process_started`はテスト用Editorプロセスの起動有無です。trueでもLicense/Null GPUでBLOCKEDになる場合があります。
不明なFixture、無効な引数、入力と重なるOutputなどは、書き込み前に終了コード2で拒否し、証跡を生成しません。
その場合もPASSとして扱わないでください。

Outputに次のファイルを収集します（生成されたもののみ。未実施のNUnit/PNG/Lockを作りません）。

- `evidence.json`: status / reason、要求・観測Version、Host OS、Editor Path、起動有無、Commit、入力と成果物のSHA-256
- `editor-version.txt`, `editor.log`, `editor.stdout.log`, `editor.stderr.log`
- `results.xml`: NUnit。失敗・不正XMLも診断用に保持
- `requested-manifest.json`, `manifest.json`, `packages-lock.json`, `srp-selection.json`
- `pipeline-smoke.png`, `graphics-device.json`: 描画SmokeのReadPixels結果と実測Device/Version/Pixel Variation

SourceのFixture / Packageは既存のハッシュ検査で保護し、一時Projectは実行ごとに別途作成・削除します。
Output内の前回NUnit等は実行前に消し、前回のPASSを再利用しません。成果物はGit管理外の `artifacts/` 等に置いてください。
Historical Evidenceへコピーして現在の成功と扱うことはできません。

## GitHub Actions

`Unity CI Windows and Linux host`は、毎PRで `ubuntu-latest` / `windows-latest` のHost Testを実行します。
Windows jobではPowerShell入口も実プロセスで検証します。これはUnity Editorを使った検証ではありません。
既存Hub / Artistの必須job名・検証を維持し、Compatibility / Pipeline / Canaryも共通Runnerを使用します。

Compatibilityのライセンス未設定時はHost job内で各Version Fixtureの `BLOCKED_NOT_RUN` 証跡を収集し、
Editor jobをスキップします。Host CIがGreenでも実Editor PASSを意味しません。
`UNITY_LICENSE_READY=true`設定後は従来のEditor jobを実行し、FAILもBLOCKEDも非ゼロ終了でCI失敗になります。
Pipeline Smokeは引き続き手動/定期実行、Canaryは非必須です。

WindowsのセルフホストRunnerを利用する場合は、Repository Variable `UNITY_CI_RUNNER`を
`["self-hosted","Windows","X64"]`などのJSON配列に設定し、既存の`UNITY_EDITOR_ROOT`または`UNITY_EDITOR`、
`UNITY_LICENSE_READY`、`UNITY_GRAPHICS_READY`を設定します。Linuxでも同じVariable名を使用します。
複数Versionの実行では、単一の`UNITY_EDITOR`より`UNITY_EDITOR_ROOT`が適切です。
ライセンスのSerial / Password等をCIの引数・証跡に渡さないでください。

## P9の検証範囲

CloudではUnity Editorが存在せず、実Editor・実NUnit・実描画・実Package解決の検証は**未実施**です。
Host Testの合成Editor/PNG/XMLは状態判定のテストデータであり、Editor成功証跡ではありません。
最初の実Editor実行では、各FixtureのImport / Compile / Testと実Package Lockを確認してください。
