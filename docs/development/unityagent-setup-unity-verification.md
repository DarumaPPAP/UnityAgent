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

UnitySubAgentHubをClone・取得する必要はありません。UnityAgent内の
`ci/` Fixtureと同一の検証SourceをUPMの
`Editor/Verification~/`に同梱しています。UPMの検証用ManifestはGit blob IDと
サイズの検査で改変・欠損を拒否します（Git SHA-1は暗号学的な真正性保証ではなく、
Package自体の信頼境界はレビュー済みUnityAgent UPM Revisionです）。

`UnityAgent > Setup > 5. Unity Verification`を開いて
`検証環境を再確認`を押すと内容を照合します。
READYならFixtureとUnityライセンス準備を確認後、
`選択したUnity検証を実行`を押してください。
Hub Source Lock/Git clone/ユーザーScope Cacheを必要としません。
必要なUnity Editor実行ファイル、Python 3.12+、GPUは別の前提条件です。

独立した一時Projectで実行します。手元のゲームProject/Control Plane/Providerは変更しません。
RunnerはUnityAgentの `ci/scripts/run-unity-tests.ps1` と同じ内容です。

## 4. Evidenceと制約

検証結果はシステム一時ディレクトリの
`UnityAgentVerification/<run-id>/` に保存され、Setupから開けます。
`evidence.json`, `results.xml`, `editor.log`, `packages-lock.json`,
描画テストの場合は`pipeline-smoke.png`等を記録します。

ExitCode 0かつ`evidence.json`の`status=PASS, observation=observed`のみPASS。
ExitCode 2かつ`status=BLOCKED_NOT_RUN, observation=not_observed`はBLOCKED。
証跡なし・矛盾した結果はFAILです。Host Testや合成Evidenceを実Editor PASSと判断しません。

現行UIは**Windows Editor用**で、P9 Linux入口はUnityAgentの `ci/scripts/run-unity-tests.sh` です。
Canary、UnityAgent Control Plane → 実EditorのFull E2E、Player/実機は別検証Gateです。
Public RepositoryのPRからライセンス済みPCをSelf-hosted Runnerとして実行させないでください。

## 5. 既知の未検証部分

CIのPython静的契約やHost Testが成功しても、**実Unity Editorでこの新しいUIがコンパイル・起動し、
別EditorのP9検証を実際に完了することは独立した観測が必要**です。
未実行は`BLOCKED_NOT_RUN`として記録し、フルE2E完了とは扱いません。

## 6. Editor Play / Timeline 動画Evidence（G1/G2補助）

Player Buildを毎回行う代わりに、描画可能なUnity Editor上でPlay / Timelineを録画できます。
`UnityAgent > Play Evidence`、または`UnityAgent > Setup`の
`6. Play Mode確認（スクリーンショット / 録画）`から開きます。

- Unity 6 / Windows・macOS Editor: 公式`UnityEditor.Media.MediaEncoder`でH.264 MP4を出力。
  `com.unity.recorder`のインストールは不要。Linux EditorでH.264 MP4を要求した場合は
  `PlatformNotSupported`で拒否し、別形式への黙示的Fallbackは行いません。
- PNG: 標準`ScreenCapture.CaptureScreenshot`を使用。非同期保存があるためPNGヘッダーとサイズを検証。
- 動画: `PlayVideoEncoder`がGame View / Device Simulator最終合成RTを1セッションだけ所有し、
  `MediaEncoder.AddFrame`で記録します。H.264 High、入力解像度は表示Game View原寸または50%、
  FPSは30/60、上限は5〜600秒。4Kで録る場合はGame View自体を4Kへ設定してください。
- **重要:** Game View RT取得はUnity 6の非公開`PlayModeView.m_TargetTexture`を
  Reflectionで使用するため、内部APIの存在と描画をG1で必ず実測。見つからない場合は録画開始を拒否。
  同一EditorでCameraのみを再描画するFallbackはUI・URP Camera Stack・PostProcessの一致を保証しないため未導入。
- 固定FPS MP4は実時間録画です。描画不足による重複フレーム数`repeated_frames`、
  取得不能/エンコード失敗`skipped_frames`を記録します。フレーム完全同期ではなく、
  `video_timing=realtime_not_frame_exact`を明示します。
