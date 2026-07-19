# Shader Performance Standards

## Principles

Shader syntax is not inherently slow. Evaluate GPU execution coherence, bandwidth/cache, register pressure/occupancy and synchronization. Do not use blanket rules such as `if is bad`, `loops are bad`, `half is always faster` or `branchless is always faster`.

## Required context

Record Unity/engine version, render pipeline, Graphics API, target device/GPU, Shader Model, build type, resolution/render scale/MSAA, TAA/STP/upscaler, stage, screen coverage/overdraw, material/instance count, keyword combination and available profiler/compiler evidence.

## External contracts

Preserve Shader name, properties, keyword names/scopes, pass/LightMode, queue/type, render state, CBUFFER layout, textures/samplers, compute kernels, script property IDs, include APIs and Shader Graph custom-function signatures.

## Workflow

- Auditor is Read-only.
- Scanner output is candidate-only.
- Optimizer acts only on selected Rule ID findings.
- One patch tests one primary hypothesis.
- Before/After and revert conditions are mandatory.
- A change that breaks image quality, temporal stability, compatibility or variants is not an optimization.

## Unity/URP

Prefer RendererFeature, RenderQueue, Layer, ShaderTag, RendererList and existing pass reuse before adding a new LightMode pass. Keep `UnityPerMaterial` layout consistent. Respect RenderGraph handle lifetime, attachment format/sample compatibility, global-state restrictions, load/store/resolve cost and native-pass merging.

## Temporal data

Do not casually lower precision or resolution for motion vectors, depth, history UV, reprojection, disocclusion, reactive masks or temporal weights.

## Variants

Separate variant reduction from missing-variant prevention. Check runtime keywords, Addressables, AssetBundles, Resources, runtime-created materials and Strict Variant before stripping.
