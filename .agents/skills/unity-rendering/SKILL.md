---
name: unity-rendering
description: Unity 6 URP、RenderGraph、RendererFeature、Shader、HLSL、Compute Shaderの設計・実装へ描画固有制約を適用する。
---

# Unity Rendering

1. Read feature Spec, Plan and Project Profile.
2. Read `SkillReferences/RENDERING_STANDARDS.md` and `SHADER_PERFORMANCE_STANDARDS.md`.
3. Confirm Unity/URP/API/target device and existing code.
4. Declare pass inputs, outputs, timing, camera resources and GPU-resource lifetime.
5. Do not mix Compatibility and RenderGraph APIs.
6. For performance questions, run `shader-performance-auditor` before refactor.
7. For keywords/stripping, use `unity-shader-variant-governor`.
8. For claimed gains, use `shader-runtime-evidence`.
9. Avoid unrequested Camera Stack, XR, HDRP, Hidden Shader, Controller or Debug UI.
