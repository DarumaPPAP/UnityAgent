---
name: unity-architecture-design
description: Unityの新規Feature、System、UI、ECS、Jobs/Burst、ScriptableObject、C#ファイル構成を、問題規模に応じた思考量で選定する。Local BehaviorはLifecycleと最小構成を先に評価し、Feature/System以上では所有権・Lifetime・変更軸・性能要件から設計する。
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
metadata:
  version: "1.1.0"
---

# Unity Architecture Design

Unityの設計をPattern名から決めず、最初に問題規模を判定する。Local BehaviorはUnity Lifecycleと既存APIで解決できるかを優先し、重いArchitecture分析は必要な規模にだけ適用する。

## When to use

- 新規FeatureまたはSystemの構造が未確定
- MonoBehaviour、Plain C#、ScriptableObjectの境界を決める
- MVP、MVVM、State、Strategy等の必要性を比較する
- Controller、Manager、Service、Interfaceの必要性を監査する
- ECS、Jobs、Burst、GameObjectとのHybrid構成を評価する
- C#ファイルの作りすぎ、薄いクラスの乱造を見直す
- Local Behaviorが不要な監視、状態、汎用化を持っていないか確認する

既知の局所バグ修正には`csharp-safe-patch`を使う。
原因不明の障害にはIncident Skillを使う。
確定済みArchitectureの実装だけなら`unity-implement`へ渡す。

## Required references

1. `SkillReferences/ARCHITECTURE_DECISION_POLICY.md`
2. `SkillReferences/ARCHITECTURE_STANDARDS.md`
3. `SkillReferences/CODING_STANDARDS.md`
4. `SkillReferences/CODE_FORMATTING_STANDARDS.md` when C# output is produced
5. 対象Sourceと直接依存
6. ECS、Rendering、UI等の条件付きReference

全Pattern、全Skill、全Referenceを一括で読まない。

## Workflow

### Step 1 — Scopeを分類する

次から最も近いものを一つ選ぶ。

- Local Behavior
- Small Feature / Feature
- System
- Project Infrastructure
- Data-parallel Simulation

ファイル数や行数ではなく、所有範囲、変更範囲、実行モデルで判断する。

### Step 2 — Local Behavior Fast Path

Local Behaviorの場合は、Architecture候補比較より先に次を確認する。

1. ユーザーが指定したAttach先、Component、Assetだけで成立するか。
2. `Awake`、`OnEnable`、`Start`、`OnDisable`、`OnDestroy`等で成立するか。
3. Unity標準Callbackまたは既存Project Eventで成立するか。
4. Unity APIまたは既存Domain Objectが状態のSource of Truthを持っていないか。
5. Serialized Target、Watcher、Trigger、Previous State、Initialized Flagが本当に必要か。
6. `Update` / Pollingを使わず成立するか。
7. 1 Primary Unity Typeで成立するか。

成立する場合はここでArchitecture決定を完了し、次を追加しない。

- 任意Target化
- 将来用Interface
- Manager / Controller / Service
- Profile / ScriptableObject
- 独自Event relay
- 不要な状態Cache
- System級の候補Architecture比較

Local Behaviorの出力は次へ縮小する。

- Goal
- Attachment Target
- Lifecycle / Callback
- State / Resource
- Side Effect / Restore
- Validation

### Step 3 — Minimum Cohesive Solutionを評価する

Fast Pathで完結しない場合も、最初に次で成立するか検討する。

- 1 MonoBehaviour
- 1 Plain C# Type
- 1 ECS Feature File
- Primary Unity Typeと同一ファイル内のprivateまたはFeature-local補助型

成立する場合は、Pattern適用のためだけに層を増やさない。

### Step 4 — OwnershipとLifetimeを固定する

Feature / System以上、またはResource寿命が実際に問題になる場合に確認する。

- creator
- owner
- valid lifetime
- readers / writers
- initialization
- synchronization
- release / disposal
- Scene Load / Unload
- Domain Reload

未解決項目はBindingとして記録し、名前やPathを推測しない。

### Step 5 — Change Axisを特定する

