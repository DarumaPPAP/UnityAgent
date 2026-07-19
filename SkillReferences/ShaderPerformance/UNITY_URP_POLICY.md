# Unity / URP Shader Performance Policy

## Target

Unity 2022 LTS and Unity 6, URP, RenderGraph, STP/TAA, Nintendo Switch/Switch 2/PS4/PS5/PC.

## Compatibility contract

Treat Shader name, properties, keywords, passes, LightModes, queue/type, Blend/ZWrite/ZTest/Cull/Stencil/ColorMask and CBUFFER layout as public API.

## SRP Batcher

Keep material properties in `UnityPerMaterial`, keep layout identical across passes, and do not hide incompatibility by moving properties to globals. Measure MaterialPropertyBlock trade-offs.

## URP Passes

Pass additions affect draw calls, variants, build time and order. Check RendererFeature filtering, RenderQueue/Layer/ShaderTag, RendererList, existing Depth/MotionVectors reuse and CPU draw-call cost first.

## RenderGraph

Respect global-state restrictions, handle lifetime, attachment format/sample compatibility, load/store/resolve behavior, intermediate texture cost and full-screen blit chains.

## Temporal

Do not casually lower precision or resolution for motion vectors, depth, history/reprojection, disocclusion, reactive masks or temporal weights. Temporal instability outweighs a small single-frame gain.

## Transparent

Check queue/raw queue/shader queue, ZWrite, depth prepass, blend mode, coverage, overdraw, bounds and shader reassignment.

## Player validation

Editor success does not prove Player variants, IL2CPP behavior or target-device performance.
