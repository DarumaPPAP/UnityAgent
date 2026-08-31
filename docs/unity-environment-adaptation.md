# Unity環境に応じた実行モード

UnityAgentはUnity CLIやMCPを必須としません。

利用時にそのProjectの環境を確認し、**現在利用できるCapabilityだけを選択して処理します**。

## 基本ルール

```text
Unity CLIあり/なし
MCPあり/なし
Unity Editorあり/なし
Player接続あり/なし
```

はすべてEnvironment Factです。

どれか1つが無いだけでUnityAgent全体を停止しません。

一方で、利用不能な検証を「成功した」とは扱いません。

## 代表例

### Unity CLI + MyUnityMCPが両方ある

```text
Project Fact -> File / MyUnityMCP
Scene        -> MyUnityMCP
Build/Test   -> Unity CLI
Player       -> Unity CLI Runtime / dedicated bridge
```

Capabilityごとに最適なProviderを使います。

### Unity CLIだけある

```text
Source       -> File
Build/Test   -> Unity CLI
Editor       -> Pipelineがあればlive command
Scene        -> Pipelineに安全なcommandが無ければMutationしない
```

### MCPだけある

```text
Source       -> File
Scene        -> MCP
Editor       -> MCP
Build/Test   -> MCPにCapabilityがあれば利用
               無ければNative Unity Editor CLIを検討
```

### Unity CLIもMCPもないがUnity Editorはある

Unity Editor本体の公式Command Lineを利用できます。

```text
Source       -> File
Compile      -> Unity Editor -batchmode
Test         -> Unity Test Framework command line
Build        -> Unity Editor command line build
Scene mutate -> safe Editor automationが無ければUnavailable
```

つまりCLI/MCPを追加しなくても、通常のC#修正、Compile確認、Test、Buildは相当範囲まで実行できます。

### Unity CLIもMCPもUnity Editorもない

Static-onlyです。

```text
Project Fact
C# / Shader read
source patch
Git diff
static review
```

Compile / Editor / Playerは次のように返します。

```text
compile = not_observed
editor  = unavailable
player  = unavailable
```

## Providerが無い時の考え方

Providerが利用不能でも、安全性が同等以上の別Providerがあれば自動的に切り替えられます。

例:

```text
Unity CLIが無い
↓
Unity Editor executableあり
↓
Native Unity Editor CLIでTest
```

一方、次は禁止です。

```text
MyUnityMCPが無い
↓
Sceneをraw YAMLで直接編集
```

MCPが無いことを理由にSafety Contractを弱めません。

## Partial completion

環境制約があっても、安全にできる範囲までは作業できます。

例:

```text
C#修正               completed
Static Review        completed
Compile              not_observed
Player Verification  unavailable
```

この場合は「全部確認済み」ではなく `partial_verified` または `implemented_unverified` として返します。

## Environment Snapshot

Runtime実装では少なくとも次を検出します。

- Target Project Root
- File read/write availability
- Git availability
- Unity Editor install/version/path
- Unity Editor running state
- Safe Mode
- Unity CLI availability
- `com.unity.pipeline` availability
- MyUnityMCP availability / Project binding
- Coplay MCP availability / Project binding
- Test Framework availability
- Target Build Module availability
- Player Runtime availability

未知の状態を勝手に`false`と決めません。

## 最終原則

```text
UnityAgentはUnity CLIを要求しない。
UnityAgentはMCPを要求しない。
UnityAgentはCapabilityを要求する。

Runtimeが環境を観測して、
その環境で利用可能なProviderだけを使う。

不足したEvidenceは不足したまま正確に報告する。
```

詳細なDesign Contractは `Specs/UnityToolRuntimeEnvironmentAdaptation.md` と `Specs/UnityEnvironmentCapabilityMatrix.yaml` を参照してください。
