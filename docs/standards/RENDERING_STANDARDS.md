# Unity Rendering Standards

## Target

- Unity 6 / Unity 2022 LTS
- URP / RenderGraph
- RendererFeature / ScriptableRenderPass
- ShaderLab / HLSL / Compute Shader
- STP / TAA / Motion Vectors
- Nintendo Switch / Switch 2 / PS4 / PS5 / PC

Confirm Unity version, URP package, Graphics API and target device before design. Do not mix Compatibility API and RenderGraph API in one execution path.

## Responsibility

- RendererFeature: settings, pass creation, registration conditions
- RenderPass: inputs, outputs, timing and resource declarations
- Shader: rendering contract and GPU work
- Material: properties, keywords and render-state operation
- Runtime Evidence: measurement and adoption decision

Do not add unrequested Controller, Manager, Hidden Shader, Camera or Debug UI as a workaround.

## GPU resource ownership

- State creator, lifetime and releaser.
- Do not retain `TextureHandle` outside its RenderGraph pass lifetime.
- State RTHandle/GraphicsBuffer/ComputeBuffer/NativeArray disposal ownership.
- Match color/depth format, dimension and sample count.
- Avoid unnecessary intermediate textures, resolves, copies and full-screen blits.
- Respect RenderGraph global-state and pass declaration constraints.
- Do not break native render-pass merging or pass culling through side effects.

## Pass additions

Before adding a pass, check:

1. RendererFeature-only filtering
2. RenderQueue / Layer / ShaderTag classification
3. RendererList filtering
4. existing Depth / MotionVectors / Shadow / Meta pass reuse
5. CPU draw-call and GPU bandwidth cost

Do not make adding another LightMode pass the first option.

## Shader external contract

Do not change without explicit approval:

- Shader name
- Material property name/type/default
- Keyword name, scope and runtime behavior
- Pass name / LightMode
- RenderQueue / RenderType
- Blend / ZWrite / ZTest / Cull / Stencil / ColorMask
- CBUFFER layout
- Texture / Sampler / Compute Kernel names
- Script property IDs
- include public functions
- Shader Graph custom-function signatures

Keep `UnityPerMaterial` CBUFFER layout consistent across passes.

## Performance model

Evaluate:

1. wave/warp coherence
2. texture/buffer/render-target bandwidth and cache
3. register pressure, spills and occupancy
4. barriers, atomics and CPU/GPU synchronization

Do not assume `if`, loops, `half` or branchless code are inherently good or bad. Scanner output is a candidate list, not a diagnosis.

## Precision and temporal data

Do not casually lower precision, resolution or stage for world position, depth reconstruction, motion vectors, history UV, reprojection, disocclusion, reactive masks, temporal weights, large UV domains or accumulated values.

A GPU-time improvement that introduces jitter, ghosting, flicker or disocclusion failure is a major regression.

## Transparent

Distinguish RenderQueue, shader queue and material raw queue. Check ZWrite, depth prepass, blend mode, screen coverage, layer count, particle bounds and mesh shape. Verify shader reassignment has not reset `renderQueue` to `-1`.

## Motion vectors

Check Forward and additional passes such as Outline. Prefer Unity's `ObjectMotionVectors.hlsl` and standard previous-matrix path before adding custom correction.

## Variant

Treat variant reduction and missing-variant prevention separately. Do not strip without reviewing runtime keywords, Addressables, AssetBundles, Resources, runtime-created materials and Strict Variant behavior.

## Validation

One patch, one primary performance hypothesis. Fix camera, scene, resolution and quality; warm up; collect multiple samples; exclude CPU-bound/VSync/dynamic-resolution effects; compare GPU time, registers, spills, occupancy, bandwidth, image difference, motion vectors, depth and temporal stability. Record revert conditions.
