# Unity Shader Variant Policy

## Classification

- Build-fixed: determined by target or pipeline; usually strip candidates.
- Material-fixed: stored on Material and not changed at runtime; `shader_feature_local` candidate.
- Runtime-switchable: changed by script, animation, volume or quality; required variants must remain in Player.
- Pass-limited: used only by vertex/fragment/etc.; stage suffix requires backend support review.

## Reduction order

1. Disable unused URP features.
2. Remove genuinely unused passes.
3. Prefer local over global keywords.
4. Add stage scope where supported.
5. Separate material-fixed from runtime-switchable options.
6. Combine mutually exclusive options into one group.
7. Apply evidence-based `IPreprocessShaders` stripping.
8. Preserve required variants explicitly.

Do not strip runtime-created materials, Addressables, AssetBundles, remote content, script-switched keywords, quality-switched keywords, RendererFeature-required passes, MotionVectors/Depth/Shadow/Meta or Strict Variant combinations without proof.
