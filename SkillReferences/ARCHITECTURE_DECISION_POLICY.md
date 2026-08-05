# Unity Architecture Decision Policy

## 1. Purpose

Unityの設計をMVP、Clean Architecture、Controller、ScriptableObject、ECS等の名称から開始せず、問題の規模、所有権、Lifetime、変更軸、データ配置、実行方式から決定する。

このPolicyは、過剰なC#ファイル分割と不要な抽象化を防ぎながら、巨大な一枚岩も防止し、ECS、Jobs、Burstを適合する問題で積極的に評価するための判断契約である。

## 2. Default: Single Cohesive Script First

小規模な機能は、理解可能な一つの責務を一つのC#ファイルへ実装することから開始する。

```text
Local Behavior
└── FeatureName.cs
```

次の理由だけでは分割しない。

- Single Responsibility Principleという名称
- Architecture Patternへの適合
- 将来再利用される可能性
- Mockを作成できる可能性
- DIへ対応できる可能性
- ファイル行数
- MonoBehaviourを薄く見せたい

責務を一つにすることと、型やファイルを一つの処理単位まで細分化することは同義ではない。

`Single Cohesive Script First`は、複数の実行Phase、副作用、Failure Boundaryを一つのPrimary Typeへ押し込むための規則ではない。ファイル数を最小化せず、理解と変更に必要な責務境界を最小化する。

## 3. Scope classification

### Local Behavior

一つのGameObjectまたはComponent内で完結する挙動。

既定候補:

- Single MonoBehaviour
- Primary Typeと同一ファイル内のprivate補助型

### Feature

一つのユーザー機能またはゲーム機能。

既定候補:

- MonoBehaviour
- 必要時のみPlain C# Logic
- 独立Assetとして価値がある場合のみScriptableObject

### System

複数Feature、Scene、Resource、外部入力を調停する。

CoordinatorまたはControllerは、状態、順序、Lifetime、Resourceのいずれかを実際に所有する場合だけ許可する。

### Project Infrastructure

Save、Network、Asset、Scene、Platform SDK等のProject横断境界。

Ports and Adapters、Backend Interface、Composition Rootを必要性に応じて使用する。

### Data-parallel Simulation

多数の同質データへ同一処理を適用する。

Jobs、Burst、ECS、Hybrid GameObject + ECSを積極評価する。

## 4. Hard Split Reasons

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
- read-only解析とSceneまたはAsset mutationの境界が異なる
- failure、retry、cancellation、rollbackの責任が異なる

該当しない型は、Primary Typeと同一ファイルまたは既存責務へ統合する。

## 5. One Primary Unity Type per File

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

Feature-localであること、internalまたはprivateであること、同じFeatureだけが使用することは、単独ではKeep-Together Reasonにならない。

## 6. Symmetric Cohesion Review

新しいファイルにはSplit Reasonを要求する。同時に、複雑な処理や補助型を同一Primary Typeまたは同一ファイルへ保持する場合はKeep-Together Reasonを要求する。

Keep-Together Reasonでは次を確認する。

- 同一owner
- 同一lifetime
- 同一execution phase
- 同一mutation boundary
- 同一failure boundary
- 主な変更理由が同じ
- 単独で理解または変更する価値が低い

次は自動分割条件ではなく、責務と依存方向を再評価するAnti-monolith Triggerである。

- read-only解析とScene、Asset、Prefab、Project Settings等のmutationが同居する
- previewまたはplan作成と本生成が同居する
- UI stateとdomain resultまたはanalysis resultが同じ型に混在する
- Undo、Rollback、Asset保存、Folder作成を通常の解析ロジックが直接所有する
- 一つのPrimary Typeが検索、検証、計画、生成、永続化のうち3 Phase以上を所有する
- 一つのメソッドが複数のfailure boundaryまたはtransaction boundaryを所有する
- `Processor`、`Manager`、`Controller`、`System`等の広い名前へ無関係な責務が集約される
- Primary Typeへ到達する前に多数のtop-level補助型が並び、entry pointの発見を妨げる
- 一つの仕様変更で、独立Phaseを含むファイル全体の理解が必要になる
- SceneまたはAssetを変更しないロジックを単独検証できるのに、Unity Editor mutationへ密結合している

行数、型数、メソッド数は単独で分割理由にしない。ただしAnti-monolith Triggerと同時に増大している場合は肥大化Evidenceとして扱う。

詳細は`COHESION_AND_FILE_GRANULARITY_STANDARDS.md`を使用する。

## 7. Soft Review Gates

数値は上限ではなく、分割理由またはKeep-Together Reasonを再確認するTriggerである。

| Scope | Initial shape | Review trigger |
|---|---:|---:|
| Local Behavior | Runtime 1 | 2ファイル超、または2 execution phase超 |
| Small Feature | Runtime 1～2 | Runtime 3ファイル超、またはread-onlyとmutationの同居 |
| Profile Feature | Runtime 1～2 + Profile 1 | 合計4ファイル超 |
| Medium System | 3～6 | 6ファイル超、または1 Primary Typeが3 phase以上を所有 |
| RendererFeature | C# 2前後 + Shader | C# 4ファイル超 |
| ECS Feature | Runtime 1 + Authoring 1 | 合計3ファイル超 |

Triggerを超えた場合、各ファイルについてResponsibility、Owner、Lifetime、Execution Phase、Side Effects、Mutation Boundary、Failure Boundary、Consumers、Split Reason、Keep-Together Reason、統合不可理由を提示する。

## 8. Controller, Manager and Service

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
- 広い名前を付け、検索、検証、計画、生成、永続化を無制限に吸収する

`Manager`、`Controller`、`Coordinator`、`Service`、`System`という名前自体は責務の証明にならない。

## 9. Interface

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

## 10. ScriptableObject

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

## 11. Presentation Architecture

### Direct View Logic

画面が小さく、状態と入力が局所的で、Presenterが転送層になる場合に使用する。

### MVP

uGUI、複数入力、複雑なView State、Presentation Logicの独立テスト価値がある場合に候補とする。

### MVVM

UI Toolkit Runtime Data Binding、多数Fieldの同期、明確なViewModel単位があり、Binding管理コストを上回る規模で候補とする。

MVPまたはMVVMをProject全体の標準にはしない。

## 12. ECS, Jobs and Burst

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

## 13. Architecture Decision output

設計結果は次を含む。

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
17. Human Readability Review

File Planでは、各新規ファイルのPrimary Type、Responsibility、Owner、Lifetime、Execution Phase、Side Effects、Mutation Boundary、Failure Boundary、Primary Change Reasons、Consumers、Split Reason、Keep-Together Reasonを記載する。
