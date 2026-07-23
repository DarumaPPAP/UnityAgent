---
name: shader-runtime-evidence
description: Use when deciding whether a Shader, RendererFeature, RenderGraph, transparency, temporal, or GPU optimization change should be adopted from reproducible Before/After captures on the target platform. Fixes rendering conditions, compares GPU and image evidence, and returns Adopt, Rework, Revert, or Inconclusive. Does not infer unavailable register, occupancy, bandwidth, or device metrics.
allowed-tools:
  - Read
metadata:
  version: "2.0.0"
---

# Shader Runtime Evidence

ShaderまたはRendering変更を、固定された描画条件と対象実機のBefore/Afterから採否判定する。

## Required conditions

- Scene and camera
- Animation time / camera path
- Resolution / render scale
- MSAA / HDR / quality
- URP Asset / Renderer Data
- TAA / STP / upscaler
- Build / graphics API / device
- Shader keyword and material combination
- Warm-up / capture window / sample count
- Before and After commit

## Workflow

1. 比較条件を固定し、対象変更以外の差分を除く。
2. GPU frame/pass timeを計測する。
3. 利用可能な場合のみregister、spill、occupancy、bandwidth、wave、overdrawを読む。
4. Image difference、Depth、Motion Vector、Temporal stabilityを比較する。
5. Transparent、Outline、Shadow、DepthOnly、MotionVectorsなど関連Passの回帰を確認する。
6. 平均だけでなくframe varianceとspikeを確認する。
7. Adopt / Rework / Revert / Inconclusiveを返す。

## Decision contract

- **Adopt** — 目標を満たし、画質・互換性回帰が許容内。
- **Rework** — GPU改善はあるが画質、安定性、目標値に問題がある。
- **Revert** — GPU悪化、描画破綻、契約破壊がある。
- **Inconclusive** — 条件差、capture不足、device metric不足、noiseが大きい。

## Output contract

- Fixed rendering conditions
- Before / After artifacts
- GPU metrics and sample count
- Image / Depth / Motion Vector / temporal comparison
- Platform limitations
- Decision and confidence
- Required next evidence
- Revert condition

## Scope — what this Skill does not do

- 未取得metricを推測しない。
- Editor GPU時間をTarget Console結果として扱わない。
- 異なるResolution、Quality、KeywordのCaptureを直接比較しない。
- ソース命令予想を実測値の代わりにしない。

## Checklist

- [ ] Scene、Camera、Resolution、URP設定を固定した
- [ ] Build、API、Device、Keywordを固定した
- [ ] Warm-upとsample countを記録した
- [ ] GPUと画質・Temporal回帰を両方確認した
- [ ] unavailable metricを推測していない
- [ ] 判定とRevert条件を記録した

## Common mistakes

- AfterだけGPU CaptureしてBeforeを推測する。
- Camera位置やanimation timeが異なる。
- Render ScaleやSTP設定の差を見逃す。
- GPU時間改善とMotion Vector破綻を別問題として無視する。
- 一つのPC GPU結果でSwitch実機採用を決める。
