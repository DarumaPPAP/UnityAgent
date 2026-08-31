# Unity Tool Runtime Environment Adaptation

## 1. Goal

UnityAgentがUnity CLI、MyUnityMCP、Coplay MCP、Unity Editor、Player Runtimeの有無に依存せず、**その時点のUnity環境で実際に利用可能なCapabilityだけを安全に選択して実行できる**ことを定義します。

この文書は `Specs/UnityToolRuntime.md` を補強するDesign Contractです。

最重要原則:

```text
外部Providerは必須依存ではない。
Providerの有無はEnvironment Factである。
Capabilityごとに現在利用可能なProviderを解決する。
利用不能な検証を成功扱いしない。
Safety Contractを下げる自動Fallbackをしない。
```

## 2. なぜ必要か

Unity開発環境は常に同じではありません。

例えば次の状態はすべて正常な利用形態として扱います。

- Unity CLIあり + MyUnityMCPあり
- Unity CLIあり + MCPなし
- Unity CLIなし + MyUnityMCPあり
- Unity CLIなし + MCPなし + Unity Editorあり
- Unity CLIなし + MCPなし + Unity Editorも未起動
- Unity EditorはあるがSafe Mode
- Unity Editor自体が未インストール
- Player Runtimeへ接続できない
- Test Frameworkや対象Build Moduleが無い

これらを`failure`として一括処理せず、Environment SnapshotからCapability単位で実行可能性を解決します。

## 3. ProviderはOptional

UnityAgentのProduction Authorityは従来通りです。

```text
Policy defines
Orchestration decides
Context materializes
Runtime executes
Persistence remembers
Operations observes/controls
Eval measures/proposes
```

次はすべてOptional Providerです。

```text
Unity CLI
com.unity.pipeline
MyUnityMCP
Coplay MCP
Native Unity Editor CLI
Player Runtime Bridge
Git
```

File Providerのみも、Workspaceへread/write権限がある場合に利用可能なProviderとして扱います。

## 4. Environment Snapshot

RuntimeはTask開始時またはUnity Capabilityが必要になった時点で、環境を次のように観測します。

```yaml
environment:
  project_root: D:/Projects/MyGame/Project
  project_exists: true
  filesystem:
    readable: true
    writable_in_mutation_scope: true
  git:
    available: true
  unity_editor:
    installed: true
    version: 6000.3.12f1
    executable_path: C:/Program Files/Unity/Hub/Editor/6000.3.12f1/Editor/Unity.exe
    running: false
    safe_mode: false
  unity_cli:
    available: false
    version: null
  pipeline:
    installed: false
    reachable: false
  myunitymcp:
    available: false
    project_bound: false
  coplay_mcp:
    available: false
    project_bound: false
  test_framework:
    available: true
  build:
    requested_target_module_available: true
  player_runtime:
    reachable: false
```

Unknownを`false`へ潰しません。

```text
true
false
unknown
```

を区別します。

## 5. Environment Profileは説明用でありRouting Authorityではない

人間向けには代表Profileを表示できます。

| Profile | 状態 | 主な利用手段 |
| --- | --- | --- |
| `FULL` | CLI + MCP + Editor | Capabilityごとの最適Provider |
| `CLI_ONLY` | CLIあり、MCPなし | Unity CLI / Pipeline / File |
| `MCP_ONLY` | MCPあり、CLIなし | MyUnityMCP / Coplay MCP / File |
| `NATIVE_EDITOR` | CLI/MCPなし、Editorあり | Native Unity Editor CLI / File |
| `FILES_ONLY` | Editor Toolなし | File / Gitのみ |
| `SAFE_MODE` | Editor Safe Mode | narrow log + source patch + recovery |
| `NO_EDITOR` | Editor未インストール | static-only |

ただしRuntimeはProfile名で一括Routingしません。

同一Task内でもCapabilityごとにProviderを選びます。

```text
project.inspect -> File
project.test    -> Native Unity Editor CLI
scene.inspect   -> MyUnityMCP
player.observe  -> unavailable
```

のような混在を許可します。

## 6. Provider model

### 6.1 File Provider

常に最初に検討できる最小Providerです。

用途:

- Project Fact read
- C# / Shader / JSON / YAML等のtext source read
- C# / Shader /通常text source mutation
- Package manifest確認
- ProjectSettings確認
- Git diff
- Safe Mode recovery source patch

Default禁止:

- `.unity` Scene raw mutation
- `.prefab` raw mutation
- serialized `.asset` raw mutation

これらはEditor-aware Providerが無いことだけを理由に自動解禁しません。

### 6.2 Native Unity Editor CLI Provider

Unity CLIが無くても、Unity Editor本体のExecutableが存在する場合に利用します。

例:

```text
Unity.exe -batchmode -projectPath <root> ...
```

用途:

