# UnityAgent

[![Unity](https://img.shields.io/badge/Unity-2022.3%2B-000000?logo=unity&logoColor=white)](https://unity.com/)
[![Codex](https://img.shields.io/badge/Codex-Plugin-111827?logo=openai&logoColor=white)](https://github.com/openai/codex)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**UnityAgent は、Unity 開発の要求を方針・承認・Capability・Provider・Evidenceに沿って実行する Control Plane です。** Unity Editor、Codex Plugin、CLIを別々の実行主体にせず、入口をUnityAgentへ集約します。

[Architecture](docs/architecture/architecture.md) · [Production Tool Runtime](docs/architecture/production-tool-runtime.md) · [Context Explorer](https://darumappap.github.io/UnityAgent/) · [Releases](https://github.com/DarumaPPAP/UnityAgent/releases)

## 責務

ユーザー、Codex Plugin、Unity UIはUnityAgentへ要求を渡します。UnityAgentがTaskの分解、Policy、Approval、環境とProjectの確認、Capability解決、Provider実行、結果のEvidence化を管理します。

| 層 | 主な責務 |
|---|---|
| Entry | Unity UI / Codex Pluginから要求を受け付ける |
| Control Plane | Task、Policy、Approval、環境、Project Binding、実行状態を管理する |
| Capability & Orchestration | 要求をCapabilityへ対応付け、必要な処理順序を決める。専門作業ではoptional SubAgentを適格性条件で解決してから、Backend Providerを解決する |
| Provider | 許可された具体的な操作を実行する |
| Evidence & State | 観測結果、実行状態、履歴を保存する |

Entryや専門Backendが独自にPolicyやControl Planeを持つ構成にはしません。Unity UI / Codex PluginからProviderを直接呼び出しません。

## UnitySubAgentHub との境界

[UnitySubAgentHub](https://github.com/DarumaPPAP/UnitySubAgentHub) は、Optionalな専門SubAgentのRegistry、Manifest、Schema、Validationを管理する別Repositoryです。要求の解釈、適格性判定、Resolution、実行、Install、Retry/Fallback、Evidence正規化はUnityAgentの責務です。

- 専門AgentのIDは **`artist_subagent`**。
- その実装BackendのIDは **`unity_artist_cli`**。
- Registryへの登録だけでは、導入済み・互換・ProjectへBinding済み・実行可能とは判断しません。
- SubAgentの自動Installは行いません。falseまたはunknownのeligibility gateは候補から除外します。

### 現在のHub連携状態

2026-09-18時点で、HubのCIはManifestからSnapshot Artifactを生成しますが、UnityAgentはそのArtifactを自動取得・読込していません。UnityAgent ReferenceImplementationは、Repository内の`Runtime/ReferenceImplementation/subagent-catalog.yaml`を`SubAgentProfileCatalog`で読み込みます。このLoaderが読むのはUnityAgent独自のProfile形式です。HubのSnapshot形式を直接読み込むAdapterやImport処理はまだありません。

ローカルProfileの専門Agent IDは`artist_subagent`、実行Backend IDは`unity_artist_cli`です。Activationでは`available`、`compatible`、`project_bound`、`package_installed`、`pipeline_reachable`の各環境事実がすべてtrueであることを要求します。`compatible`はArtist CLIのsupport metadataから観測し、primary tierとrender pipelineに対応するknown backendの組み合わせが確認できた場合だけtrue、明示的な非対応はfalse、情報不足はunknownとして扱います。falseまたはunknownのProfileはResolution前に除外します。Hubへの登録だけでUnityAgentが実行を開始することはありません。

## Provider model

`Capability`は実現したいこと、`Provider`は操作を実行する実体です。Provider名だけで機能を選ばず、現在のProject・環境・Policy・Evidence条件を満たす候補をUnityAgentが解決します。

代表的なProviderにはFile、Native Unity Editor、Official Unity CLI、`unity_artist_cli` Backend、Installer、Player Runtimeがあります。これはProvider種別の一覧であり、すべてのProjectやReleaseで常に利用可能という意味ではありません。Artist Backendが扱える広いCLI surfaceと、Resolverに登録されたCapabilityも区別します。

## 安全性と完了判定

変更系処理は原則として次の順序で進めます。

```text
Inspect → Plan / Exact Scope → Approval → Apply → Evidence
```

Approvalは対象、Scope、Revisionに結び付けます。未観測の結果を成功として扱いません。

```text
Compile PASS
!= Editor PASS
!= Player PASS
!= Target Device PASS
!= Performance PASS
!= Visual PASS
```

Providerが使えないときは、制約を弱めたり別Backendへ無条件に切り替えたりせず、`unavailable`または環境阻害として報告します。

## Install

### Requirements

- Windows PowerShell 5.1以上（Windows Bootstrapを使う場合）
- Python 3.10以上（Control Planeのローカル導入に使用）
- Unity 2022.3以上（Unity Packageを利用する場合）
- Codex CLI（Codex Pluginを利用する場合）

Unity EditorでPackage Managerを開き、Git URLからUnityAgent UPM Packageを追加します。

```text
https://github.com/DarumaPPAP/UnityAgent.git?path=/Packages/com.darumappap.unity-agent#v0.0.7-beta
```

追加後、`UnityAgent > Setup`を開いてControl PlaneとCodex CLIの状態を確認します。Setup画面からControl Planeの導入、検出、Codex Pluginの導入・修復を行えます。

PowerShellからControl Planeだけを導入する場合:

```powershell
irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/main/scripts/install.ps1 | iex
```

このBootstrapはRelease artifactをSHA-256検証してControl Planeを導入します。詳細なSetup Plan、Approval、Repair手順は[Setup Guide](.agents/plugins/unity-agent/skills/unity-agent-setup/SKILL.md)を参照してください。

Codex Pluginを手動で追加する場合:

```powershell
codex plugin marketplace add DarumaPPAP/UnityAgent --ref v0.0.7-beta --json
codex plugin add unity-agent@unity-agent --json
```

Pluginを追加した後は、新しいCodex Threadで開始してください。Unity UIとCodex Pluginは同じUnityAgent Control Planeを入口として使用します。

## Local reference data

UnityAgentのLocal Reference Navigatorは、取得済みのReference Snapshotをローカル検索する仕組みです。通常の質問で外部Driveや検索サービスへ常時接続したり、ベクトルDBへ同期したりする機能ではありません。詳細は[Local Reference Navigator](docs/architecture/local-reference-navigator.md)を参照してください。

## Quickstart

Unity Project Rootを明示してEnvironmentを確認し、まず変更を伴わないSetup Planを生成します。

```powershell
$Project = "D:\Projects\MyGame"
unity-agent doctor --project-path "$Project" --format json --non-interactive
unity-agent setup --operation plan --project-path "$Project" --format json --non-interactive
```

Setup PlanのApplyは別操作です。承認済みPlanとApproval Referenceを指定し、Planで示されたScopeだけを適用します。

## Validation

Repositoryの基本検証:

```powershell
python .\Tools\validate_all.py
python .\Tools\SkillValidator\validate_skills.py --strict
python .\Tools\ProductionToolRuntime\validate_production_tool_runtime.py
python .\Tools\run_regression_gate.py
```

Local Regression Gateの一部は、ローカルCodex CLIや認証済み環境を必要とします。GitHub-hosted Release Workflowの検証結果と混同しないでください。

## Canonical sources

| 内容 | Source |
|---|---|
| Layer境界 | `Specs/unityagent-layer-contract.yaml` |
| PolicyとApproval | `Policy/` |
| RoutingとOrchestration | `Orchestration/` |
| Runtime / Provider Registry / Resolution | `Runtime/` |
| Durable Evidence | `Persistence/` |
| Regression / Eval | `Eval/` |
| Optional SubAgent metadata | [UnitySubAgentHub](https://github.com/DarumaPPAP/UnitySubAgentHub) |

詳細は[Architecture](docs/architecture/architecture.md)と[Production Tool Runtime](docs/architecture/production-tool-runtime.md)を参照してください。

## Status and license

UnityAgentはBetaです。Release Workflowは`main/VERSION`からcanonical tagを生成し、UPM Package、Codex Plugin、Python wheel / source distribution、`SHA256SUMS.txt`を公開します。手動入力したTagをRelease Source of Truthにはしません。UnityAgentは[MIT License](LICENSE)で提供されます。
