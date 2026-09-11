# UnityAgent

[![Unity](https://img.shields.io/badge/Unity-2022.3%2B-000000?logo=unity&logoColor=white)](https://unity.com/)
[![Codex](https://img.shields.io/badge/Codex-Plugin-111827?logo=openai&logoColor=white)](https://github.com/openai/codex)
[![Release](https://img.shields.io/badge/Release-v0.0.2--beta-orange)](https://github.com/DarumaPPAP/UnityAgent/releases)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![UnityAgent CI](https://github.com/DarumaPPAP/UnityAgent/actions/workflows/validate-agent-contracts.yml/badge.svg)](https://github.com/DarumaPPAP/UnityAgent/actions/workflows/validate-agent-contracts.yml)

**AIにUnity開発を任せるためのControl Plane。**  
Unityの設計・実装・検証を、Policy / Capability / Provider / Evidenceに分離して安全に回します。

> **Current source version:** `v0.0.2-beta`  
> Betaでは破壊的変更が入る可能性があります。

[Architecture Explorer](https://darumappap.github.io/UnityAgent/) · [Releases](https://github.com/DarumaPPAP/UnityAgent/releases) · [Architecture](docs/architecture/architecture.md) · [MIT License](LICENSE)

---

## What is UnityAgent?

UnityAgentは単なる「Unity操作CLI」ではありません。

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

UnityAgentは次の原則で構成されています。

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

## Recommended setup

### 1. Install UnityAgent Control Plane

PowerShell:

```powershell
irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/main/scripts/install.ps1 | iex
```

このBootstrap URLは常に `main/scripts/install.ps1` を使用します。既定では**最新の公開UnityAgent Prerelease**を解決し、ReleaseのPython wheelを `SHA256SUMS.txt` で検証してからインストールします。

特定Releaseを固定したい場合:

```powershell
$env:UNITY_AGENT_TAG = "v0.0.2-beta"
irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/main/scripts/install.ps1 | iex
```

確認:

```powershell
unity-agent --help
```

### 2. Add the UnityAgent UPM package

Unity Editor:

1. `Window > Package Manager`
2. `+`
3. `Add package from git URL...`
4. 次を入力

```text
https://github.com/DarumaPPAP/UnityAgent.git?path=/Packages/com.darumappap.unity-agent#v0.0.2-beta
```

### 3. Open UnityAgent Setup

```text
UnityAgent > Setup
```

### 4. Install / Repair the Codex Plugin from Unity

```text
UnityAgent Setup

Codex Integration
├─ Codex Pluginを確認
└─ Codex Pluginをインストール / 修復   ← Recommended
```

Unity WindowはCodex CLIを直接Mutationしません。

```text
Unity Window
  ↓
UnityAgent Control Plane
  ↓
Setup Plan / Approval
  ↓
Installer Provider
  ↓
Codex CLI
  ↓
UnityAgent Codex Plugin
  ↓
InstallReceipt / Evidence
```

インストール後はCodexで**新しいThread**を開始してPluginを読み直してください。

---

# Manual Codex installation

Unity Editorを使わず手動で導入する場合:

```powershell
codex plugin marketplace add DarumaPPAP/UnityAgent --ref v0.0.2-beta --json
codex plugin add unity-agent@unity-agent --json
codex plugin list --json
```

`v0.0.2-beta` からMarketplace IDは **`unity-agent`** 専用です。

```text
Marketplace : unity-agent
Plugin      : unity-agent@unity-agent
```

旧Betaで使用していた汎用的な `personal` Marketplace名には依存しません。

---

# Quickstart

Unity Project Rootは `Assets / Packages / ProjectSettings` を含むディレクトリです。

```powershell
$Project = "D:\Projects\MyGame"
```

Environmentを確認:

```powershell
unity-agent doctor `
  --project-path "$Project" `
  --format json `
  --non-interactive
```

Setup Planを作成:

```powershell
unity-agent setup `
  --operation plan `
  --project-path "$Project" `
  --format json `
  --non-interactive
```

`unavailable` は必ずしもUnityAgent自体の異常ではありません。UnityAgentは利用できないProviderや未観測の結果を、勝手に成功へ変換しません。

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

UnityArtistCLIはLookDev / Lighting / Camera / Cinematic等を担当するspecialist Providerです。UnityAgentのGraph / Loop / Policyを持つ第二のAgent Frameworkにはしません。

`v0.0.2-beta` のUnityAgentはUnityArtistCLI `v0.0.1-beta` をimmutable dependencyとしてpinしています。UnityAgentのRelease channelとProvider製品versionは別契約として扱います。

---

# Safety & Evidence

UnityAgentは「動いた気がする」を成功にしません。

```text
Compile PASS
!= Editor PASS
!= Player PASS
!= Target Device PASS
!= Performance PASS
!= Visual PASS
```

Providerが利用できない場合もSafety Contractを弱めません。

```text
Provider unavailable
!= Approvalを省略してよい
!= Mutation Scopeを広げてよい
!= Evidenceを推測してよい
```

Mutationは原則として次の経路を維持します。

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

---

# Architecture

UnityAgentの製品境界は5層です。

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

Repository全体:

```powershell
python .\Tools\validate_all.py
```

Skill authoring quality:

```powershell
python .\Tools\SkillValidator\validate_skills.py --strict
```

Production Tool Runtime:

```powershell
python .\Tools\ProductionToolRuntime\validate_production_tool_runtime.py
```

Local Regression Gate:

```powershell
python .\Tools\run_regression_gate.py
```

> Local Regression GateはローカルのCodex CLI / 認証済み環境を前提とします。GitHub-hosted Release Workflowの必須Gateとは分離されています。

---

# Release

Canonical version:

```text
0.0.2-beta
```

Release Workflowは同一tagから以下を生成します。

- UnityAgent UPM package
- Codex `unity-agent` plugin archive
- Python Control Plane wheel / source distribution
- `SHA256SUMS.txt`

Releaseはimmutable tagとして作成し、GitHubではPrereleaseとして公開します。

---

# License

UnityAgent is released under the [MIT License](LICENSE).

---

# Project status

UnityAgentは現在Betaです。

目標は、Unity Editor、Codex、Official Unity CLI、UnityArtistCLIなどの入口や実行手段が増えても、**UnityAgentのControl Plane / Graph / Loop / Evidence契約を作り直さず拡張できる構成**を維持することです。

Bug / Proposal / Beta feedbackはGitHub Issuesへお願いします。
