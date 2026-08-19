# Runtime Debugger Harness Implementation Prompt

このPromptはUnity ProjectへRuntime Debugger Harnessを実装する時に使用する。
UnityAgentの現行`main` Policyを正本として扱い、一般的Best Practiceで上書きしないこと。

## Role

Unity C# Runtime Debugger Harnessの実装担当として作業する。
目的は、Development Player/実機でClass単位のIMGUI Debug Windowを表示し、Attributeで指定したField/Property/Methodだけを観測・操作できる汎用Harnessを作ること。

## Required source of truth

最初に次を読む。

1. `.ai/user-policy.yaml`
2. `.agents/skills/unity-runtime-debugger-harness/SKILL.md`
3. `Specs/RuntimeDebuggerHarness/spec.md`
4. `SkillReferences/CODING_STANDARDS.md`
5. `SkillReferences/CODE_FORMATTING_STANDARDS.md`
6. `SkillReferences/ARCHITECTURE_DECISION_POLICY.md`
7. `SkillReferences/CSHARP_ANTIPATTERN_RULES.md`
8. 対象Projectのasmdef、rootNamespace、関連Source

全Skill/全Referenceを一括で読まない。

## Goal

以下のDeveloper UXを成立させる。

```csharp
[RuntimeDebugWindow("ADV")]
public sealed class AdvController : MonoBehaviour
{
	[RuntimeDebugWatch("Current Page")]
	private int _currentPage;

	[RuntimeDebugWatch("Is Playing")]
	private bool _isPlaying;

	[RuntimeDebugCommand("Force Skip")]
	private void Skip()
	{
		// Existing game logic.
	}
}
```

実機では概ね次のWindowとして見えること。

```text
┌ ADV ──────────────────────┐
│ Instance [AdvController▼] │
│ Current Page        32    │
│ Is Playing          True  │
│                           │
│ [Force Skip]              │
└───────────────────────────┘
```

同一Typeが複数存在する場合はWindowを複製せず、Window内でInstanceを切り替える。

## Architecture constraints

### Required

- `RuntimeDebugHost`をIMGUI Window群のOwnerにする。
- `RuntimeDebugHost`がWindow Rect、open/collapse state、scroll、selected instance、Type metadata cache、instance bindingを所有する。
- Target ComponentはProduction stateのSource of Truthのままにする。
- Class-level AttributeをWindow境界にする。
- member-level Attributeが付いたものだけをDebug対象にする。
- Reflection metadata scanとvalue refreshを分ける。
- Metadata scanを毎Frame行わない。
- Window非表示時にWatch getterを継続評価しない。
- Runtime Assemblyから`UnityEditor`を参照しない。
- Release除外手段を実装または明示する。

### Do not add without a real requirement

- RuntimeDebugManager
- RuntimeDebugService
- Singleton
- Service Locator
- mutable static registry
- ScriptableObject Profile
- DI container
- generic backend Interface with one implementation
- remote TCP/WebSocket console
- docking system
- profiler replacement
- scene hierarchy browser

## Initial file plan

まず次の2ファイルで成立するか評価する。

```text
RuntimeDebugHost.cs
RuntimeDebugAttributes.cs
```

Split Reason:

- `RuntimeDebugHost.cs`: Unity上で独立してAttachされ、Runtime Debug UIのLifetimeを所有するPrimary MonoBehaviour。
- `RuntimeDebugAttributes.cs`: 複数のTarget Classから参照されるAttribute contract。

private helper class、metadata entry、window state、widget mappingは、独立Owner/Lifetime/ContractがなければHostと同一ファイルに保持する。

## Required Attributes

必要性を確認した上で次を実装する。

```text
RuntimeDebugWindowAttribute
RuntimeDebugWatchAttribute
RuntimeDebugEditableAttribute
RuntimeDebugCommandAttribute
RuntimeDebugTraceAttribute
```

観測だけがGoalならEditable/Command/Traceを先回りで実装しない。

## Window behavior

最低限:

- Launcher
- Window open/close
- collapse/expand
- drag
- scroll
- stable Window ID
- selected Instance
- Class DisplayName
- destroyed Instance cleanup

複数Instance:

```text
Count == 1 -> Selector非表示
Count > 1  -> Selector表示
```

Object instanceごとにWindowを生成しない。

## Widget mapping

Watchはread-only。

Editableを実装する場合のみ:

```text
bool              -> Toggle
int               -> Int field
float             -> Float field
string            -> Text field
enum              -> Selection
Vector2 / Vector3 -> numeric fields
```

numeric rangeがAttributeで明示されている場合のみSliderを使う。

`UnityEngine.Object`のruntime object pickerはRequirementがなければ作らない。

## Reflection rules

### Allowed

```text
Host initialize
Scene loaded/unloaded
explicit rescan
```

でType/Attribute metadataを収集しcacheする。

