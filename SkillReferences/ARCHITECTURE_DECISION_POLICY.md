# Unity Architecture Decision Policy

## 1. Purpose

Unityの設計をMVP、Clean Architecture、Controller、ScriptableObject、ECS等の名称から開始せず、問題の規模、所有権、Lifetime、変更軸、データ配置、実行方式から決定する。

このPolicyは、過剰なC#ファイル分割と不要な抽象化を防ぎながら、問題規模に応じて思考量そのものを切り替えるための判断契約である。

設計原則のCanonical Sourceは`SkillReferences/ENGINEERING_DESIGN_PRINCIPLES.md`とする。

## Engineering Principles Gate

Architecture候補やPatternを比較する前に、次の順序で判断する。

```text
Requirement / Existing Owner
↓
KISS — Simplest Cohesive Solution
↓
YAGNI — No Speculative Structure
↓
Cohesion / SRP
↓
Proven Knowledge Duplication
↓
Conditional SOLID
```

- KISSとYAGNIをSOLIDより先に適用する。
- DRYはSyntax similarityではなく、実在する同一Knowledge / Change Reasonの重複に対してのみ適用する。
- SRPはProperty単位のType分割を要求しない。
- OCP / LSP / ISP / DIPは、実在するVariation、Inheritance / Interface、Boundary、Dependency理由がある場合だけ評価する。
- Type / File Structureを確定した後にNamingを行う。Naming GateがArchitecture判断を逆方向に支配してはならない。

## 2. Default: Minimum Cohesive Solution First

小規模な機能は、ファイル数を減らすことではなく、ユーザー要求を満たす最小の凝集した解決から開始する。

これは`ENGINEERING_DESIGN_PRINCIPLES.md`におけるKISSのUnity実装規則であり、YAGNIと組み合わせてSpeculative Structureを抑止する。

```text
Local Behavior
└── 必要なUnity Component / Lifecycleだけで解決
```

次を必要性なしに追加しない。

- Target Object
- Watcher / Trigger
- Previous State / Initialized Flag
- Manager / Controller / Service
- Profile / ScriptableObject
- Interface
- Event relay
- Update Polling

次の理由だけでは分割または一般化しない。

- Single Responsibility Principleという名称
- Architecture Patternへの適合
- 将来再利用される可能性
- Mockを作成できる可能性
- DIへ対応できる可能性
- ファイル行数
- MonoBehaviourを薄く見せたい

責務を一つにすることと、型や状態を細分化することは同義ではない。

## 3. Scope classification and design depth

### Local Behavior

一つのGameObjectまたはComponent内で完結する挙動。

既定候補:

- Single MonoBehaviour
- Unity Lifecycle
- 既存Unity Component / API
- Primary Typeと同一ファイル内のprivate補助型

Local Behaviorは後述のFast Pathを使用し、成立する場合はSystem級Architecture分析を省略する。

### Small Feature / Feature

一つのユーザー機能またはゲーム機能。

既定候補:

- MonoBehaviour
- 必要時のみPlain C# Logic
- 独立Assetとして価値がある場合のみScriptableObject

複数参加要素、独立Lifetime、実在するChange Axisが現れた場合にのみ構造を増やす。

### System

複数Feature、Scene、Resource、外部入力を調停する。

CoordinatorまたはControllerは、状態、順序、Lifetime、Resourceのいずれかを実際に所有する場合だけ許可する。

### Project Infrastructure

Save、Network、Asset、Scene、Platform SDK等のProject横断境界。

Ports and Adapters、Backend Interface、Composition Rootを必要性に応じて使用する。

### Data-parallel Simulation

多数の同質データへ同一処理を適用する。

Jobs、Burst、ECS、Hybrid GameObject + ECSを積極評価する。

## 4. Local Behavior Fast Path

Local Behaviorでは、次の順序だけを先に確認する。

1. **Requirement Surface** — ユーザーが明示したGameObject、Component、Assetだけで成立するか。
2. **Unity Lifecycle** — `Awake`、`OnEnable`、`Start`、`OnDisable`、`OnDestroy`等で直接解決できるか。
3. **Existing Callback / API** — Unity標準Callbackや既存Component APIで解決できるか。
4. **Source of Truth** — Unityまたは既存Domain Objectが必要な状態をすでに保持していないか。
5. **Extra State Check** — 状態Cache、監視対象、Watcher、Triggerが本当に必要か。
6. **Polling Check** — `Update`やCoroutine Pollingを使わずに成立するか。
7. **File Check** — 1 Primary Unity Typeで成立するか。

上記で成立した場合は、次を省略する。

