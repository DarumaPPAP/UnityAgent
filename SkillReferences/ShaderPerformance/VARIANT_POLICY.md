# Unity Shader Variant Policy

## Classification

- Build-fixed: determined by target or pipeline; usually strip candidates.
- Material-fixed: stored on Material and not changed at runtime; `shader_feature_local` candidate.
- Runtime-switchable: changed by script, animation, volume or quality; required variants must remain in Player.
- Pass-limited: used only by vertex/fragment/etc.; stage suffix requires backend support review.

## Branch-vs-variant decision

Keyword化は最適化の既定解ではない。`SkillReferences/ShaderPerformance/BRANCHING_POLICY.md`を適用し、条件値を compile-fixed / draw-uniform / spatially-coherent runtime / lane-divergent runtime に分類してから判断する。

- draw-uniformな小〜中規模feature toggleは、variant直積を避けられるruntime branchも必ず比較する。
- heavy pathを完全除去する価値が高く、variant数をboundedに保てる場合はstatic variantを優先候補へ上げる。
- lane-divergent runtime branchをvariant削減だけを理由に採用しない。
- static variantをruntime instruction削減だけを理由に採用しない。compile/build time、memory、stripping、Player availabilityを同時に確認する。
- `clip` / `discard`を含むfeatureはEarly-Z / Hi-Z / tile影響を含めて別途評価する。

## Reduction order

1. Disable unused URP features.
2. Remove genuinely unused passes.
3. Prefer local over global keywords.
4. Add stage scope where supported.
5. Separate material-fixed from runtime-switchable options.
6. Compare draw-uniform runtime branch against introducing another independent keyword.
7. Combine mutually exclusive options into one group.
8. Apply evidence-based `IPreprocessShaders` stripping.
9. Preserve required variants explicitly.

## Required reporting when adding a keyword

- local / global scope
- `shader_feature*` / `multi_compile*`
- independent boolean or mutually-exclusive group
- theoretical variant multiplier
- runtime switchability
- stripping behavior
- Strict Variant / Addressables / AssetBundle / remote content risk
- why a draw-uniform runtime branch was rejected, when applicable

Do not strip runtime-created materials, Addressables, AssetBundles, remote content, script-switched keywords, quality-switched keywords, RendererFeature-required passes, MotionVectors/Depth/Shadow/Meta or Strict Variant combinations without proof.
