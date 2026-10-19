# 固定Full E2E：Repository管理のローカル検証

## 目的と境界

UnityAgentの既存 `fixed_full_e2e_probe` を、Repository内のFixtureを使いWindows Unity 6.3.12f1で検証する。
P9とは独立に **Control Plane → ToolBroker → EditorでScene/Material/C#生成 → Compile → PlayMode → Persistence Evidence** を観測する。
正式G1（Blender → Unity Import → QA → Rollback）、Player、実機のGateを成功扱いしない。

正本は `tests/unity/projects/production-e2e/` と `Packages/com.darumappap.unity-agent/`。
テストProject、UPMコピー、ホストCLIのvenv、State、Evidenceは `%TEMP%/ua-e2e/e2e-*/` 以下に生成する。
ユーザーのゲームProject、常設の追加Repository、Self-hosted Runnerは利用しない。

## 実行

Host専用Runnerは `tools/full_e2e/` に置き、UPMへMirrorされる `tests/unity/` の正本Fixtureを読み取り再利用する。Runner自体はUPM Verification Bundleへ同梱しない。

Windows、Unity `6000.3.12f1`、有効なライセンス、Python 3.12、Gitが必要。初回のCLI依存パッケージ導入にはネットワークが必要となる場合がある。
PowerShellの未署名スクリプト制限を緩めず、Pythonから直接実行できる。

```powershell
cd D:\UnityAgent
py -3.12 tools\full_e2e\run.py --expected-sha (git rev-parse HEAD)
```

ここで `(git rev-parse HEAD)` は現在の開発Revisionを表示するだけで、外部レビュー済みSHAであることを証明しない。
レビュー済みの40文字SHAを明示すると、その値とGit HEADが異なる場合は起動前に停止する。
PowerShellラッパー `tools/full_e2e/run.ps1` も同梱。署名必須環境では無理に実行しない。

Planのみ確認する場合：

```powershell
py -3.12 tools\full_e2e\run.py --plan-only --expected-sha (git rev-parse HEAD)
```

## 実行と承認

1. Git SHAとFixture・UPM・Control Planeのソース状態を検証。未コミット変更・Symlink・不整合は拒否する。
2. RepositoryのFixtureとUPMのコピーを一時Workspaceに生成。UPM `file:` パスはそのコピー内のManifestのみ変更する。
3. 同一Repository Revisionから隔離venvへCLIをインストールし、`e2e plan` の7ファイル固定DiffとScript全文を提示する。
4. 利用者が `MUTATION <plan-prefix>` を入力した場合のみ、専用Unity Editorを起動してheartbeatを観測し、`e2e approve` を呼ぶ。
5. 続いて別入力 `SAVE <plan-prefix>` を求め、`e2e approve-save` を実行してから `e2e apply` する。
6. `completed`、`compile=passed`、`playmode=passed`、Evidence参照と保存済みRun結果一致を確認する。

承認拒否、Source変更、Editor未起動、Compile・PlayMode失敗、期限切れはPASS扱いしない。
Editorは強制終了させない。完了後にユーザーが専用Unity Editorを閉じ、一時Workspaceを必要な証跡を保存した上で削除する。

## Evidenceと制約

`%TEMP%/ua-e2e/e2e-*/evidence/` に `plan.json`、`result.json`、`summary.json`、CLI / Editorログを保存する。
正式な署名付きEditor Result、Control Plane Evidence、Stateは同一Workspaceの `state/` にある。
Resultの `E2E_EDITOR_VERIFIED` はローカルの固定E2E成功のみを表す。GitHub Actions実行証明ではない。
ログにはOSアカウント・ローカルパスが含まれ得るため、公開Repositoryへ直接Uploadしない。
生成したWorkspaceの自動削除は、Editorが稼働中のProjectファイルを保持し得るため行わない。

## Host回帰テスト

```powershell
py -3.12 -m unittest discover -s tests/runtime -p "test_full_e2e_ci.py"
```

Fixture隔離、UPM参照の維持、Template Hash不一致・Symlink・Scope違反・変更済みSource・未承認の拒否を検証する。
HostテストPASSと実Unity Editor成功を混同しない。

参照：Unity Package Managerの[Local folder dependency](https://docs.unity3d.com/Manual/upm-localpath.html)は `file:` パスをProjectの `Packages` フォルダ基準で解決する。
