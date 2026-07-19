---
name: unity-fix-errors
description: Unityのコンパイル、RenderGraph、Shader、Variant、実機エラーを原因ベースで修正する。
---

# Unity Fix Errors

- Reproduce and identify the first causal error, not downstream noise.
- Preserve API, serialization, Shader and rendering contracts unless explicitly approved.
- Do not hide Variant errors by collecting everything into SVC or disabling Strict Variant.
- Do not invent include functions or delete MotionVectors/Depth just to compile.
- Do not work around RenderGraph errors with unnecessary copy passes before checking resource declarations, formats and sample counts.
- Distinguish Editor-only success from Player/IL2CPP/target-device success.
- After the minimal fix, report cause, change, compatibility impact and required validation.
