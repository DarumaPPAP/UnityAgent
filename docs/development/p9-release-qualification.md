# P9 Unity 6.3 LTS Release Qualification（G1とは独立）

## 決定と対象

- 通常PRは公開CIのG0契約・Host検証を必須とし、実Editor起動をすべてのPRに要求しない。
- UnityAgentの標準P9基準は **Unity 6000.3.12f1 / URP 17.3.0** に固定する。Unity 6.6の既存Artist/Built-in/URP/HDRP Fixtureは互換性検証として維持する。
- Release候補のソースCommit SHAを固定し、同じSHAのP9実Editor PASSだけをBeta Releaseの前提とする。
- G1 Production E2Eの独立承認は変更しない。レビュアー不在の間、G1は `BLOCKED_NOT_RUN`、Production Verifiedは不可。
- 未検証のBlender→Unity、動的SubAgent協業、RollbackをBetaのProduction Verified能力と宣言しない。既存Policy / ApprovalとCapability availabilityに従う。

## 非公開P9 Runner（個人環境はオンデマンド）

1. 通常開発PC・通常Windowsユーザーで、**必要時だけ**GitHub Actions Runnerを起動する。専用Windowsユーザーは企業向けの強化オプションであり、個人環境では必須としない。
2. Private実行リポジトリに `ci/private/p9-release-verification.yml` を `.github/workflows/p9-release-verification.yml` として配置する。保護された `main` と `p9-verification` Environmentで起動する。公開PRのRunnerには接続しない。
3. ラベル `self-hosted` / `Windows` / `unity-6000.3.12f1` / `private-only` を使用。ローカル環境にUnity 6000.3.12f1、GPU、Unityライセンス、Python 3.12+を用意する。
4. Private Repository Variable `UNITYAGENT_APPROVED_SHA` を**Release候補の40文字Git SHA**に設定する。事前にGitHubレビューを終えたCommitを選ぶ。
5. Runner実行環境に `UNITY_EDITOR`（正確なUnity.exeパス）、`UNITY_LICENSE_READY=true`、`UNITY_GRAPHICS_READY=true` を、実際に確認した上で設定する。Unity Editor使用中に別Editorを起動しない。
6. Private workflowを手動起動する。実行終了後にRunnerを停止する。P9とG1の同時実行は禁止。Editorの実起動、NUnit、Package Lock、PNG、Graphics Device、入力SHAが一致しない場合はPASSとしない。

## Beta Release前のEvidence Gate

公開UnityAgent Release Workflowの起動前に、Private側のP9 Run IDを確保する。

公開側のRepository Variable `UNITYAGENT_P9_REPOSITORY` = `owner/private-repo`、Repository Secret `UNITYAGENT_P9_EVIDENCE_TOKEN` = 当該Private repoの**Actions:read限定**トークンを設定する（トークンをログやartifactへ保存しない）。個人/組織の権限管理はGitHubで行う。

Release Workflowの `p9_evidence_run_id` に該当Run IDを指定し、`confirm_release`を明示する。Release jobはGitHub APIからPrivate Runの完了、Workflow名・Path・手動起動・mainを確認し、GitHub Actions artifact `unityagent-p9-lts-urp` を取得する。 `tools/release/verify_p9_evidence.py` が次を検証する。

| Gate | 条件 |
|---|---|
| Run | Private main上の所定Workflow / workflow_dispatch / conclusion=success |
| Source | `source_identity.commit == Release GITHUB_SHA` |
| Editor | `requested_editor` と `observed_editor` が共に `6000.3.12f1` |
| Evidence | `PASS` / `observed` / 同一Run ID / 入力変更なし |
|実描画| URP 17.3.0、NUnit PASS、GPU非Null、PNG、Log、Package Lock、SHA256が整合 |

どれか一件でも未取得・不一致・期限切れのArtifactは **Fail-Closed**。Tag生成前に停止し、`BLOCKED_NOT_RUN` はRelease合格としない。P9のPASSはG1の9 Gateの代替ではない。

## Projectでの検証

対象は機密ゲームProjectではなく `tests/unity/projects/production-e2e` のDisposableコピー。P9のみなら `UNITYAGENT_PRODUCTION_FBX` / `rock apply` は**不要**であり、`RockProductionTests` は起動しない。

ローカルWindowsでの実行例：

```powershell
$env:UNITY_LICENSE_READY = 'true'  # Unity Hubで実際の有効なライセンスを確認した後
$env:UNITY_GRAPHICS_READY = 'true' # GPU/Displayが利用できることを確認した後
& .\tests\unity\scripts\run-unity-tests.ps1 -Fixture p9-lts-urp `
  -EditorPath 'C:\Program Files\Unity\Hub\Editor\6000.3.12f1\Editor\Unity.exe' `
  -OutputDirectory '.\artifacts\p9-lts-urp'
```

PowerShellの改行継続はバッククォートを使用するか、1行で実行する。実際のEditor Pathは設置先に合わせる。

手元でP9が成功しても、Private workflow経由の**同一SHA証跡をRelease Gateが受領**するまではRelease不可。G1のProduction Verifiedは独立のまま。
