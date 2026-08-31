# UnityAgent Development Request

このTemplateは、UnityAgentへローカルUnity開発を依頼するときの標準入力です。

全部を埋める必要はありません。Projectから検出できるFactは空欄でも構いません。

ただし、**Goal / Project Root / Mutation Scope / 完了条件**は可能な限り明示してください。

---

## 1. Goal

何を作る、直す、調査する、改善するのかを記載します。

```text
Goal:

```

例:

```text
MainCamera移動時に発生するFrame spikeの原因を特定し、Switch向けに改善する。
```

---

## 2. Target Unity Project

```text
Project Root:
D:\Projects\MyGame\Project
```

原則、`Assets/`ではなくUnity Project Rootを指定します。

```text
Project/
├─ Assets/
├─ Packages/
└─ ProjectSettings/
```

UnityAgent本体をTarget Projectの`Assets/`配下へコピーしません。

---

## 3. Development Mode

必要なものへチェックします。

- [ ] 調査のみ
- [ ] 設計のみ
- [ ] 設計 + 実装
- [ ] C#局所修正
- [ ] Rendering / Shader
- [ ] Performance調査
- [ ] Editor Tool
- [ ] Portable Package
- [ ] MCP / Tool Runtime
- [ ] Player / Target Device Verification
- [ ] その他

---

## 4. Read Scope

標準:

```text
Read Scope:
Project Root全体
```

Project Fact確認のため、必要に応じて次を読み取って構いません。

- `Assets/`
- `Packages/`
- `ProjectSettings/`
- asmdef
- package manifest / lock
- Unity Version
- Render Pipeline設定
- Build / Quality設定

読み取り許可はMutation許可ではありません。

---

## 5. Mutation Scope

変更を許可する範囲を記載します。

```text
Mutation Scope:
Assets/<対象Directory>/**
```

例:

```text
Mutation Scope:
Assets/Rendering/GPUCulling/**
Assets/Shaders/GPUCulling/**
```

必要になるまで、次はMutation Scopeへ含めないことを推奨します。

- `Packages/`
- `ProjectSettings/`
- 他FeatureのDirectory

Mutation Scope外へ変更が必要な場合:

```text
勝手に変更せず、必要理由・変更先・影響・代替案を先に提示する。
```

---

## 6. Known Project Conditions

分かっている範囲だけ記載します。

```text
Unity Version:

Render Pipeline:

Target Platform:

Target Device:

Performance Target:

Namespace:

Relevant Packages:

Relevant Existing Systems:

Do Not Change:
```

未記入項目は、実Projectから取得できる場合はProject Factを使用します。

推測で固定しません。

---

## 7. User Constraints

ユーザー固有の優先事項、禁止事項、品質条件を記載します。

```text
Constraints:
- 
- 
- 
```

例:

```text
- Switchを最優先する
- staticを不要に増やさない
- 新Managerを追加する前にExisting Ownerで解決できないか確認する
- ProjectSettingsを変更する場合は先にDesign Reviewへ戻す
```

---

## 8. Required Capability

Tool製品名ではなく、必要な能力を記載できます。

未記入でもGoalから選択可能です。

例:

```text
Required Capability:
- project.inspect
- source.inspect
- scene.inspect
- scene.mutate
- project.compile
- project.test
- project.build
- editor.capture
- performance.capture
- player.observe
```

重要:

```text
Capability != Provider
```

`scene.inspect`が必要だからといって、依頼側で必ずMyUnityMCPやUnity CLIへ固定する必要はありません。

Provider選択は、現在利用可能なRuntime実装、Policy、Approval、接続状態、Project identity、安全Contractに従います。

---

## 9. Provider Preference

通常は空欄で構いません。

特定Providerを使う理由がある場合だけ指定します。

```text
Provider Preference:

```

例:

```text
Provider Preference:
MyUnityMCPで取得可能なGraphics inspectionはMyUnityMCPを優先する。
```

ただしProvider PreferenceはPolicy / Safety Contractを上書きしません。

---

## 10. Provider Fallback Rule

標準Rule:

```text
Provider unavailableを理由に、より弱いSafety Contractへ自動Fallbackしない。
```

特に、承認付きMyUnityMCP Mutationが必要なTaskで、接続失敗を理由にraw `eval`へ切り替えません。

必要なら:

- reconnect
- replan
-別Providerの同等Safety Contract確認
- Human Review
- BLOCK / INCONCLUSIVE

を選択します。

---

## 11. Design Review

設計変更を伴う場合に指定します。

```text
Design Review:
required / conditional / not_required
```

`required`の場合、実装前に最低限次を提示します。

### Mermaid関連図

- Existing System
- New / Modified Component
- Capability
- Runtime boundary
- Provider boundary
- Validation / Evidence

### Design Check

- Goal一致
- Existing Owner
- Responsibility
- Source of Truth
- Read Scope
- Mutation Scope
- Capability requirement
- Provider候補
- Approval boundary
- Performance
- Platform依存
- Validation
- Non-goal

### 最終イメージ仕様書

- Summary
- User-visible behavior
- Major components
- Data / Control Flow
- Expected files
- Acceptance Criteria
- Non-goal
- Unresolved

