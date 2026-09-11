# UnityAgent

[![Unity](https://img.shields.io/badge/Unity-2022.3%2B-000000?logo=unity&logoColor=white)](https://unity.com/)
[![Codex](https://img.shields.io/badge/Codex-Plugin-111827?logo=openai&logoColor=white)](https://github.com/openai/codex)
[![Release](https://img.shields.io/badge/Release-v0.0.6--beta-orange)](https://github.com/DarumaPPAP/UnityAgent/releases)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![UnityAgent CI](https://github.com/DarumaPPAP/UnityAgent/actions/workflows/validate-agent-contracts.yml/badge.svg)](https://github.com/DarumaPPAP/UnityAgent/actions/workflows/validate-agent-contracts.yml)

**AIにUnity開発を任せるためのControl Plane。**  
Unityの設計・実装・検証を、Policy / Capability / Provider / Evidenceに分離して安全に回します。

> **Current source version:** `v0.0.6-beta`  
> Betaでは破壊的変更が入る可能性があります。

[Architecture Explorer](https://darumappap.github.io/UnityAgent/) · [Releases](https://github.com/DarumaPPAP/UnityAgent/releases) · [Architecture](docs/architecture/architecture.md) · [MIT License](LICENSE)

---

## What is UnityAgent?

UnityAgentは単なるUnity操作CLIではありません。

ユーザーやCodexから受けた要求に対して、**何をするか / どこまで変更してよいか / どのProviderへ実行させるか / 何をEvidenceとして残すか**を管理するUnity開発Control Planeです。

```text
User / Codex / Unity UI
          │
          ▼
      UnityAgent
 Architect / Commander
     Loop Owner
          │
          ▼
 Capability / Policy / Approval
          │
          ▼
       Providers
   ├─ Official Unity CLI
   ├─ UnityArtistCLI
   └─ Future Providers
          │
          ▼
   Evidence / Run State
```

- **One Control Plane** — Unity EditorとCodexで別の実行基盤を持たない。
- **Capability-first** — Provider名ではなく「何を実現したいか」を正本にする。
- **Approval-gated mutation** — 変更系処理はPlan / Scope / Approvalを通す。
- **Evidence-first** — 観測できていない結果をPASSとして扱わない。
- **Provider isolation** — UnityAgent Coreへ専門機能を詰め込まずProviderへ分離する。

---

# Installation

## Requirements

- Windows PowerShell 5.1+
- Python 3.10+
- Unity 2022.3+
- Codex Pluginを利用する場合はCodex CLI

## Recommended: Unity-first setup

### 1. Add the UnityAgent UPM package

Unity Editor:

1. `Window > Package Manager`
2. `+`
3. `Add package from git URL...`
4. 次を入力

```text
https://github.com/DarumaPPAP/UnityAgent.git?path=/Packages/com.darumappap.unity-agent#v0.0.6-beta
```

> `v0.0.2-beta` のUPM artifactにはUnity `.meta` 不足があるため使用しないでください。`v0.0.6-beta` ではBootstrap/UIを含む現在のSetup導線を使用できます。

### 2. Open UnityAgent Setup

```text
UnityAgent > Setup
```

`v0.0.6-beta` ではSetup Windowを、依存関係と次の操作が一目で分かるカード型UIへ再設計しています。

```text
UnityAgent Setup                                  v0.0.6-beta

Setup Readiness                                  1/2 READY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. UnityAgent Control Plane              ACTION REQUIRED
Resolved Path: Not Found
[ Install Control Plane ]
[ 再検出 ] [ 参照... ]

2. Codex CLI                                      READY
Resolved Path: C:\...\codex.exe
[ 再検出 ] [ 参照... ]

3. Codex Integration                      READY TO CHECK
[ 状態を確認 ] [ Codex Pluginをインストール / 修復 ]

Current Status
Diagnostics / Raw response
Advanced
```

### 3. Install the Control Plane from Unity

Control Planeがまだ無い場合は、Setup WindowのPrimary actionを使用します。

```text
Install Control Plane
```

Bootstrapは**Control Plane自身だけ**を導入します。

```text
UnityAgent UPM
  ↓ bootstrap-only path
Package-local PowerShell installer
  ↓
GitHub Release wheel + SHA256SUMS.txt
  ↓ SHA-256 verify
pip --user
  ↓
unity-agent.exe
  ↓
UNITY_AGENT_CONTROL_PLANE
```

BootstrapからCodex PluginやUnityArtistCLI等のProviderを直接変更することは禁止しています。Control Plane導入後の通常処理は従来どおりです。

```text
Unity Window
  ↓
UnityAgent Control Plane
  ↓
Setup Plan / Approval
  ↓
Installer Provider
  ↓
Provider / Codex CLI
  ↓
InstallReceipt / Evidence
```

### 4. Detect Codex CLI and install the Codex Plugin

Control PlaneがReadyになったら、Codex CLIを確認します。

Codex CLIは概ね次の順で解決します。

```text
Manual Override
  ↓
UNITY_AGENT_CODEX_CLI / CODEX_CLI
  ↓
Windows npm / common locations
  ↓
NVM / user-local locations
  ↓
PATH / where.exe / which
  ↓
Installer Providerで codex --version を実行確認
```

その後、

```text
Codex Pluginをインストール / 修復
```

を実行します。Plugin導入後はCodexで**新しいThread**を開始してください。

---

## Alternative: PowerShell / Headless install

Unity Editorを使わずControl Planeを入れる場合、またはRepair用途では従来のBootstrapも利用できます。

```powershell
irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/main/scripts/install.ps1 | iex
```

既定では最新の公開UnityAgent Prereleaseを解決し、Release wheelを `SHA256SUMS.txt` で検証してからインストールします。

特定Releaseを固定する場合:

```powershell
$env:UNITY_AGENT_TAG = "v0.0.6-beta"
irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/main/scripts/install.ps1 | iex
```

Installerは導入した `unity-agent.exe` の絶対PathをUser環境変数 `UNITY_AGENT_CONTROL_PLANE` に保存します。

---

# Manual Codex installation

Unity Editorを使わず手動で導入する場合:

```powershell
codex plugin marketplace add DarumaPPAP/UnityAgent --ref v0.0.6-beta --json
codex plugin add unity-agent@unity-agent --json
codex plugin list --json
```

```text
Marketplace : unity-agent
Plugin      : unity-agent@unity-agent
```

旧Betaで使用していた汎用的な `personal` Marketplace名には依存しません。

---

# Troubleshooting

## Control Planeが見つからない

Setup WindowのControl Planeカードから順に確認してください。

```text
Install Control Plane
→ 再検出
→ 参照...
→ Override解除
→ Diagnostics
```

Control Plane Resolverは概ね次の順で探索します。

```text
Manual Override
  ↓
UNITY_AGENT_CONTROL_PLANE
  ↓
User environment
  ↓
Python User Scripts
  ↓
Process PATH / User PATH
```

## Codex CLIが見つからない

```text
再検出
→ 参照...
→ Override解除
→ Diagnostics
```

Windowsでは `codex.exe / codex.cmd / codex.bat / codex.ps1` を考慮します。

---

# Quickstart

Unity Project Rootは `Assets / Packages / ProjectSettings` を含むディレクトリです。

```powershell
$Project = "D:\Projects\MyGame"
```

Environment確認:

```powershell
unity-agent doctor `
  --project-path "$Project" `
  --format json `
  --non-interactive
```

Setup Plan:

```powershell
unity-agent setup `
  --operation plan `
  --project-path "$Project" `
  --format json `
  --non-interactive
```

Codex CLIを明示する場合:

```powershell
unity-agent setup `
  --operation doctor `
  --project-path "$Project" `
  --product codex_cli `
  --codex-path "C:\Path\To\codex.exe" `
  --format json `
  --non-interactive
```

`unavailable` は必ずしもUnityAgent自体の異常ではありません。未観測・利用不可の結果を勝手にPASSへ変換しません。

---

# What UnityAgent does

| Area | UnityAgentの役割 |
| --- | --- |
| Architecture | Taskの責務・境界・依存方向を決める |
| Routing | IntentをCapabilityへ変換する |
| Policy | Mutation Scope / Approval / Safetyを適用する |
| Runtime | Provider Registry / Resolver / Dispatcherを統括する |
| Unity operations | Official Unity CLI等へ実行を委譲する |
| Visual / Cinematic | UnityArtistCLIへ専門処理を委譲する |
| Toolchain Setup | Installer ProviderでCodex Plugin等を観測・導入する |
| Evidence | ProviderResultを正規化し、実行結果を永続化する |
| Regression | Frozen BaselineとのBehavior比較を行う |

---

# Provider model

```text
Skill      = どう作業するか
Capability = 何を実現したいか
Provider   = 誰が実行するか
Evidence   = 実際に何を観測したか
```

代表Provider:

- File Provider
- Native Unity Editor Provider
- Official Unity CLI Provider
- UnityArtistCLI Provider
- Player Runtime Provider
- Installer Provider

UnityArtistCLIはLookDev / Lighting / Camera / Cinematic等を担当するspecialist Providerです。第二のAgent Frameworkにはしません。

`v0.0.6-beta` のUnityAgentはUnityArtistCLI `v0.0.1-beta` をimmutable dependencyとしてpinしています。UnityAgentのRelease channelとProvider製品versionは別契約です。

---

# Safety & Evidence

```text
Compile PASS
!= Editor PASS
!= Player PASS
!= Target Device PASS
!= Performance PASS
!= Visual PASS
```

```text
Provider unavailable
!= Approvalを省略してよい
!= Mutation Scopeを広げてよい
!= Evidenceを推測してよい
```

通常Mutationは原則として次の経路を維持します。

```text
Inspect
  ↓
Prepare / Plan
  ↓
Exact Diff / Scope
  ↓
Expected Revision
  ↓
Approval
  ↓
Apply
  ↓
Evidence
```

Control Plane未導入時の**Control Plane自身のBootstrapだけ**が、この通常経路の前段にある限定例外です。

---

# Architecture

```text
① Entry Layer
   Unity UI / Codex Plugin

② Control Plane
   UnityAgent

③ Capability & Orchestration Layer
   Graph / Loop / Runtime Guard / Policy / Approval
   Provider Registry / Resolver / Dispatcher

④ Provider Layer
   Official Unity CLI / UnityArtistCLI / Installer / Future Providers

⑤ Evidence & State Layer
   ProviderResult / Run History / Capture / InstallReceipt / Evaluation
```

> **Unity UI / Codex PluginからProviderへ直接接続しない。**

詳細:

- [Architecture](docs/architecture/architecture.md)
- [Production Tool Runtime](docs/architecture/production-tool-runtime.md)
- [Unity Environment Adaptation](docs/unity-environment-adaptation.md)
- [Local Unity Project Development](docs/local-project-development.md)
- [Layer Contract](Specs/unityagent-layer-contract.yaml)
- [Architecture Explorer](https://darumappap.github.io/UnityAgent/)

---

# Development & Validation

```powershell
python .\Tools\validate_all.py
python .\Tools\SkillValidator\validate_skills.py --strict
python .\Tools\ProductionToolRuntime\validate_production_tool_runtime.py
python .\Tools\run_regression_gate.py
```

Local Regression GateはローカルのCodex CLI / 認証済み環境を前提とし、GitHub-hosted Release Workflowの必須Gateとは分離されています。

---

# Release

Canonical version:

```text
0.0.6-beta
```

Release Workflowは**tag文字列を手入力しません**。`main/VERSION`からcanonical tag `v0.0.6-beta` を自動生成します。

Actionsでは:

```text
UnityAgent Release
→ Run workflow from main
→ confirm_release = true
```

だけを指定します。旧versionのコピペや先頭`v`忘れでReleaseが落ちる経路を排除しています。

Release Workflowは同一tagから以下を生成します。

- UnityAgent UPM package
- Codex `unity-agent` plugin archive
- Python Control Plane wheel / source distribution
- `SHA256SUMS.txt`

UPM artifactはRelease前に、Editor assetsの`.meta`とpackage-local Bootstrap scriptがpack後の`.tgz`へ含まれていることを検証します。

---

# License

UnityAgent is released under the [MIT License](LICENSE).

---

# Project status

UnityAgentは現在Betaです。

目標は、Unity Editor、Codex、Official Unity CLI、UnityArtistCLIなどの入口や実行手段が増えても、**UnityAgentのControl Plane / Graph / Loop / Evidence契約を作り直さず拡張できる構成**を維持することです。

Bug / Proposal / Beta feedbackはGitHub Issuesへお願いします。
