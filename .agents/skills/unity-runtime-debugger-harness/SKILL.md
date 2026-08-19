---
name: unity-runtime-debugger-harness
description: Use when designing or implementing an in-game Unity debugger with IMGUI-style immediate-mode windows, Attribute-based runtime watches, editable debug controls, commands, method-call traces, or Player/IL2CPP diagnostics. Produces a bounded Runtime Debugger Harness with explicit ownership, release stripping, and validation. Does not investigate the underlying gameplay/rendering incident itself.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
metadata:
  version: "1.0.0"
---

# Unity Runtime Debugger Harness

## Purpose

Unity Editor外、Development Player、Console/端末実機で、対象Classの状態・操作・呼び出し履歴を即座に確認するためのRuntime Debugger Harnessを設計・実装する。

本SkillはDebug UIを一画面へ詰め込むのではなく、**Debug対象Class = 1 IMGUI Window**を基本単位とする。Attributeで80%の用途を宣言的に扱い、必要な場合だけImmediate-modeのCustom Drawを追加する。

Primary成果物:

- Runtime Debugger Harness architecture
- Attribute contract
- IMGUI Window/Widget contract
- Reflection/AOT/stripping contract
- Trace strategy
- File Plan
- Implementation prompt or source change
- Player/target-device validation plan

## When to use

- 「実機でprivate fieldを見たい」
- 「特定Methodが呼ばれたか確認したい」
- 「IMGUIみたいなDebug WindowをUnityに作りたい」
- 「ClassごとにDebug Windowを自動生成したい」
- 「Attributeを付けるだけでRuntime値を見たい」
- 「実機からDebug Commandを実行したい」
- 「Player/IL2CPP用の簡易Inspectorが欲しい」
- 「複数のDebug Windowをドラッグして並べたい」

次には使わない。

- 原因未確定の障害調査そのもの: `unity-incident-investigation`
- 一般的なEditorWindow/CustomInspectorのみ: 適切なC#/Editor route
- 既知の1行修正だけ: `csharp-safe-patch`
- Profiler/Frame Debugger/RenderDocの代替として性能原因を断定する作業

## Required references

1. `.ai/user-policy.yaml`
2. `SkillReferences/CODING_STANDARDS.md`
3. `SkillReferences/CODE_FORMATTING_STANDARDS.md` when C# is produced
4. `SkillReferences/ARCHITECTURE_DECISION_POLICY.md`
5. `SkillReferences/CSHARP_ANTIPATTERN_RULES.md`
6. `Specs/RuntimeDebuggerHarness/spec.md`
7. 対象Projectへ実装する場合は対象asmdef、rootNamespace、関連Source

## Canonical architecture

既定形:

```text
RuntimeDebugHost
├── Launcher / Window list
├── Type metadata cache
├── Debug window state
├── Scene instance binding
├── Watch refresh scheduling
└── IMGUI draw ownership

[RuntimeDebugWindow] Target Type
├── [RuntimeDebugWatch] Field / Property
├── [RuntimeDebugEditable] explicit mutable Field / Property
├── [RuntimeDebugCommand] Method
└── [RuntimeDebugTrace] Method metadata
```

### Ownership

- `RuntimeDebugHost`がDebug Window、Rect、open/collapse state、instance selection、metadata cacheを所有する。
- Target Componentはゲーム状態のSource of Truthを保持し、Debugger側へ値を複製しない。
- 同じTypeが複数Instanceある場合、Type Windowは1つとしInstance Selectorで切り替える。
- Scene Load/UnloadでTarget Instance bindingを更新する。
- Window非表示中は不要なWatch evaluationを止める。

### Do not create by default

- RuntimeDebugManager
- RuntimeDebugService
- Singleton
- Service Locator
- ScriptableObject profile
- DI container
- 1実装しかない抽象Interface
- 毎Frameの全Scene Reflection scan
- production logging subsystem
- remote networking console

必要なら実在するRequirementとSplit Reasonを提示する。

## Attribute contract

### RuntimeDebugWindowAttribute

Target: class

目的:

- Classを独立Debug Windowとして登録する。
- DisplayNameを省略した場合はType名を使う。

例:

```csharp
[RuntimeDebugWindow("ADV")]
public sealed class AdvController : MonoBehaviour
```

### RuntimeDebugWatchAttribute

Target: field / property

目的:

- read-only表示。
- private/publicを問わず明示的にAttributeが付いたmemberのみ対象。
- Property getterの副作用は禁止。Getterが重い場合は対象外または低頻度更新を選ぶ。

例:

```csharp
[RuntimeDebugWatch("Current Page")]
private int _currentPage;
```

### RuntimeDebugEditableAttribute

Target: field / settable property

目的:

- Debuggerから値を書き換える明示opt-in。
- WatchとEditableを混同しない。
- Production Game Stateを変更するため、Development/Debug define限定を基本とする。