- Project import / compile observation
- command-line Player Build
- Build Profile / Build Target build
- Unity Test Framework command-line test
- allowlisted named `-executeMethod`
- Editor log capture

`-executeMethod`は既存の名前付きAutomation Entry Pointを優先します。

LLM生成の匿名任意コード実行経路として使用しません。

### 6.3 Unity CLI Provider

存在する場合のみ利用します。

用途:

- Editor / Project discovery
- Editor install管理
- Build / Test
- `com.unity.pipeline`
- warm Editor command
- Player Runtime command
- JSON / NDJSON structured transport

Unity CLIが無い場合、**自動インストールを必須前提にしません**。

ユーザーTaskがCLI導入自体を要求していない限り、利用可能な他Providerを先に評価します。

### 6.4 MyUnityMCP Provider

接続され、対象Projectへ正しくBindingできる場合のみ利用します。

特にDomain Mutationでは既存Safety Contractを維持します。

```text
Inspect
 -> Prepare
 -> Exact Diff
 -> Revision
 -> Approval
 -> Apply
```

MCPが存在しないことはUnityAgent全体の失敗ではありません。

### 6.5 Coplay MCP Provider / Bridge

利用可能な場合にEditor Capabilityを提供します。

参考にする性質:

- tool discovery
- grouped tool visibility
- multi-instance routing
- project-local tools
- long-running job

ただしUnityAgentのPolicy / Orchestration Authorityにはしません。

### 6.6 Player Runtime Provider

Playerが接続可能な場合のみRuntime Observationを提供します。

存在しない場合:

```text
player_observation = unavailable
```

であり、Editor EvidenceからPlayer成功を推測しません。

## 7. Capability resolution

RuntimeはProviderではなくCapabilityから解決します。

```yaml
request:
  capability: project.test
  required_evidence:
    - test_execution
  project_root: D:/Projects/MyGame/Project
```

Resolver:

```text
1. Environment Snapshotを取得
2. Capabilityを実行できるProvider候補を列挙
3. Project Bindingを確認
4. Policy / Approvalを確認
5. Required Evidenceを満たせるか確認
6. Safety Contractを比較
7. 最適なProviderを選択
8. 無ければ unavailable / partial を返す
```

## 8. Capability Matrix

| Capability | MyUnityMCP | Coplay MCP | Unity CLI / Pipeline | Native Editor CLI | File | Providerなし時 |
| --- | --- | --- | --- | --- | --- | --- |
| `project.inspect` | yes | yes | yes | limited | yes | unavailable |
| `source.read` | limited | limited | limited | no | yes | unavailable |
| `source.patch` | optional | optional | optional | no | yes | unavailable |
| `compile.observe` | yes | yes | yes | yes | log/static limited | `not_observed` |
| `project.test` | optional | yes when testing exposed | yes | yes when Test Framework available | no | `unavailable` |
| `project.build` | optional | yes when build exposed | yes | yes | no | `unavailable` |
| `scene.inspect` | preferred | yes | Pipeline when available | no generic scene API | static read only | `unavailable` or `static_only` |
| `scene.mutate` | preferred | guarded generic | allowlisted named command | allowlisted named `-executeMethod` only | default prohibited | `unavailable` |
| `profiler.observe` | preferred | yes when group enabled | project command if exposed | custom named automation only | no | `unavailable` |
| `player.observe` | optional dedicated | no default guarantee | RuntimeOnly command | no generic bridge | no | `unavailable` |

## 9. Automatic fallbackの条件

Automatic fallbackを許可するのは、**Semantic SafetyとEvidence Strengthが要求を満たす場合だけ**です。

```text
Provider A unavailable
  ↓
Provider Bが同じCapabilityを提供
  ↓
Policy/Mutation Scopeを維持
  ↓
Required Evidenceを満たす
  ↓
Safety Contractが同等以上
  ↓
自動Fallback可
```

### 許可例

```text
project.test
Unity CLI unavailable
Native Unity Editor + Test Framework available
  -> Native Editor CLIでTest実行
```

### 禁止例

```text
scene.mutate
MyUnityMCP unavailable
  -> raw .unity YAML編集
```

は禁止します。

### Partial completion

完全なEvidenceを取得できなくても、安全に実行できる作業まで進められる場合は部分完了を許可します。

例:

```text
C# bug fix
File Providerあり
Unity Editorなし

source patch      = completed
static review     = completed
compile evidence  = not_observed
runtime evidence  = not_observed
completion        = partial_verified
```

## 10. Unity CLIを使わないケース

### Editorあり

```text
File Provider
+
Native Unity Editor CLI
```

で動作できます。

- C#/Shader編集: File Provider
- Compile: Native Editor
- Test: Native Editor + Test Framework
- Build: Native Editor command line
- Scene/Prefab Mutation: safe Editor Providerが無ければ原則Unavailable

