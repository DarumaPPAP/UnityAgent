# Unity Architecture Standards

## Core principles

- Specification, semantics, ownership and lifetime precede convenience.
- Separate configuration, orchestration, runtime execution and evidence collection.
- Prefer explicit dependencies over global lookup, service locators or mutable static state.
- Do not introduce Controller/Manager/Pool/Cache/DI/Fallback/Debug layers without a requirement and measurable benefit.
- Keep one primary responsibility per type and one primary hypothesis per patch.

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

## Evidence

Static findings and runtime findings are separate. Editor behavior is not sufficient evidence for IL2CPP, Player, Console or Switch. Performance changes require fixed conditions, Before/After measurements and revert criteria.