- MediaEncoderを閉じてからMP4ファイルサイズ・`ftyp`シグネチャ・SHA-256を検証します。
  ファイルが再生できることや画質が一致することは、別途人間または映像デコードで検証します。

### Play録画

1. 対象SceneとGame Viewを開く。Playを開始する（既存のPlay中に起動してもよい）。
2. `通常Playを録画 (MP4)`を選択。操作・描画後、`録画を終了して保存`を押す。
3. PNGが必要なら`Screenshot (PNG)`を押す。Pause中のPNGは古い描画内容の可能性がある。
4. `play-evidence.json`、MP4、PNG、Consoleエラー、`skipped_frames`、
   `repeated_frames`を照合し、映像を実際に再生して品質を確認する。

### Timeline録画

1. **Play中**に`Timeline (任意)`へScene内の`PlayableDirector`を指定する。
2. `Timelineを先頭から再生して録画 (MP4)`を押す。
3. 対象Directorを停止→`Play()`でGraph再構築→時刻0→`Evaluate()`で開始する。
   Directorの`stopped`イベント、有限`duration`への到達、最大録画時間、
   ユーザーの停止、Play終了、Window破棄またはDomain Reloadで録画を終了する。
4. TimelineのCamera切替、Cinemachine、URP Camera Stack、PostProcess、
   Screen Space Overlay UIを実録画で確認する。

**非対応と今後のGate:** 非対話型Editorでの録画、ゲーム音声の合成、
EXR/ProRes、高品質オフライン・フレーム単位Render、Timeline内のParticle/Physics/Audioの
決定論的再現は未実装です。単に`PlayableDirector.Evaluate()`を呼んだだけでは保証できません。
録画中のMain Thread・GPU Readback・Encoder負荷はProfilerで別途測定し、
性能評価は録画を止めた状態をBaselineにしてください。

### Evidence / 受入

保存先: OS一時フォルダ `UnityAgentPlayEvidence/<run-id>/`。ProjectのAssets、
ProjectSettings、Player Buildは触りません。

Evidenceには`capture_kind=editor_play`、Run ID、Editor Version、Scene、Project、
開始/更新時刻、Timeline Director/Asset、画像/動画PathとSHA-256、
停止原因、FPS、解像度、エンコード・欠落・重複フレーム数、Console Error/Exception/Assert数を記録します。

`CAPTURED`は**Captureファイルの取得確認のみ**を意味します。
エラーや重複・欠落があれば`CAPTURED_WITH_RUNTIME_ERRORS`、
`CAPTURED_WITH_TIMING_VARIATION`など別Statusで示します。
`visual_acceptance=human_review_required`、
`e2e_gate=not_assessed`は固定し、正式G1/G2/Persistenceへ自動昇格しません。
実際のG1/G2 PASSにはScopeの承認、実行前Compile、具体的な期待結果、
Runtime例外確認、Evidence Store append、必要な人間によるVisual判定が追加で必要です。

#### G1実Unity Editor受入マトリクス（**未実施**）

| 対象 | 合格条件 | 記録 |
|---|---|---|
| Unity 6000.3.x / URP | Console Compile Errorなし、30fpsのPNG/MP4出力 | PNG / MP4 / evidence.json / editor.log |
| Unity 6000.6.x / Built-in | Game View描画を記録 | 同上 |
| Unity 6000.3.x / Timeline | Scene内DirectorのCamera切替、開始停止、指定区間を確認 | 動画再生・停止理由 |
| Unity 6000.3.x / URP UI | Overlay Canvas、色・上下向き・PostProcessの一致 | PNG/動画の目視比較 |
| 異常系 | Game View未描画、Play終了、Domain Reload、解像度変更、Editorフォーカス喪失、録画上限 | Fail-Closed、終了理由、破損なし |
| FPS | 30/60fpsの出力再生時間とフレーム数を外部デコーダで検証 | ffprobe等 / Editorログ |

静的テストは`python -m unittest discover -s tests/packaging -p 'test_play_evidence_source.py'`。
このテストだけではUnity Compileや映像品質を証明できません。
