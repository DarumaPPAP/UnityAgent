---
name: shader-runtime-evidence
description: Shader最適化のBefore/Afterを対象実機で再現可能に計測し採否を判断する。
metadata:
  version: "1.0.0"
---

# Shader Runtime Evidence

Fix scene, camera, animation time, resolution, render scale, MSAA, quality, URP asset, TAA/STP/upscaler, build, API, device and keyword combination. Measure GPU time and available register/spill/occupancy/bandwidth/wave/overdraw data. Compare image difference, motion vectors, depth and temporal stability. Return Adopt, Rework, Revert or Inconclusive. Do not infer unavailable metrics.
