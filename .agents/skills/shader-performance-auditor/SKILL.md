---
name: shader-performance-auditor
description: ShaderLab、HLSL、Compute Shaderの性能リスクを証拠ベースで監査する。
metadata:
  version: "1.0.0"
---

# Shader Performance Auditor

Read `RULE_CATALOG.md`, `ARCHITECTURE_MATRIX.md`, `UNITY_URP_POLICY.md`, `SEVERITY_MODEL.md` and `AUDIT_OUTPUT_TEMPLATE.md`.

Record environment, dependencies, stage and execution frequency. Distinguish compile-time, draw-uniform, wave-uniform, coherent and lane-divergent flow. Review bandwidth, cache, register pressure, occupancy, spills, overdraw, barriers, atomics, precision and variants. Classify each finding as Confirmed, High confidence or Measurement required. Scanner output is candidate-only.
