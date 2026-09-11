# UnityAgent

**AIにUnity開発を任せるためのControl Plane。**  
Unityの設計・実装・検証を、Policy / Capability / Provider / Evidenceに分離して安全に回します。

> **Status:** `v0.0.1-beta`  
> Betaでは破壊的変更が入る可能性があります。

[Architecture Explorer](https://darumappap.github.io/UnityAgent/) · [Latest Release](https://github.com/DarumaPPAP/UnityAgent/releases/latest) · [Architecture](docs/architecture/architecture.md)

---

## Concept

UnityAgentは「Unityを操作するCLI」そのものではありません。

ユーザーの依頼を受けて、**何をするか・どこまで変更してよいか・誰に実行させるか・何を証拠として残すか**を管理するAI開発Control Planeです。

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

UnityAgentは次の考え方を中心に設計しています。

1. **1つのControl Plane** — Codex PluginとUnity Editor UIで別実装を持たない。
2. **Capability-first** — `何をしたいか` を先に決め、実行ProviderはRuntimeが解決する。
3. **Approval-gated mutation** — 変更系処理はPlan / Scope / Approvalを通す。
4. **Evidence-first** — 観測できていない結果をPASSとして扱わない。
5. **Providerを増やしてもCoreを肥大化させない** — 実処理はProviderへ分離する。

---

# Installation

## Requirements

- Windows PowerShell 5.1 以上
- Python 3.10 以上
- Unity 2022.3 以上
- Codex Pluginを使う場合はCodex CLI

## Control Plane

```powershell
irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/main/scripts/install.ps1 | iex
```

このBootstrapは `main/scripts/install.ps1` から起動しますが、実際にインストールするControl Planeは公開済みGitHub Releaseを使用します。

現在の既定Releaseは `v0.0.1-beta` です。ReleaseのPython wheelを取得し、`SHA256SUMS.txt` と照合した後にインストールします。

```powershell
unity-agent --help
```

が成功すればControl Planeの導入は完了です。

### インストーラを確認してから実行する場合

```powershell
irm https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/main/scripts/install.ps1 -OutFile $env:TEMP\unityagent-install.ps1
notepad $env:TEMP\unityagent-install.ps1
& $env:TEMP\unityagent-install.ps1
```

---

# Quickstart

## Step 1 — Unity Projectを指定する

`Assets` フォルダではなく、`Assets / Packages / ProjectSettings` を含むUnity Project Rootを指定します。

```powershell
$Project = "D:\Projects\MyGame"
```

## Step 2 — Environmentを確認する

```powershell
unity-agent doctor `
  --project-path "$Project" `
  --format json `
  --non-interactive
```

`unavailable` が出ても、それだけでUnityAgent全体の異常とは限りません。
UnityAgentは利用できないProviderや未観測の結果を、勝手に成功へ変換しません。

## Step 3 — Setup Planを作る

```powershell
unity-agent setup `
  --operation plan `
  --project-path "$Project" `
  --format json `
  --non-interactive
```

Planには利用可能 / 不足Toolchain、`verify` / `install_then_verify`、`plan_id`、Approval要否が含まれます。

---

# Unity Editor integration

UnityAgentにはEntry Layer用のUPM Packageがあります。

## Via Unity Package Manager

公開Betaを使う場合、Unity Editorで:

1. `Window > Package Manager`
2. `+`
3. `Add package from git URL...`
4. 次を入力

```text
https://github.com/DarumaPPAP/UnityAgent.git?path=/Packages/com.darumappap.unity-agent#v0.0.1-beta
```

導入後:

```text
UnityAgent > Setup
```

からControl Planeへ接続できます。

Unity側のWindowはEntry Layerです。Official Unity CLI、UnityArtistCLI、Codex CLIへ直接Mutationを送らず、`unity-agent` Control Planeを通します。

### Recommended — Codex PluginはUnity Windowから導入

`main` ではUnityAgent Setup WindowからCodex Integrationを管理できます。

```text
UnityAgent > Setup

Codex Integration
├─ Codex Pluginを確認
└─ Codex Pluginをインストール / 修復   ← Recommended
```

Install / Repairは次の経路で実行します。

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

Unity Windowが `codex plugin ...` を直接実行するわけではありません。Planを表示し、ユーザー承認後に同じ `plan_id` をInstaller ProviderへApplyします。

> **Current Beta note:** 公開済み `v0.0.1-beta` のUPM artifactには、このワンクリックCodex Plugin導入UIはまだ含まれていません。現在は `main` に実装済みで、次BetaからこのUnity Window導線をPrimary installation pathにする予定です。`v0.0.1-beta` を使う場合は下のManual Codex integrationを使用してください。

---

# Codex integration

## Recommended

次Beta以降は **`UnityAgent > Setup > Codex Pluginをインストール / 修復`** を推奨します。

理由は、Marketplace / Plugin状態の観測、Plan、Approval、Apply、InstallReceiptをUnityAgent側で一貫して扱えるためです。

インストール後はCodexで**新しいThread**を開始してPluginを読み直してください。

## Manual — current `v0.0.1-beta`

Marketplaceを追加:

```powershell
codex plugin marketplace add DarumaPPAP/UnityAgent --ref v0.0.1-beta --json
```

Pluginを追加:

```powershell
codex plugin add unity-agent@personal --json
```

確認:

```powershell
codex plugin list --json
```

UnityAgentは既存の同名Marketplaceを勝手にretargetしません。`personal` が別Sourceに使われている場合はfail-closedで停止します。

UnityAgent PluginはProviderそのものではなく、Architecture / Routing / Approval / Evidence-backed executionの入口です。

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

UnityAgentはProvider製品名をGraphの正本にしません。

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

UnityArtistCLIはLookDev / Lighting / Camera / Cinematic等を担当するspecialist Providerです。
UnityAgentのGraph / Loop / Policyを持つ第二のAgent Frameworkにはしません。

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

Providerが利用できない場合も、Safety Contractを弱めません。

```text
Provider unavailable
!= Approvalを省略してよい
!= Mutation Scopeを広げてよい
!= Evidenceを推測してよい
```

Visual / Cinematic mutationでは次の流れを維持します。

```text
Inspect
  ↓
Prepare
  ↓
Exact Diff
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

重要なルール:

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

# Beta release

現在の公開Beta:

**[`v0.0.1-beta`](https://github.com/DarumaPPAP/UnityAgent/releases/tag/v0.0.1-beta)**

Releaseには以下を同一タグから生成して公開します。

- UnityAgent UPM package
- Codex Plugin archive
- Python Control Plane wheel / source distribution
- `SHA256SUMS.txt`

UnityArtistCLIもBetaでは固定Releaseへpinし、UnityAgent Releaseの再現性を維持します。

---

# Project status

UnityAgentは現在Betaです。

目標は、Unity Editor、Codex、Official Unity CLI、UnityArtistCLIなどの入口や実行手段が増えても、**UnityAgentのControl Plane / Graph / Loop / Evidence契約を作り直さず拡張できる構成**を維持することです。

Bug / Proposal / Beta feedbackはGitHub Issuesへお願いします。
