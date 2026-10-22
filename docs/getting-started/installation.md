# 導入とRevisionの選び方

通常の利用は公開Betaから始めます。Developmentは新機能の検証・開発向けです。同じ `0.0.8-beta` というVersion表示でも、公開Tagとmainのコードは同じとは限りません。

## 公開Releaseから導入する

確認対象は [v0.0.8-beta](https://github.com/DarumaPPAP/UnityAgent/releases/tag/v0.0.8-beta)、Commit `f093d82feac1cd02fa779491d8a7e7abedfe8af8` です。「公開済み」はすべての実環境Gateが検証済みという意味ではありません。

### 前提環境

- Unity 6.x+とGit。Artist Backendの対象PipelineはBuilt-in・URP・HDRPです。
- WindowsでのControl Plane BootstrapにはWindows PowerShell 5.1以上とPython 3.10以上。
- Codex連携を使う場合はCodex CLIと利用可能な認証環境。Unityライセンスや描画環境は実Editor検証時に別途必要です。

Unity Package Managerの「Add package from git URL」で追加します。

```text
https://github.com/DarumaPPAP/UnityAgent.git?path=/Packages/com.darumappap.unity-agent#v0.0.8-beta
```

`UnityAgent > Setup` を開き、Control Planeの導入・検出を行います。Package同梱Bootstrapは対応するRelease wheelとChecksumを取得し、SHA-256を照合してLocalAppDataの管理runtimeへ導入します。Control PlaneだけのBootstrapと、導入後のProvider・Plugin Setupを区別してください。

Package追加・Control Plane導入の後は [最初の操作](first-task.md) へ進みます。古いPackageやHostが残る場合は、ProjectのPackage参照、Control Planeの検出パス、手動Overrideを確認します。Hostの更新だけではUPMは更新されません。

### Codex連携（任意）

SetupからCodexの状態を診断し、導入・修復の計画と対象を確認して承認します。手動のMarketplaceコマンドは [READMEの導入例](../../README.md#install) を参照してください。追加後は新しいCodexのチャットで開始します。

### Hostだけを導入する場合

Windowsの既存remote Bootstrapも利用できます。Tagを明示してUPMと揃えます。

```powershell
$env:UNITY_AGENT_TAG = 'v0.0.8-beta'
irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/main/scripts/install.ps1 | iex
```

取得するBootstrapスクリプトはmain上のものですが、導入対象は指定Releaseの成果物です。mainのControl Planeを導入するコマンドではありません。Tag未指定時は公開Prereleaseを選ぶため、固定導入では指定を省略しません。

## Developmentを検証する

利用する機能を含むレビュー済みの40文字Commit SHAを選び、UPM・Host・任意Pluginのソースを揃えます。`<reviewed-commit-sha>` は実際のSHAへ置き換え、常時main追従にはしません。公開Tagを付け替えません。

UPMのGit URL：

```text
https://github.com/DarumaPPAP/UnityAgent.git?path=/Packages/com.darumappap.unity-agent#<reviewed-commit-sha>
```

Hostは対象CommitをcheckoutしたUnityAgent Repositoryで、独立した開発用venvに既存の方法で導入します。

```powershell
git checkout --detach <reviewed-commit-sha>
git rev-parse HEAD
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
uagent --help
```

既存の未コミット変更がない専用checkoutで実行し、既存作業を上書きしません。Editable導入後にSourceを変更すると、同じSHA表示でも実行内容が変わります。検証中はソースを固定し、実行ファイルのパスも記録してください。

Codex PluginもDevelopment版を使う場合は、既存Marketplaceの参照を確認したうえで同じSHAを `--ref` に指定します。別の導入元を黙って置き換えず、Setupの計画・承認境界を維持します。

**Version表示やGit SHAのメモだけでは、実行中のUPM・Hostが同一Revisionだった証明にはなりません。** Release用BootstrapはDevelopmentのHostを導入しません。Setupの明示的なControl Planeパス指定とDoctorで対象を確認し、実装上証明できないRevision整合は未検証として報告します。新しいRunner Pinや管理DBは作りません。

## 更新・修復と実Editor検証

Development側の詳細UIと確認項目は [既存Setupガイド](../development/unityagent-setup-unity-verification.md)、Revision整合と検証環境は [Unity開発・検証環境仕様](../development/unity-test.md#9-revision整合) にあります。高度なSetup UIや検証機能が公開Releaseに含まれるとは仮定しないでください。

利用可否とGate別の未検証範囲は [機能の状態表](../references/capability-status.md) を参照してください。
