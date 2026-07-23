---
name: shader-performance-auditor
description: Use when reviewing ShaderLab, HLSL, Compute Shader, or Shader Graph custom code without modifying files for GPU performance risks such as divergence, overdraw, bandwidth, cache behavior, register pressure, occupancy, spills, barriers, atomics, precision, or variant growth. Produces evidence-ranked findings and measurement requirements. Does not apply refactors or treat source patterns as measured GPU cost.
allowed-tools:
  - Read
metadata:
  version: "2.0.0"
---

# Shader Performance Auditor

ShaderLab、HLSL、Compute ShaderをRead-onlyで監査し、静的に確定できる問題とGPU計測が必要な問題を分離する。

## When to use

- Shaderの負荷要因を監査したい
- `if`、`loop`、`discard`、precision、Texture sampleの判断
- Fragment / Vertex / Computeのボトルネック候補整理
- 修正前にRule IDと計測条件を確定したい

描画順、RendererFeature、RenderGraphの問題は`unity-rendering`を併用する。修正は`shader-performance-refactor`へ渡す。

## Required references

対象に応じて読む。

- `RULE_CATALOG.md`
- `ARCHITECTURE_MATRIX.md`
- `UNITY_URP_POLICY.md`
- `SEVERITY_MODEL.md`
- `AUDIT_OUTPUT_TEMPLATE.md`

## Workflow

1. Unity、URP、Platform、graphics API、Shader stage、Pass、Queueを確定する。
2. 呼び出し頻度、画面占有率、頂点数、dispatch size、overdraw条件を確認する。
3. compile-time、draw-uniform、wave-uniform、coherent、lane-divergent flowを分ける。
4. Texture/Buffer帯域、cache locality、sample count、formatを確認する。
5. register pressure、occupancy、spill候補を確認するが、compiler/disassemblyなしで確定しない。
6. barrier、atomic、wave operation、group sizeを対象GPU条件で評価する。
7. precisionを値域、補間、temporal data、platform supportから評価する。
8. Keyword、Pass、Variant増加を`unity-shader-variant-governor`へ委譲する。
9. FindingをConfirmed / High confidence / Measurement requiredに分類する。

Scanner出力は候補に留め、確定診断にしない。

## Output contract

各Findingに次を含める。

- Rule ID
- Shader / file / stage / pass / location
- Trigger condition
- Evidence
- Confidence
- Expected GPU mechanism
- Visual or compatibility risk
- Minimal proposal
- Required measurement
- Safe / Review Required / Manual Only

## Scope — what this Skill does not do

- ファイルを変更しない。
- `if`、`loop`、`half`、`discard`を一律禁止しない。
- ソース行数や命令予想だけでGPU時間を断定しない。
- 生成されたShader Graphコードを直接修正しない。
- 画質や外部Shader契約の変更を提案なしで行わない。

## Checklist

- [ ] Platform、stage、Pass、実行頻度を確認した
- [ ] divergenceのuniformityを分類した
- [ ] bandwidth、register、overdraw、variantを分離した
- [ ] 静的確定と計測必要を分けた
- [ ] FindingへRule IDと条件を付けた
- [ ] ファイルを変更していない

## Common mistakes

- 分岐があるだけで遅いと断定する。
- Fragment負荷を画面占有率やOverdrawなしで評価する。
- `half`化をMotion Vector、Depth、Historyへ適用する。
- register pressureをソース変数数だけで確定する。
- Variant問題をShader ALU最適化として扱う。
