# Unity Runtime Debugger Harness Specification

## Status

Draft v1.0 — UnityAgent source-of-truth design.

## Goal

Development Player / Console / mobile実機上で、対象Classの状態、Debug操作、Method呼び出し履歴を、Unity IMGUIベースの複数Windowとして即座に確認できる汎用Debugger Harnessを提供する。

本HarnessはProfiler、Frame Debugger、RenderDoc、Editor Inspectorの代替ではない。目的は「今このInstanceの値は何か」「このMethodは呼ばれたか」「Debug専用Commandを実行したい」を実機上で最短確認すること。

## Core UX

```text
[Debug]

┌ ADV ──────────────────────┐
│ Instance [AdvController▼] │
│ Current Page        32    │
│ Is Playing          True  │
│ State               TALK  │
│                           │
│ PlayAnimation       14    │
│ Last Call        0.82s    │
│                           │
│ [Force Skip]              │
└───────────────────────────┘

            ┌ Audio ───────────────┐
            │ Current BGM  BGM_03  │
            │ SE Count     4       │
            └──────────────────────┘
```

## Design principles

1. Debug対象Class = 1 Window。
2. 同一Type複数Instance = Window内Selector。
3. Attribute opt-in。全private memberの自動公開は禁止。
4. Read-only WatchとMutationを分離する。
5. Reflection metadata scanと値更新を分離する。
6. HostがWindow stateとbinding lifetimeを所有する。
7. Runtime/Editor境界を分離する。
8. ReleaseへDebug mutation pathを残さない。
9. Editor success != Player/IL2CPP success。
10. TraceはReflection単独では実現しない。

## Required runtime types

### RuntimeDebugHost

Primary Unity Type。

Responsibilities:

- IMGUI entry point
- launcher
- Type Window ownership
- Window Rect/open/collapse/scroll state
- Type metadata cache
- Scene instance binding
- selected instance state
- controlled watch refresh
- drawing standard widgets

Must not own:

- production game state
- gameplay command queue
- application-wide logging
- networking/remote console
- Editor instrumentation

### RuntimeDebugAttributes

Feature-local Attribute群。

Initial surface:

```text
RuntimeDebugWindowAttribute
RuntimeDebugWatchAttribute
RuntimeDebugEditableAttribute
RuntimeDebugCommandAttribute
RuntimeDebugTraceAttribute
```

V1で実際に不要なAttributeは実装しない。

## Attribute semantics

### RuntimeDebugWindowAttribute

Target: Class

Properties:

- DisplayName: optional

Behavior:

- Attribute付きTypeだけWindow candidate。
- DisplayName省略時はType.Name。

### RuntimeDebugWatchAttribute

Target: Field / Property

Properties:

- DisplayName: optional
- Order: optional only when real ordering need exists

Behavior:

- read-only
- getter exceptionはDebug rowへ表示し、game flowをcatchで継続させる用途に使わない
- Property getterは副作用禁止

### RuntimeDebugEditableAttribute

Target: Field / settable Property

Properties:

- DisplayName
- optional Min/Max for numeric slider

Behavior:

- explicit debug-only mutation
- unsupported typeはread-only fallbackではなくUnsupported表示または対象外

### RuntimeDebugCommandAttribute

Target: Method

V1:

- parameterless instance method only
- void returnを基本
- invocation exceptionをWindow上へ表示
- arbitrary overload bindingは実装しない

### RuntimeDebugTraceAttribute

Target: Method

Metadata only unless instrumentation backend is enabled。

Required displayed data when trace is active:

- call count
- last call realtime
- optional recent ring history

Optional data:

- arguments
- return value
- stack trace

Optional dataはAllocationと情報量が増えるため明示enable時のみ。

## Window system

### Launcher

- compact button or strip
- discovered Window list
- Open/Close toggle
- All Close
- optional Search when Window count justifies it

### Window

Required:

- stable integer ID
- title
- drag
- collapse
- close
- scroll
- selected instance

Optional:

- resize handle
- pin
- reset position

DockingはV1対象外。

### Instance selection

If count == 1:

- selector hidden

If count > 1:

- selector displayed
- Object name and instance IDを区別可能な表示にする
- destroyed instanceをScene/Lifetime refreshで除去する

500 Enemyのような場合でも500 Windowを生成しない。

## Immediate-mode widget surface

Required primitive set:

### Display

- Label
- Value
- Separator
- Space
- Foldout
- Horizontal group
- Vertical group
- ScrollView

### Input

- Button
- Toggle
- TextField
- IntField
- FloatField
- Slider
- Enum selector

### Diagnostics

- changed-value highlight
- command success/error
- trace count
- last-call age
- ring history

Dear ImGui API互換は要求しない。目的はUnity Runtime Debuggerに必要なImmediate-mode interaction modelを提供すること。

## Custom Draw extension

Attributeだけで不足する実在用途が複数確認された場合にのみ追加する。

Preferred shape:

```text
IRuntimeDebugCustomDraw
```

Interface adoption gate:

- 2つ以上の実装が存在する、または明確な外部契約が必要
- RuntimeDebugHostがconsumer
- arbitrary debug panel renderingがVariation Axis

