# Unity Architecture Standards

## Core principles

- Specification, semantics, ownership and lifetime precede convenience when the problem scale requires them.
- Architecture is selected per problem domain, not imposed project-wide.
- Prefer the minimum cohesive solution that satisfies the confirmed requirements.
- Local BehaviorではUnity Lifecycle、既存Component、既存Callbackによる直接解決を最初に評価する。
- Feature / System以上ではOwnership、Lifetime、Change Axisを必要な深さで確認する。
- Separate configuration, orchestration, runtime execution and evidence collection only when those responsibilities have different owners, lifetimes or change axes.
- Prefer explicit dependencies over global lookup, service locators or mutable static state.
- Do not introduce Controller/Manager/Pool/Cache/DI/Fallback/Debug layers without a requirement and measurable benefit.
- Keep one primary responsibility per type and one primary hypothesis per patch.
- Pattern names, future possibilities and file line counts are not architecture evidence.
- ユーザーが指定した具体対象を、将来再利用だけを理由に一般化しない。

## Local behavior

一つのGameObjectまたはComponentで完結する処理は、次の順で確認する。

1. ユーザー指定のAttach先と既存Componentだけで成立するか。
2. Unity Lifecycleで成立するか。
3. 既存Callback / Eventで成立するか。
4. Unity APIまたは既存Domain Objectが必要な状態を保持していないか。
5. 追加状態、Watcher、Trigger、Serialized Targetが本当に必要か。
6. `Update` / Pollingなしで成立するか。

成立する場合はSystem級のArchitecture候補比較や汎用化を省略する。

## File granularity

Use Minimum Cohesive Solution First for local behavior and small features.

Create a new C# file only when at least one split reason exists:

- independent Unity component or asset
- different owner or lifetime
- Runtime / Editor boundary
- Managed / Burst / Job boundary
- GameObject Authoring / ECS Runtime boundary
- Assembly or Package dependency boundary
- confirmed multi-feature reuse
- independent public contract or replaceable backend
- independently valuable complex logic or performance unit

Unity上で独立してアタッチ、生成、参照されるMonoBehaviour、ScriptableObject、EditorWindow等は原則1 File 1 Primary Unity Typeとする。

Do not mechanically split private helpers, feature-local enums, results, comparers, jobs, ECS components, tags, aspects, system-local types or RenderGraph PassData into separate files.

Do not split by line count alone. When a small feature exceeds its normal file shape, document responsibility, owner, lifetime, consumers, split reason and why co-location is insufficient.

## Requirement surface

ユーザーが明示したGameObject、Component、Asset、対象範囲を最小Requirement Surfaceとして扱う。

再利用性、将来拡張、汎用性だけを理由に次を追加しない。

- 任意Target参照
- Profile
- Watcher
- Trigger
- Manager / Controller / Service
- Interface

追加する場合は、現在要求を満たすための実在理由を示す。

## State ownership

Unity APIまたは既存Domain ObjectがSource of Truthを持つ状態を、理由なく別fieldへ複製しない。

CacheやPrevious Stateは、変更検出、高コスト取得回避、履歴、Frame境界Snapshot等の実在理由がある場合だけ追加する。

## Abstraction policy

Controller, Manager, Coordinator or Service is allowed only when it owns at least one of:

- two or more independent participants
- execution order
- feature state transition
- resource creation and release
- cross-scene lifetime
- multiple input integration
- subsystem consistency
- failure, retry or cancellation

Do not create pass-through orchestration types.

Interface is allowed for real multiple implementations, platform/backend variation, external SDK boundary, package public contract, external I/O replacement or different implementation lifetime. A single implementation and hypothetical future reuse are insufficient.

## ScriptableObject policy

Use ScriptableObject when independent asset identity, shared immutable configuration, profile variation, designer authoring, independent distribution or strategy/definition data is required.

Do not use ScriptableObject only to make a MonoBehaviour thin, hold a few local values, create global mutable state or prepare for a hypothetical profile.

When ScriptableObject owns mutable runtime state, Runtime Set or Event Channel behavior, document owner, reset, listener release, Domain Reload and Editor asset mutation risks.

## ECS, Jobs and Burst

Evaluate ECS or Jobs/Burst when data is homogeneous, queried in batches, updated frequently, parallelizable and separable from managed GameObject references.

ECS is not reserved only for post-regression rescue. It is an active candidate for projectile, crowd, status tick, visibility, spatial partition, voxel/chunk, LOD, procedural simulation and GPU-driven data preparation workloads.

Do not apply 1 Type 1 File mechanically to ECS. Group feature-local components, tags, aspects, systems and jobs by Feature, Query, System Group, Package dependency or public contract.

Production performance adoption requires a baseline, fixed conditions, Before/After measurements, quality constraints and revert criteria. Evaluate GameObject bridge, Baking, structural changes, sync points, archetypes, chunk utilization, GC and native memory.

## Unity assets and serialization

Treat public APIs, serialized fields, prefab/scene references, enum values, save data, Shader property names, keyword names and file paths as compatibility contracts.

Do not automatically change:

- class/struct identity semantics
- synchronous/async API shape
- serialized field names or types
- enum numeric values
- ScriptableObject/Profile ownership
- Job dependency chains
- Shader Pass/LightMode/RenderState/CBUFFER layout

## Runtime ownership

For managed, native and GPU resources, document as needed by the problem scale:

- creator
- owner
- valid lifetime
- readers/writers
- synchronization
- release/disposal responsibility

Local BehaviorでUnity自身が所有するComponent状態まで重複して管理表へ展開しない。

## Rendering architecture

RendererFeature configures and registers passes. RenderPass declares inputs, outputs, execution timing and resources. Shader implements GPU work. Material is the unit of properties, keywords and render state. Runtime Evidence determines whether a performance change is adopted.

Before adding a Shader Pass, evaluate RendererFeature filtering, RenderQueue, Layer, ShaderTag, RendererList and reuse of Depth/MotionVectors/Shadow/Meta passes.

## Architecture decision output

Local Behaviorは次へ縮小する。

- Goal
- Attachment Target
- Lifecycle / Callback
- State / Resource
- Side Effect / Restore
- Validation

Feature / System以上の新規Architecture workは必要に応じて次を報告する。

- scope classification
- confirmed context
- ownership and lifetime
- change axes
- compared candidates
- selected architecture
- rejected alternatives
- file plan and split reasons
- types intentionally kept together
- types intentionally not created
- dependency direction
- serialization contracts
- validation plan
- re-evaluation conditions

## Evidence

Static findings and runtime findings are separate. Editor behavior is not sufficient evidence for IL2CPP, Player, Console or Switch. Performance changes require fixed conditions, Before/After measurements and revert criteria.
