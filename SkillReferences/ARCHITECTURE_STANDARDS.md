# Unity Architecture Standards

## Core principles

- Specification, semantics, ownership and lifetime precede convenience.
- Architecture is selected per problem domain, not imposed project-wide.
- Prefer the smallest cohesive structure that satisfies the confirmed requirements.
- Separate configuration, orchestration, runtime execution and evidence collection only when those responsibilities have different owners, lifetimes or change axes.
- Prefer explicit dependencies over global lookup, service locators or mutable static state.
- Do not introduce Controller/Manager/Pool/Cache/DI/Fallback/Debug layers without a requirement and measurable benefit.
- Keep one primary responsibility per type and one primary hypothesis per patch.
- Pattern names, future possibilities and file line counts are not architecture evidence.

## File granularity

Use Single Cohesive Script First for local behavior and small features.

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

For managed, native and GPU resources, document:

- creator
- owner
- valid lifetime
- readers/writers
- synchronization
- release/disposal responsibility

## Rendering architecture

RendererFeature configures and registers passes. RenderPass declares inputs, outputs, execution timing and resources. Shader implements GPU work. Material is the unit of properties, keywords and render state. Runtime Evidence determines whether a performance change is adopted.

Before adding a Shader Pass, evaluate RendererFeature filtering, RenderQueue, Layer, ShaderTag, RendererList and reuse of Depth/MotionVectors/Shadow/Meta passes.

## Architecture decision output

New architecture work must report:

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
