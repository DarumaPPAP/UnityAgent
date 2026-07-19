---
name: shader-performance-refactor
description: 監査済みShaderへ外部互換性と画質を維持した小さな最適化差分を適用する。
metadata:
  version: "1.0.0"
---

# Shader Performance Refactor

Require a Rule ID, selected target and measurable Before state. Read `REFACTOR_POLICY.md` and `SHADER_REVIEW_GATE.md`. List external contracts, change one hypothesis, compile, verify material/keyword/pass compatibility, compare images and GPU evidence, then record revert conditions. Do not perform unreviewed redesign or permanently edit generated Shader Graph code.