- 2～4 Architecture候補の比較
- Change Axis列挙
- System級Ownership表
- 将来利用を想定した抽象化
- 不要なFile Plan拡張

Local Behaviorの出力は原則次だけでよい。

1. Goal
2. Attachment Target
3. Lifecycle / Callback
4. State / Resource
5. Side Effect / Restore
6. Validation

## 5. Unity Lifecycle First

Unity Componentの有効化、無効化、生成、破棄、Scene境界などに直接対応する処理は、次の優先順で解決する。

```text
Unity Lifecycle
↓
Existing Unity Callback / Event
↓
Existing project event
↓
Explicit custom event
↓
Coroutine / Timer
↓
Update / Polling
```

`Update`は常時監視が要件そのものである場合、または上位手段で状態変化を検出できない場合にのみ採用する。

## 6. Requirement Surface Lock

ユーザーが具体的な対象を指定している場合、その対象を最小Requirement Surfaceとして保持する。

例:

```text
「MainCameraに付ける」
```

から、再利用性だけを理由に次を追加してはならない。

- 任意のTarget GameObject
- 別Trigger Component
- Profile Asset
- Watcher
- Manager

一般化が必要な場合は、現在要求を満たすための実在理由を示す。

## 7. No Extra State

Unity APIまたは既存Domain ObjectがSource of Truthを持つ場合、同じ意味の状態をprivate fieldへ複製しない。

状態Cacheを許可する代表例:

- 変更検出に前回値が必要
- 取得コストを避ける必要がある
- 履歴自体が仕様
- 非同期またはFrame境界をまたぐSnapshotが必要

`_initialized`、`_previousState`、`_hasState`等は「安全そう」という理由だけで追加しない。

## 8. Hard Split Reasons

新しいC#ファイルには最低一つの理由が必要である。

- Unity上で独立してアタッチするMonoBehaviour
- 独立して生成または参照するScriptableObject
- RuntimeとEditorの分離
- ManagedとBurst / Jobの分離
- GameObject AuthoringとECS Runtimeの分離
- ownerが異なる
- lifetimeが異なる
- AssemblyまたはPackage依存が異なる
- 外部Systemとの独立契約
- 複数Featureから実際に共有される
- 単独で置換するBackend
- 独立テスト価値の高い複雑なロジック
- 独立した性能計測またはJob依存を持つ

該当しない型は、Primary Typeと同一ファイルまたは既存責務へ統合する。

## 9. One Primary Unity Type per File

Unity上で独立してアタッチ、生成、参照される次の型は、原則として1 File 1 Primary Typeとする。

- MonoBehaviour
- ScriptableObject
- EditorWindow
- CustomEditor
- ScriptedImporter
- RendererFeature

次は無条件に別ファイルへ分離しない。

- private enum
- private class
- private readonly struct
- Feature-local Result
- Feature-local Comparer
- Feature-local Job
- ECS Component
- ECS Tag Component
- ECS Aspect
- System専用Job
- RenderGraph PassData
- 小規模な内部State

複数のpublic Unity Object型を一つのファイルへ詰め込むことを推奨する規則ではない。

## 10. Soft Review Gates

数値は上限ではなく、分割理由を再確認するTriggerである。

| Scope | Initial shape | Review trigger |
|---|---:|---:|
| Local Behavior | Runtime 1 | 2ファイル超 |
| Small Feature | Runtime 1～2 | Runtime 3ファイル超 |
| Profile Feature | Runtime 1～2 + Profile 1 | 合計4ファイル超 |
| Medium System | 3～6 | 6ファイル超 |
| RendererFeature | C# 2前後 + Shader | C# 4ファイル超 |
| ECS Feature | Runtime 1 + Authoring 1 | 合計3ファイル超 |

Triggerを超えた場合、各ファイルについてResponsibility、Owner、Lifetime、Consumers、Split Reason、統合不可理由を提示する。

## 11. Controller, Manager and Service

作成を許可する条件:

- 2つ以上の独立した参加要素を調停する
- 実行順序を所有する
- Feature全体の状態遷移を所有する
- Resource生成と解放を所有する
- SceneをまたぐLifetimeを持つ
- 複数入力を統合する
- Subsystem間の整合性を保証する
- Failure、Retry、Cancellationを所有する

禁止:

- 一つの依存先へ処理を転送するだけ
- Stateや順序を持たない
- 名前を付けるためだけ
- Pattern構造を完成させるためだけ

`Manager`、`Controller`、`Coordinator`、`Service`、`System`という名前自体は責務の証明にならない。

## 12. Interface

