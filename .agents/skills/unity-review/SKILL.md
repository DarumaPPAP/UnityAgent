---
name: unity-review
description: Unity C#、Rendering、Shader変更を仕様・互換性・実測証拠からレビューする。
---

# Unity Review

- Read project profile, feature spec and relevant standards.
- Separate correctness, compatibility, performance and maintainability findings.
- Use C# anti-pattern audit for C# and shader-performance-auditor for Shader/HLSL.
- Verify public API, serialization, Prefab/Scene, save data, Shader properties, keywords, passes and render state.
- Require Player/IL2CPP or target-device evidence where relevant.
- Do not approve performance claims without Before/After conditions and revert criteria.