Design Reviewが必須の場合はApprove前にImplementation Mutationへ進みません。

---

## 12. Required Verification

必要な検証を指定します。

```text
Verification:
- Static Review
- Compile
- EditMode Test
- PlayMode Test
- Direct Editor Validation
- Player Validation
- Target Device Validation
- Performance Capture
- Visual Capture
```

すべて必要とは限りません。

ただし、実行していない検証をPASS扱いしません。

```text
Compile PASS
!= Runtime PASS
!= Player PASS
!= Target Device PASS
```

---

## 13. Live Editor Rule

必要に応じて使用します。

標準:

```text
live Editorへ安全な構造化接続が可能な場合、Scene / Prefab / Assetのraw YAML直接編集よりEditor経由を優先する。
```

ただし:

```text
Editor reachable
!= Mutation authorized
```

です。

---

## 14. Safe Mode Rule

C# compile errorによりPipeline / MCP等へ接続できない場合:

```text
1. Safe Modeか確認
2. Compiler Errorを必要最小限取得
3. 該当C# Sourceだけ修正
4. 対象Editorだけ再起動
5. Compile再確認
6. Tool connectionを復旧
```

接続失敗だけでraw file mutationへ移行しません。

---

## 15. Player / Runtime Rule

Player / Target Device検証が必要な場合:

```text
Player Requirement:

```

例:

```text
Player Requirement:
Switch実機でLOD stateとCamera Far ClipをRead-only観測したい。
```

Player Runtime commandはallowlist方式を基本とします。

例:

```text
observe.camera
observe.lod
observe.renderer
observe.memory
observe.frame
```

Runtime Mutation commandは別Approval対象です。

---

## 16. Evidence Requirement

```text
Evidence:
- 
- 
```

例:

```text
- Unity compile error 0
- 対象Sceneのbefore / after
- Profiler capture
- Switch実機Frame Time
```

Evidenceは観測Sourceを区別します。

```text
static_analysis
compile
editor_validation
player_validation
target_device_validation
performance_capture
visual_capture
```

---

## 17. Required

必須要求:

```text
Required:
- 
- 
- 
```

---

## 18. Optional

できれば欲しいが、完了条件にはしない項目:

```text
Optional:
- 
- 
```

---

## 19. Non-goal

今回やらないことを明記します。

```text
Non-goal:
- 
- 
```

Scope creep防止に重要です。

---

## 20. Acceptance Criteria

Task完了条件を具体化します。

```text
Acceptance Criteria:
- 
- 
- 
```

例:

```text
- BGMが意図しないClipへ戻らない
- 新規Managerを追加していない
- Compile Error 0
- 既存の2 BGM同時再生仕様を壊していない
```

---

## 21. Completion Report

完了時には最低限次を報告します。

- Root cause / 実装内容
- 変更File
- Mutation Scope逸脱の有無
- Provider / Toolを使った場合の実行経路
- 実施したVerification
- Evidence
- 未観測項目
- Known limitation
- 次に必要なHuman action

---

# 完全版入力例

```text
UnityAgentで以下を設計・実装してください。

Project Root:
D:\Projects\MyGame\Project

Goal:
Unity 6 URP RenderGraph向けにGPU Culling Featureを追加する。

Development Mode:
設計 + 実装

Read Scope:
Project Root全体

Mutation Scope:
Assets/Rendering/GPUCulling/**
Assets/Shaders/GPUCulling/**

Known Conditions:
- Switch最優先
- URP
- SRP Batcher ON

Constraints:
- staticを不要に増やさない
- ProjectSettings変更は事前Review
- Existing Ownerを優先

Required Capability:
- project.inspect
- scene.inspect
- source.inspect
- project.compile
- editor.capture
- performance.capture

Design Review:
required

Verification:
- Static Review
- Compile
- Direct Editor Validation
- Performance Capture

Acceptance Criteria:
- 対象RendererのCPU Culling Costを観測可能
- Compile Error 0
- 既存Renderingを破壊しない
- 未実施のSwitch実機検証は未観測として報告する
```

---

# 最小依頼版

普段は次だけでも開始できます。

```text
UnityAgentで以下を開発してください。

Project Root:
D:\Projects\MyGame\Project

Goal:
<やりたいこと>

Read Scope:
Project Root全体

Mutation Scope:
Assets/<対象>/**

Project Factは実Projectから取得してください。
必要CapabilityはGoalから選択してください。
Providerは固定せず、安全Contractと利用可能状態から選択してください。

指定外Mutationが必要なら理由を先に説明してください。
設計変更を伴う場合はDesign Reviewを先に行ってください。
未観測のVerificationをPASS扱いしないでください。
```

---

# Target Architectureについて

`Specs/UnityToolRuntime.md`に定義されるCapability-driven Tool RuntimeはTarget Architectureです。

Runtime Tool Broker / Provider Registry等がProduction実装へ昇格する前は、既存のRuntime / MCP / Harness契約を使用します。

このTemplateはTarget Architectureの語彙を先行して使えますが、存在しないProviderを実装済みとして要求しません。