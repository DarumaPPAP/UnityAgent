---
name: unity-architecture-design
description: Unityの新規Feature、System、UI、ECS、Jobs/Burst、ScriptableObject、C#ファイル構成を、所有権・Lifetime・変更軸・性能要件から選定する。小規模機能への過剰分割を防ぎ、各新規ファイルのSplit Reasonと不採用案を明示する。
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
metadata:
  version: "1.0.0"
---

# Unity Architecture Design

Unityの設計をPattern名から決めず、問題の規模、所有権、Lifetime、データ、実行方式、制作フローから決定する。

## When to use

- 新規FeatureまたはSystemの構造が未確定
- MonoBehaviour、Plain C#、ScriptableObjectの境界を決める
- MVP、MVVM、State、Strategy等の必要性を比較する
- Controller、Manager、Service、Interfaceの必要性を監査する
- ECS、Jobs、Burst、GameObjectとのHybrid構成を評価する
- C#ファイルの作りすぎ、薄いクラスの乱造を見直す

既知の局所バグ修正には`csharp-safe-patch`を使う。
原因不明の障害にはIncident Skillを使う。
確定済みArchitectureの実装だけなら`unity-implement`へ渡す。

## Required references

1. `SkillReferences/ARCHITECTURE_DECISION_POLICY.md`
2. `SkillReferences/ARCHITECTURE_STANDARDS.md`
3. `SkillReferences/CODING_STANDARDS.md`
4. 対象Sourceと直接依存
5. ECS、Rendering、UI等の条件付きReference

全Pattern、全Skill、全Referenceを一括で読まない。

## Workflow

### Step 1 — Scopeを分類する

次から最も近いものを一つ選ぶ。

- Local Behavior
- Feature
- System
- Project Infrastructure
- Data-parallel Simulation

ファイル数や行数ではなく、所有範囲、変更範囲、実行モデルで判断する。

### Step 2 — 最小構成を先に評価する

最初に次で成立するか検討する。

- 1 MonoBehaviour
- 1 Plain C# Type
- 1 ECS Feature File
- Primary Unity Typeと同一ファイル内のprivateまたはFeature-local補助型

成立する場合は、Pattern適用のためだけに層を増やさない。

### Step 3 — OwnershipとLifetimeを固定する

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

### Step 4 — Change Axisを特定する

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

### Step 5 — 2～4候補を比較する

問題に適合する候補だけを比較する。

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

### Step 6 — ECS Opportunity Check

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

### Step 7 — File Planを作る

各ファイルへ次を記載する。

- pathまたはportable filename
- Primary Type
- responsibility
- owner
- lifetime
- consumers
- Split Reason
- 同一ファイルへ統合できない理由

同一ファイルへ保持する型と、意図的に作らない型も記載する。

### Step 8 — Quality Gate

- Architecture Fit
- File Granularity
- Ownership and Lifetime
- Serialization Validation
- ECS Data Layout when applicable
- Performance Capture when Production performance adoption

### Step 9 — Decisionを返す

- Selected Architecture
- Rejected Alternatives
- File Plan
- Dependency Direction
- Serialization Contracts
- Validation Plan
- Re-evaluation Conditions

## Non-negotiable rules

- Single Cohesive Script Firstを既定とする。
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

# Architecture Decision

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
