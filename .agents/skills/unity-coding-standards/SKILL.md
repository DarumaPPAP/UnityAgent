---
name: unity-coding-standards
description: Unity C#実装へ命名、API互換性、IL2CPP、Burst/Jobs、Allocation、例外、async規約を適用する。
---

# Unity Coding Standards

Read `SkillReferences/CODING_STANDARDS.md`, `ARCHITECTURE_STANDARDS.md` and C# anti-pattern policy before implementation or review.

Resolve environment and call frequency first. Preserve public APIs and serialized contracts. Avoid hidden static lifetime, blocking async, swallowed exceptions, unmeasured hot-path rewrites and unsupported AOT/reflection assumptions. For Shader/HLSL work, delegate to `unity-rendering` and the Shader Performance skills rather than applying C# rules directly.