標準Widget mapping:

- bool -> Toggle
- int -> Int field / optional slider
- float -> Float field / optional slider
- enum -> Selection
- string -> Text field
- Vector2/Vector3 -> numeric fields
- UnityEngine.Object -> 原則read-only。Runtime object pickerを勝手に追加しない。

### RuntimeDebugCommandAttribute

Target: method

目的:

- WindowからMethodを明示実行する。
- V1は原則parameterless methodのみ。
- arbitrary argument editor、overload resolver、async command queueは要求されるまで追加しない。

### RuntimeDebugTraceAttribute

Target: method

目的:

- Trace対象Method metadataを宣言する。

重要:

`MethodInfo`を取得しただけでは通常のC# method invocationを自動検出できない。Attribute-only Traceを成立させるにはInstrumentationが必要。

Trace backendは次の順で判断する。

1. 対象Unity Version/Build pipelineで安全なIL instrumentationが確認済み -> Editor-only instrumentationを候補にする。
2. instrumentationが未確認、またはIL2CPP/AOT互換性が不明 -> Manual Traceを使用する。
3. Debug convenienceだけを理由にmutable static global routerを作らない。

Trace表示の最小要件:

- call count
- last call realtime
- optional fixed-size ring history

引数・戻り値・stack trace記録はAllocation/Privacy/Performance costがあるためopt-inとする。

## Immediate-mode Window contract

IMGUI式Harnessが最低限持つ機能:

### Window shell

- launcher
- open / close
- collapse / expand
- drag
- optional resize
- scroll
- stable Window ID
- Type name / DisplayName
- selected Instance name
- Scene name when useful

### Layout

- Label
- Value row
- Horizontal / Vertical group
- Separator
- Space
- Foldout/group
- ScrollView

### Input

- Button
- Toggle
- Text field
- Int field
- Float field
- Slider
- Enum selection

### Diagnostics

- Watch value
- Changed highlight
- Command result/error
- Trace call count
- Last call time
- Ring history

Dear ImGuiの全API互換を目標にしない。Unity Runtime Debuggerとして必要なImmediate-mode primitiveを提供し、Docking、table virtualization、plotting、remote transport等は要求が出た時点で独立評価する。

## Custom draw extension

Attributeだけで表現しにくいDebug UIが実在する場合のみCustom Draw extensionを追加する。

候補:

- 複数実装が実際に存在するなら`IRuntimeDebugCustomDraw`
- またはHarness専用Draw callback contract

Interface採用時はImplementations、Consumer、Variation Axisを明示する。
単一画面のためだけにInterfaceを追加しない。

## Reflection and refresh rules

### Scan

許可:

```text
Host initialize / Scene boundary
-> candidate Components
-> Type metadata
-> Attribute members
-> cache
```

禁止:

```text
Every frame
-> Find all objects
-> GetFields/GetProperties/GetMethods
-> Attribute scan
```

### Refresh

- Reflection metadata scanとWatch value refreshを分離する。
- Watch refreshはWindow visible時のみ。
- 既定更新頻度を固定値として盲目的に保証しない。0.1s程度は初期候補であり、対象数と実機Evidenceで調整する。
- `OnGUI`はEvent種別により複数回呼ばれる可能性を考慮し、値更新を描画call数と同一視しない。
- Getter exceptionを通常flowにしない。Debug表示へerrorを隔離し、ゲーム処理を飲み込まない。

## IL2CPP / AOT / stripping

Reflectionを使う時点で必須レビュー:

- Editor / Player
- Mono / IL2CPP
- Development / Release
- Managed stripping level
- Attribute metadata preservation
- private reflected member preservation
- generic/runtime constructed typeの有無

対策候補:

- `PreserveAttribute`
- custom preserve marker
- `link.xml`
- generated preservation data

一律に`preserve="all"`へ逃げない。必要範囲だけ保持する。

Release contract:

- `RUNTIME_DEBUG`等の明示defineでHarnessを制御する。
- ReleaseではHostを生成しない。
- 可能ならDebug Attribute metadataも除去する。
- Debugger経由のmutable command/editable pathをReleaseへ残さない。

## Workflow

### Step 1 — GoalとRuntime boundaryを固定する

最低限:

- Unity Version
- Editor or Player
- Mono or IL2CPP
- Development or Release
- Target platform when Player/compatibility matters
- 観測だけか、値変更/Commandも必要か
- Traceが必要か

Projectから取得できる情報を質問し直さない。

### Step 2 — Window unitを固定する

既定:

```text
1 Target Type = 1 Window
```

複数InstanceはSelector。
ObjectごとにWindowを大量生成しない。

### Step 3 — Attribute surfaceを最小化する

最初に必要なAttributeだけを選ぶ。

- Window
- Watch
- Editable when requested
- Command when requested
- Trace when requested

見栄えのためだけにGroup/Order/Format Attributeを増やさない。