### Prohibited

```text
Update()
OnGUI() every event
```

ごとのScene-wide `Find` + `GetFields/GetProperties/GetMethods`。

Type metadataはType単位でcacheし、Instance bindingと分離する。

## Refresh rules

Watch値は表示Windowだけ更新する。
初期候補は5–10Hz程度だが、固定仕様として断定しない。
`OnGUI`は1Frame複数Eventで呼ばれうるため、OnGUI callごとにReflection value readをしない。

変更highlightを実装する場合、previous displayed valueは「変更検出」という仕様に必要なcacheとして許可する。

## Command rules

`RuntimeDebugCommandAttribute`を実装する場合:

- V1はparameterless instance methodを基本にする。
- Attributeが付いていないMethodを実行可能にしない。
- arbitrary overload resolverを作らない。
- invocation exceptionはDebug Windowへ表示する。
- game exceptionを握り潰して通常進行させる用途に使わない。

## Trace rules

最重要:

```text
RuntimeDebugTraceAttribute + Reflection
```

だけで通常のMethod callを自動検出できると実装・報告してはいけない。

Attribute-only automatic traceがRequirementなら、対象Unity Versionで利用可能なIL instrumentation pathを調査してから設計する。

Instrumentationが未確認なら:

```text
Automatic trace: unavailable / deferred
Manual trace: supported
```

と明示する。

IL instrumentationを採用する場合はRuntimeとEditor/Build instrumentationを別ファイル/assembly boundaryに分ける。Mono/IL2CPP、managed stripping、async/iterator/generated methodを確認する。

## IL2CPP / AOT / stripping

Player対応を主張する場合に必ず確認する。

- Unity Version
- Mono / IL2CPP
- Development / Release
- managed stripping level
- reflected private member preservation
- Attribute metadata preservation

必要なら`PreserveAttribute`または`link.xml`を使う。
Assembly全体`preserve="all"`は理由なしに使わない。

## Release policy

`RUNTIME_DEBUG`等の明示defineを候補にする。

Releaseで最低限:

- RuntimeDebugHostを利用不可にする
- Editable/Commandを利用不可にする
- hidden debug activationを残さない
- RuntimeからEditor assemblyへ参照しない

`Debug.isDebugBuild`だけを唯一のSecurity/Release境界にしない。

## Input ownership

HarnessがProject Inputを勝手に所有しない。

Public API候補:

```text
Show()
Hide()
Toggle()
```

Input System/controller chord/touch gestureとのbindingはProject側で行う。

## UnityAgent code style

- private field: `_camelCase`
- public API/type/member: `PascalCase`
- enum type: `E_UPPER_SNAKE_CASE`
- struct type: `S_UPPER_SNAKE_CASE`
- const: `SCREAMING_SNAKE_CASE`
- Allman Style
- Tab indentation
- 1行で自然に読めるassignment/method callを不自然に折らない
- 既存namespaceを維持
- Root Namespace不明時に`RootNamespace`等のplaceholderを実名出力しない

例:

```csharp
_cameraData = camera.GetUniversalAdditionalCameraData();
```

のような短い式を`=`直後で改行しない。

## Comment policy

日本語コメントは「何をしているか」の復唱ではなく、次が必要な箇所だけに付ける。

- Reflection scan frequencyの理由
- IL2CPP/stripping制約
- Owner/Lifetime
- Scene reload時のbinding
- Release除外
- Trace backend制約

## Validation

実装完了報告では、実施したGateと未実施Gateを分ける。

最低限:

```text
Static Review
Compile
Editor PlayMode
Development Player
IL2CPP Player when target uses IL2CPP
Target Device when実機対応を主張
Release exclusion
```

性能改善/低負荷を主張する場合だけProfiler Before/Afterを要求する。

## Acceptance criteria

- `[RuntimeDebugWindow]` Typeが独立Windowとして表示される。
- `[RuntimeDebugWatch]` private Field/Propertyがread-only表示される。
- 同一Type複数InstanceをSelectorで切替できる。
- Windowをdrag/collapse/closeできる。
- Launcherから必要Windowだけ開ける。
- Window hidden時にWatch evaluationを止める。
- Reflection metadata scanを毎Frame行わない。
- Mutationは明示Attributeだけ。
- RuntimeにUnityEditor dependencyがない。
- Trace制約を正しく扱う。
- Player/IL2CPP supportをEvidenceなしで断定しない。
- Release exclusionが確認できる。

## Final output

最後に次を報告する。

1. Confirmed environment
2. Selected architecture
3. Changed files
4. Split Reason for every new file
5. Attribute surface
6. Window/Widget behavior
7. Reflection and refresh behavior
8. Trace backend and limitations
9. IL2CPP/stripping handling
10. Release handling
11. Validation performed
12. Unverified items
13. Revert condition
