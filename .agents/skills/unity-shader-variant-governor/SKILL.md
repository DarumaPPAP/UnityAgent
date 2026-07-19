---
name: unity-shader-variant-governor
description: Unity Shader Keyword、Variant、URP Strip、SVC、Strict Variant、Runtime切替を監査する。
metadata:
  version: "1.0.0"
---

# Unity Shader Variant Governor

1. Inventory pragmas and keyword scopes.
2. Classify build-fixed, material-fixed, runtime-switchable and pass-limited keywords.
3. Calculate source-level Cartesian products.
4. Check URP assets, materials, RendererFeatures, Addressables, AssetBundles, Resources and runtime creation.
5. Separate reduction candidates from missing-variant risks.
6. Verify Strict Variant combinations.
7. Follow `VARIANT_POLICY.md`; never strip from Editor usage alone.