単一画面だけなら追加しない。

## Reflection strategy

### Metadata scan

Allowed timing:

- Host initialization
- Scene loaded/unloaded
- explicit Rescan debug action when needed

Not allowed:

- every Update
- every OnGUI event

Cache per Type:

- Window attribute metadata
- FieldInfo / PropertyInfo / MethodInfo
- widget mapping metadata

Instance bindingはmetadataとは別管理。

## Refresh strategy

Watch value refreshはWindow表示中のみ。

Initial candidate:

- 5–10 Hz

ただし固定性能保証ではない。対象数、getter cost、target device evidenceで調整する。

`OnGUI` event回数をRefresh frequencyとして扱わない。

## Value change detection

Optional but recommended:

- last displayed valueをWindow entryが持つ
- changed時のみ短時間highlight

Previous valueは「変更検出」という明確な仕様があるため許可されるcache。

## Trace strategy

### Constraint

ReflectionはMethod metadataを取得できるが、通常のC# Method call interceptionを提供しない。

### Backend A — Manual trace

Use when:

- Unity Version / IL instrumentation compatibilityが未確認
- 最小導入を優先

Requirements:

- Trace state ownerを明確化
- global mutable static registryを安易に導入しない
- target codeへの追加行を明示する

### Backend B — Editor-only IL instrumentation

Use when:

- Attribute-only traceが必須
- 対象Unity VersionでIL post-processing pathが確認済み
- Player/IL2CPP validationを実施できる

Hard split:

```text
Runtime/
Editor or Build Instrumentation/
```

Must validate:

- compile
- Mono Player when relevant
- IL2CPP Player
- managed stripping
- domain reload
- incremental compile
- method overloads
- async/iterator/generated state machine boundaries

Do not claim universal support before evidence。

## IL2CPP / stripping

Required review:

- managed stripping level
- reflected private members
- Attribute metadata
- Preserve strategy
- link.xml scope

Prefer narrow preservation。

Avoid:

```xml
<assembly fullname="Assembly-CSharp" preserve="all" />
```

unless explicitly justified。

## Release exclusion

Recommended define:

```text
RUNTIME_DEBUG
```

Release requirements:

- Host unavailable or disabled
- Editable/Command path unavailable
- optional removal of Attribute metadata
- no hidden launcher input
- no Editor-only assembly reference from Runtime

`Debug.isDebugBuild` aloneに全security boundaryを依存しない。Project build policyでdefine/package inclusionを管理する。

## Input activation

Harness自身はProject Inputを所有しない。

Expose a bounded API such as:

```text
Show
Hide
Toggle
```

Project側がInput System、controller chord、touch gesture等から呼ぶ。

## File plan

### V1 minimum

```text
RuntimeDebugHost.cs
RuntimeDebugAttributes.cs
```

Split Reasons:

- Host: independent attachable MonoBehaviour / runtime lifetime owner
- Attributes: multiple target classesから参照されるcompile-time contract

### When automatic trace is enabled

```text
Runtime/
  RuntimeDebugHost.cs
  RuntimeDebugAttributes.cs
Editor/
  RuntimeDebugTracePostProcessor.cs
```

Editor instrumentationはRuntimeとAssembly/API boundaryが異なるためHard Split。

Do not create by default:

```text
RuntimeDebugManager.cs
RuntimeDebugService.cs
RuntimeDebugRegistry.cs
RuntimeDebugProfile.asset
IRuntimeDebugBackend.cs
```

## Acceptance criteria

### Functional

- `[RuntimeDebugWindow]` classが独立Windowとして表示される
- `[RuntimeDebugWatch]` private field/propertyを表示できる
- same Type multiple instancesをSelectorで切り替えられる
- Window drag/collapse/closeが動く
- LauncherからWindow visibilityを制御できる
- Editable/CommandはAttribute opt-inのみ
- destroyed instanceが安全に除去される
- Window hidden時にWatch refreshを止める

### Trace

- selected backendの制約が明示される
- Attribute-only traceをReflection-onlyで実装しない
- trace active時にcall count/last callを表示できる

### Compatibility

- Runtime AssemblyにUnityEditor dependencyなし
- target Unity Versionでcompile
- Development Playerで動作
- IL2CPP targetならIL2CPP Player validation
- strippingでWatch memberが消えない
- Release exclusion確認

### Performance

- every-frame reflection metadata scanなし
- hidden Windowのvalue pollingなし
- profiler evidenceなしに「負荷ゼロ」と報告しない

## Non-goals V1

- Dear ImGui binary/API compatibility
- docking
- remote TCP/WebSocket console
- profiler replacement
- scene hierarchy browser
- arbitrary object inspector
- automatic serialization editor
- graph plotting
- log capture system
- cheat console
- production telemetry

## Re-evaluation conditions

以下が発生したらArchitectureを再評価する。

- Window 30+でlauncher usabilityが低下
- Watch 500+でreflection refresh costが問題化
- remote device operationが必須
- automatic traceがManual Traceでは運用不能
- persistent window layoutが必要
- custom widgetsが複数Featureで共有される
- UI Toolkit runtimeへ移行する明確な要件が出る