Interfaceを許可する条件:

- 実在する複数実装
- PlatformまたはBackend切替
- 外部SDK境界
- Package間Public Contract
- 外部I/Oのテスト置換
- 実装とConsumerでLifetimeが異なる

禁止:

- 実装が一つでVariation Axisがない
- Mock可能性だけが理由
- DI形式を整えるだけ
- 将来必要になる可能性だけ
- 一つのメソッドを転送するだけ

Interface採用時はImplementations、Consumer、Variation Axis、Concrete dependencyでは不足する理由を記録する。

## 13. ScriptableObject

積極採用条件:

- 複数Instanceで共有
- 複数Profileの差し替え
- Stage、Platform、Character等のVariation
- Prefabから独立したAuthoring
- Designerが独立Assetとして編集
- Addressables等で独立配信
- Asset Identity自体に意味がある
- DefinitionまたはStrategy Asset

非採用条件:

- 一つのMonoBehaviourだけが使う少数の値
- SerializeFieldで十分
- MonoBehaviourを薄く見せたいだけ
- 一つしかProfileがない
- Runtime Stateの保存だけ
- Global Mutable Stateとしての利用

提案時はAuthoring Data、Shared Immutable Configuration、Profile、Definition Asset、Strategy Asset、Runtime Set、Event Channel、Mutable Runtime Stateのどれかを明示する。

Runtime Set、Event Channel、Mutable Runtime StateはOwner、初期化、解除、Domain Reload、Editor Asset汚染を追加確認する。

## 14. Presentation Architecture

### Direct View Logic

画面が小さく、状態と入力が局所的で、Presenterが転送層になる場合に使用する。

### MVP

uGUI、複数入力、複雑なView State、Presentation Logicの独立テスト価値がある場合に候補とする。

### MVVM

UI Toolkit Runtime Data Binding、多数Fieldの同期、明確なViewModel単位があり、Binding管理コストを上回る規模で候補とする。

MVPまたはMVVMをProject全体の標準にはしない。

## 15. ECS, Jobs and Burst

### Opportunity Check

次のうち3項目以上が成立する場合、ECSまたはJobs/Burst案を候補から除外しない。

- 多数対象へ同一処理
- 高頻度更新
- 同質データ
- 並列化可能
- unmanaged化可能
- Queryで更新対象を表現可能
- GameObject参照をHot Path外へ分離可能
- 将来的な対象数増加が要件として確定

### Active evaluation targets

- Projectile
- Crowd
- NPC群の簡易Simulation
- Status Effect Tick
- Visibility / Distance
- Spatial Partition
- Voxel / Chunk
- Environment Instance
- LOD評価
- GPU Driven用データ生成
- Procedural Simulation
- 大量MarkerまたはIndicator

### Caution targets

- 少数の固有Character
- AnimatorまたはTimelineへの高頻度Bridge
- GameObject参照を大量に持つ
- Entityごとに大きく異なる処理
- 高頻度Structural Change
- Managed ComponentがHot Pathに残る
- Authoring Costが利益を上回る小規模機能

### ECS file granularity

ECSでは1型1ファイルを要求しない。

```text
EnemyMovementAuthoring.cs
  MonoBehaviour Authoring
  Baker

EnemyMovementEcs.cs
  Components
  Tags
  Aspect
  System
  System-local Job
```

分離単位はFeature、Query、System Group、Package依存、Public Contractとする。

### Production evidence

本番採用では可能な範囲で次を比較する。

- GameObject Baseline
- Jobs / Burst Variant
- ECS Variant
- Main Thread Time
- Worker利用率
- Total CPU Time
- Chunk Utilization
- Archetype数
- Structural Change
- Sync Point
- GC Allocation
- Native Memory
- Baking Cost
- GameObject Bridge Cost
- Player / IL2CPP
- Target Device
- DebugとAuthoring Cost

性能ArchitectureはBefore / AfterとRevert条件なしに採用確定しない。

## 16. Architecture Decision output

Local Behavior Fast Pathで完結しないFeature / System以上では次を含む。

1. Goal
2. Scope
3. Confirmed Context
4. Ownership and Lifetime
5. Change Axes
6. Candidate Architectures
7. Selected Architecture
8. Rejected Alternatives
9. File Plan
10. Types Kept in the Same File
11. Intentionally Not Created Types
12. Dependency Direction
13. Data and Execution Flow
14. Serialization Contracts
15. Validation Plan
16. Re-evaluation Conditions

File Planでは、各新規ファイルのPrimary Type、Responsibility、Owner、Lifetime、Consumers、Split Reasonを記載する。