実際に独立して変化するものだけを列挙する。

- Platform
- Backend
- Profile
- Stage
- UI framework
- GameObject / ECS execution model
- Authoring / Runtime
- Editor / Player

「将来変わるかもしれない」はVariation Axisにしない。

### Step 6 — 必要な場合だけ2～4候補を比較する

Local Behavior Fast Pathで完結した場合は候補比較を行わない。

Feature / System以上で構造選定が必要な場合のみ、問題に適合する候補を比較する。

- Single MonoBehaviour
- MonoBehaviour + local helper types
- MonoBehaviour + Plain C# logic
- MonoBehaviour + ScriptableObject Profile
- Feature Coordinator
- MVP / MVVM
- State / Strategy / Command / Observer
- Ports and Adapters
- Jobs / Burst
- ECS
- Hybrid GameObject + ECS
- RendererFeature / RenderPass / Shader

各候補について利点、欠点、Runtime Cost、Authoring Cost、Migration Costを簡潔に示す。

### Step 7 — ECS Opportunity Check

データ並列処理では、次の成立数を確認する。

- 多数対象へ同一処理
- 高頻度更新
- 同質データ
- 並列化可能
- unmanaged化可能
- Queryで対象を表現可能
- GameObject参照をHot Path外へ分離可能
- 将来大量化が要件として確定

3項目以上ならECSまたはJobs/Burst案を候補から除外しない。
本番採用時はGameObject Baseline、Jobs/Burst、ECSの比較Evidenceを要求する。

### Step 8 — File Planを作る

新規ファイルが複数必要な場合、各ファイルへ次を記載する。

- pathまたはportable filename
- Primary Type
- responsibility
- owner
- lifetime
- consumers
- Split Reason
- 同一ファイルへ統合できない理由

同一ファイルへ保持する型と、意図的に作らない型も記載する。

### Step 9 — Quality Gate

- Architecture Fit
- File Granularity
- Ownership and Lifetime when applicable
- Serialization Validation
- ECS Data Layout when applicable
- Performance Capture when Production performance adoption

### Step 10 — Decisionを返す

Local BehaviorではFast Pathの縮小出力を返す。
Feature / System以上では必要に応じて次を返す。

- Selected Architecture
- Rejected Alternatives
- File Plan
- Dependency Direction
- Serialization Contracts
- Validation Plan
- Re-evaluation Conditions

## Non-negotiable rules

- Minimum Cohesive Solution Firstを既定とする。
- Local BehaviorへSystem級Architecture分析を機械的に適用しない。
- Unity Lifecycleまたは既存Callbackで成立する場合、`Update` / Pollingを先に選ばない。
- ユーザー指定対象を再利用性だけで任意Target化しない。
- Unityまたは既存Domainが持つ状態を理由なく二重管理しない。
- Architecture Patternを満たすためだけに型やファイルを増やさない。
- 新規ファイルごとにHard Split Reasonを要求する。
- hypothetical reuseを分割理由にしない。
- 単純転送Controller、Manager、Service、UseCaseを作らない。
- 1実装しかないInterfaceを慣習だけで作らない。
- 局所SerializeFieldで足りる設定をScriptableObjectへ逃がさない。
- ECS Component、Tag、Aspect、Jobを1型1ファイルへ機械的に分割しない。
- MVPまたはMVVMをProject全体へ強制しない。
- 行数だけでファイルを自動分割しない。
- 性能改善を計測なしで確定しない。

## Output contract

### Local Behavior

1. Goal
2. Attachment Target
3. Lifecycle / Callback
4. State / Resource
5. Side Effect / Restore
6. Validation

### Feature / System以上

1. Goal
2. Scope
3. Confirmed Context
4. Ownership and Lifetime
5. Change Axes
6. Candidate Architectures when needed
7. Selected Architecture
8. Rejected Alternatives when compared
9. File Plan
10. Types Kept in the Same File
11. Intentionally Not Created Types
12. Dependency Direction
13. Data and Execution Flow
14. Serialization Contracts
15. Validation Plan
16. Re-evaluation Conditions