### Step 4 — Ownership/Lifetimeを確定する

- Host creator
- Host lifetime
- Scene reload behavior
- Domain reload behavior
- Target binding lifecycle
- metadata cache invalidation
- window state reset/persistence

### Step 5 — Trace backendを決める

Attribute-only自動Traceを要求された場合:

- Reflectionだけでは不可能と明示する。
- Target Unity VersionでIL instrumentationを採用できるか確認する。
- 未確認ならManual Trace契約へ落とす。
- Instrumentationを採る場合はRuntimeとEditor/Build instrumentationをHard Splitする。

### Step 6 — File Planを作る

V1の初期候補:

```text
RuntimeDebugHost.cs
RuntimeDebugAttributes.cs
```

ただしTrace instrumentation、Editor-only build processor、independent custom draw contractが実在する場合のみ分割する。

各新規ファイルにSplit Reasonを付ける。

### Step 7 — Implement or generate implementation prompt

C#を生成する場合:

- Project namespaceを解決する。
- UnityAgent naming/formattingを守る。
- RuntimeからUnityEditor参照を禁止する。
- public/serialized contractを無断変更しない。

Promptのみの場合も、Acceptance Criteriaと禁止事項を明記する。

### Step 8 — Validation

最低限:

1. Static review
2. Compile
3. Editor PlayMode smoke test
4. Development Player
5. IL2CPP Player when target uses IL2CPP
6. target device when実機利用がGoal
7. Release exclusion check

性能主張をする場合のみBefore/After captureを追加する。

## Scope guards

- Debuggerを原因修正そのものへ変質させない。
- DebuggerからProduction stateを勝手に変更可能にしない。
- 全private member自動公開をしない。
- `FindObjectsByType`等を毎Frame呼ばない。
- Attribute-only method traceをReflectionだけで実現したと報告しない。
- Editor-only APIをRuntime assemblyへ混ぜない。
- ReleaseへDebug menu/commandを残さない。
- Debug UIのためだけにProject全体へ新しいArchitectureを強制しない。

## Delegates to

- 原因調査: `unity-incident-investigation`
- C# bounded fix: `csharp-safe-patch`
- Harness全体の構造再検討: `unity-architecture-design`
- 実装後C# review: `unity-review` / C# reviewer
- Player/実機Evidence: `unity-runtime-evidence`
- IL weaving/Roslyn implementationが独立専門作業になる場合: 対応するC# implementation/reviewerへ委譲

## Output contract

1. Goal
2. Runtime environment
3. Selected Harness architecture
4. Window model
5. Attribute surface
6. Widget surface
7. Ownership and lifetime
8. Reflection/refresh strategy
9. Trace backend
10. IL2CPP/AOT/stripping strategy
11. Release exclusion strategy
12. File Plan and Split Reasons
13. Implementation prompt or changed files
14. Validation performed
15. Unverified Player/target-device items
16. Re-evaluation conditions

## Checklist

- [ ] Target Class = Windowの境界が明確
- [ ] 同一Type複数InstanceがWindow増殖しない
- [ ] WatchとEditableを分離した
- [ ] Commandは明示opt-in
- [ ] Reflection scanを毎Frame行わない
- [ ] TraceをReflectionだけで自動検出できると誤認していない
- [ ] Host owner/lifetimeが明確
- [ ] Runtime/Editor assembly境界が明確
- [ ] IL2CPP/AOT/stripping planがある
- [ ] Release exclusion planがある
- [ ] UnityAgent naming/formattingを守る
- [ ] Editor成功だけで実機成功と報告していない

## Common mistakes

- Category + Manager + Registry + Serviceを先に作り、Class WindowというRequirement Surfaceを失う。
- Object InstanceごとにWindowを生成して画面を埋める。
- `RuntimeDebugWatch`を付けていないprivate fieldまで全部晒す。
- Getterを毎OnGUI eventでReflection評価する。
- `MethodInfo`を持っているだけでMethod callを監視できると思う。
- IL2CPP strippingをEditorで見えたから問題ないと扱う。
- Debug CommandをReleaseへ残す。
- DebuggerのGC/CPU負荷をゲーム本体の性能回帰と混同する。

## Anti-Rationalization

| Rationalization | Required response |
|---|---|
| Debug用だからglobal staticでいい | DebugでもOwner/Lifetime/resetを明示する。必要なら例外理由を記録する |
| ReflectionはDebug用だから毎Frameでもいい | scan frequencyと対象数を分離し、metadataをcacheする |
| Attributeを付けたからTraceできる | Method invocation interceptionには別Instrumentationが必要 |
| Editorで動いたからIL2CPPも動く | Player/IL2CPP Evidenceを別Gateにする |
| 便利なので全部editableにする | Mutationは明示Attribute opt-inだけ |
| 将来使うのでDockingやRemote Consoleも入れる | 現Requirement外は別Taskへ分離する |