### Editorなし

File Providerだけで静的作業を行います。

```text
read / patch / review = possible
compile               = not_observed
Editor                 = unavailable
Player                 = unavailable
```

## 11. MCPを使わないケース

Unity CLIがある場合:

```text
File
+
Unity CLI
+
Pipeline when installed
```

で実行します。

Pipelineが無い場合も、CLIのProject / Build / Test CapabilityとFile Providerを利用します。

CLIも無い場合はNative Editorへ移行します。

## 12. CLIもMCPも使わないケース

### Unity Editorあり

```text
File Provider
+
Native Unity Editor CLI
```

を標準とします。

この構成でもC#開発、Compile確認、Test、Buildは相当範囲まで可能です。

### Unity Editorなし

Static-onlyです。

```text
Project Fact
C# / Shader patch
Git diff
static review
```

まで行います。

Unity実行を必要とする成功条件は未達として明示します。

## 13. Safe Mode

Safe Modeは特別なEnvironment Stateです。

CLI/MCPの有無ではなく、Editorが正常にAssemblyをロードできない状態として扱います。

```text
compiler diagnostics取得
 -> reported sourceだけ修正
 -> target Project限定
 -> Editor restart
 -> Environment re-discovery
```

MCP/Pipeline復旧前にScene Mutationへ進みません。

## 14. Multi-instance

どのProviderでもTarget Project Root一致を最優先します。

```text
Provider discovery
 != target binding
```

MCPで複数Editorが接続されている場合も、曖昧な自動選択をしません。

Coplay MCPも複数Instance時にはactive instanceの明示Bindingを要求する設計を持つため、UnityAgent側でも同じくProject Root / stable instance identityでfail closedします。

## 15. Environment-aware result

Resultには必ず実行環境を含めます。

```yaml
environment_summary:
  unity_cli: unavailable
  myunitymcp: unavailable
  native_unity_editor: available
  player_runtime: unavailable

capabilities:
  source_patch: completed
  compile: observed_pass
  tests: observed_pass
  scene_runtime_validation: not_observed
  player_validation: unavailable
```

Providerが無かった事実をAgent failureにしません。

ただし、要求された成功条件を観測できなかった場合はCompletionを過大評価しません。

## 16. Completion classification

```text
verified
partial_verified
implemented_unverified
blocked_by_environment
not_applicable
```

### verified

Required Evidenceをすべて満たした。

### partial_verified

安全に実装・一部検証できたが、上位Evidenceが環境上Unavailable。

### implemented_unverified

変更は行えたが、Unity実行Evidenceを取得できていない。

### blocked_by_environment

TaskのCore Capability自体が利用不能。

## 17. Anti-regression

以下を禁止します。

- Unity CLIを必須依存にする。
- MyUnityMCPを必須依存にする。
- Coplay MCPを必須依存にする。
- MCPが無いだけでUnityAgent全体を停止する。
- CLIが無いだけでFile / Native Editor Capabilityを捨てる。
- Editorが無いのにCompile成功と報告する。
- Playerが無いのにRuntime成功と報告する。
- Provider unavailableを理由にraw Scene/Prefab mutationへ降格する。
- Provider selectionをOrchestration Graphへ固定する。
- Environment SnapshotをProject Factより優先して推測する。

## 18. Acceptance Criteria

- CLI / MCPが両方存在しても動く。
- CLIだけでも動く。
- MCPだけでも動く。
- CLI / MCPどちらも無くてもNative EditorがあればCompile/Test/Build Capabilityを利用できる。
- Editorも無ければFile Providerで安全に静的作業を継続できる。
- Scene/Prefab等の高Risk MutationはProvider不足を理由にSafetyを下げない。
- `unavailable` / `not_observed` / `partial_verified`を区別する。
- Provider availability failureをAgent quality regressionに誤分類しない。
- ProviderごとではなくCapabilityごとに解決する。
- Environment再検出後にProvider選択を更新できる。

## 19. Implementation impact

Tool Broker実装時には少なくとも次が必要です。

```text
Runtime/Tooling/
├─ environment_probe.py
├─ capability_resolver.py
├─ provider_registry.yaml
├─ provider_contract.py
├─ tool_broker.py
└─ Providers/
   ├─ File/
   ├─ NativeUnityEditor/
   ├─ UnityCli/
   ├─ MyUnityMcp/
   └─ CoplayMcp/
```

Native Unity Editor Providerを独立Providerとして追加することで、Unity CLIが存在しないProjectでもUnity公式Editor CLIを利用できます。

## 20. Final rule

```text
UnityAgentはToolを要求しない。
UnityAgentはCapabilityを要求する。
Runtimeが現在のUnity環境を観測する。
利用可能なProviderだけを使う。
不足するEvidenceは不足したまま正確に返す。
```
