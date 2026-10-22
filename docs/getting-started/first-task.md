# 最初のTask：診断とSetup Plan

最初はProjectを変更しない診断から始めます。[導入ガイド](installation.md) に従ってControl Planeを導入し、実行するHostと対象Projectを確認してください。DoctorとPlanは診断・計画のStateやEvidenceを保存するため、ファイル書込が一切ない操作ではありません。

## 公開v0.0.8-betaを使う

`Assets/`、`Packages/manifest.json`、`ProjectSettings/ProjectVersion.txt` を持つUnity ProjectのRootを明示します。

```powershell
$Project = "D:\Projects\MyGame"
unity-agent doctor --project-path "$Project" --format json --non-interactive
unity-agent setup --operation plan --project-path "$Project" --format json --non-interactive
```

公開TagのCLIは `unity-agent` と `--project-path` が必要です。CWD検出、`uagent`、位置引数の `setup plan` はこのReleaseへ逆適用しません。

## DevelopmentのCLIを使う

以下はCommit `95ec7214697c9c4690ea72a4949a0c90fd928a9b` の構文です。

```powershell
Set-Location "D:\Projects\MyGame"
uagent doctor --format json --non-interactive
uagent setup plan --format json --non-interactive
```

CWDから親方向へ最も近いUnity Projectを検出します。子フォルダ全体の探索や、別の接続中Editorへの切替は行いません。別Projectは `--project-p "$Project"` で指定します。旧 `unity-agent`、`--project-path`、`setup --operation plan` は互換利用できますが、両Projectフラグの同時指定はエラーです。

## 結果を確認する

1. 解決されたProjectとControl Planeの応答を確認する。終了コード非0や `blocked` を成功扱いしない。
2. Doctorでは製品ごとの `installed` / `verified` / `unavailable` / `stale` と理由を確認する。操作全体の `completed` や終了コード0は、全製品が使えるという意味ではない。
3. Setup Planの対象製品、Action、Scope、`plan_id` を確認する。Plan生成はInstallではない。
4. 応答のRun・Evidence参照と対象Revisionを保持する。診断EvidenceはCompile・Editor・Player等のPASSを証明しない。

既定の診断対象はOfficial Unity CLIとArtist Backendです。Codex Pluginの確認は同じコマンドに `--product unity_agent_codex_plugin` を指定します。任意Backendが未導入でも、独立したCapabilityまで利用不可とは判断しません。

## 変更へ進むとき

Planを適用する場合は、完全なPlanを保存し、そのPlan ID・対象Project・Scopeを確認して承認を得ます。既存の `--approved-plan`、`--expected-plan-id`、`--approval-ref` を用いるApply手順は [Setup Skill](../../.agents/plugins/unity-agent/skills/unity-agent-setup/SKILL.md) に従います。古いPlanを再構築して承認を流用しません。

Scene・Asset変更や固定E2Eには、それぞれの前提と承認が必要です。[固定E2E手順](../architecture/full-e2e-capability.md) は独立した検証であり、最初の診断Taskには含みません。

## うまく進まない場合

| 状況 | 確認先・次の操作 |
|---|---|
| `uagent` が見つからない | Releaseなら `unity-agent` を使用。DevelopmentならvenvとHost導入元を確認 |
| Projectが見つからない | Rootの3条件、明示パス、DevelopmentのCWDを確認 |
| ツールが `unavailable` / `stale` | 理由、検出パス、導入元、Project bindingを確認。自動導入とは扱わない |
| Planや承認の不一致 | 最新の対象・Revisionで計画を作り直し、承認を再確認 |
| `READY` なのに検証が未完了 | READYの意味と各Gateを確認。実行ファイル検出と実Editor成功は別 |

[既存Setupガイド](../development/unityagent-setup-unity-verification.md)、[SubAgentの利用条件](../guides/subagents.md)、[機能の状態表](../references/capability-status.md) へ進めます。
