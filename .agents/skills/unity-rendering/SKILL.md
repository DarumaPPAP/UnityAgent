---
name: unity-rendering
description: Use when designing, implementing, investigating, or reviewing Unity 6 URP rendering work involving RenderGraph, ScriptableRendererFeature, RendererList, ShaderLab, HLSL, Compute Shader, cameras, depth, motion vectors, transparency, or render ordering. Applies rendering-specific contracts, preserves an approved Visual Intent when present, and delegates aesthetic direction to unity-visual-direction. Delegates shader audit, variant governance, and GPU evidence. Does not invent extra passes, cameras, controllers, debug systems, or beauty criteria outside the requested scope.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "2.3.0"
---

# Unity Rendering

Unity 6 URP、RenderGraph、RendererFeature、Shader/HLSLの作業へ、描画順、Resource、Shader契約、実機差を含む固有Gateを適用する。
このSkillはRendering境界を所有し、C#一般監査、GPU計測、美的方向性は専門Skillへ委譲する。

## When to use

- ScriptableRendererFeature / ScriptableRenderPass
- RenderGraph Raster / Compute / Unsafe Pass
- RendererList、FilteringSettings、ShaderTagId、RenderQueueRange
- Color / Depth / Motion Vector / History / GBuffer
- Transparent、Outline、Post Process、TAA / STP
- ShaderLab、HLSL、Compute Shader
- Camera Stack、Base / Overlay、Output Texture
- RenderingのEditor / Player / Platform差

美しいScene、Composition、Lighting mood、Color script、Look Development、Hero Shotの定義自体は`unity-visual-direction`をPrimaryにする。

## Required references

対象に応じて必要なものだけを読む。

1. Feature Spec / Plan / Task
2. 対象Renderer、Shader、RendererFeature、Project Settings等の直接Sourceと検出済みProject Fact
3. 必要なProject Factが未解決の場合だけ`Specs/ProjectProfile.md`をFallbackとして読む
4. 美的成果を含む場合は承認済みVisual Intent Contractと`SkillReferences/BEAUTIFUL_DEFINITION_INTEGRATION.md`
5. `SkillReferences/RENDERING_STANDARDS.md`
6. `SkillReferences/SHADER_PERFORMANCE_STANDARDS.md`
7. Shader変更時は`SkillReferences/ShaderPerformance/UNITY_URP_POLICY.md`
8. Shaderに条件分岐、keyword、feature toggle、`clip` / `discard`が含まれる場合は`SkillReferences/ShaderPerformance/BRANCHING_POLICY.md`
9. 監査時は`SHADER_REVIEW_GATE.md`と`RULE_CATALOG.md`
10. 修正時は`REFACTOR_POLICY.md`
11. Variant変更時は`VARIANT_POLICY.md`

`Specs/ProjectProfile.md`はFallbackであり、対象Projectから検出したUnity/URP/Renderer/Platform Factや今回ユーザーが確認したFactを上書きしない。

## Delegates to

- Visual direction、Beauty definition、Visual Intent、Beauty Review: `unity-visual-direction`
- Shader/HLSL Read-only監査: `shader-performance-auditor`
- Confirmed Shader Finding修正: `shader-performance-refactor`
- Keyword / Variant / Strip: `unity-shader-variant-governor`
- GPU Before/After: `shader-runtime-evidence`
- 原因未確定の描画破綻: `unity-incident-investigation`
- Task実装: `unity-implement`
- 受入レビュー: `unity-review`

## Step 1 — Resolve the rendering context

- Unity / URP / Core RP package version
- Renderer type and Renderer Data
- Forward / Forward+ / Deferred
- RenderGraph or Compatibility mode
- Camera type and stack
- XR、MSAA、HDR、Dynamic Resolution、STP/TAA
- Target Platform and graphics API
- Editor / Player / Development / Release
- Existing RenderFeature order
- 美的成果を含む場合はSelected Definition IDとVisual Intent Contract

これらは対象Projectの直接Sourceと検出済みFactを先に使い、不足する項目だけProject Profileで補う。
APIとpackage versionを確認せず、別Versionの実装を移植しない。
Visual Intentが必要なのに未定義の場合、Rendering側で勝手に「美しい」を補完せず`unity-visual-direction`へ戻す。

## Step 2 — Declare the pass contract

各Passで次を明示する。

- Purpose
- Injection point / `RenderPassEvent`
- Camera eligibility
- Filtering: Queue、Layer、Rendering Layer、ShaderTag
- Inputs
- Outputs
- Color attachments
- Depth attachment
- Read / write access
- Load / Store behavior
- Clear behavior
- MSAA / format / dimension
- Global state requirements
- Resource creator, owner, lifetime
- Consumers after the pass

Passが何を読むか、何を上書きするか、後段が何を期待するかを曖昧にしない。

## Step 3 — Confirm draw selection semantics

- `RenderQueueRange.opaque` / `transparent`
- `SortingCriteria.CommonOpaque` / `CommonTransparent`
- `ShaderTagId`と対象Passの`LightMode`
- LayerMask / RenderingLayerMask
- RendererListの対象Renderer
- Override Material / Override Shaderの置換範囲
- RenderStateBlock

Override Materialは元ShaderへPassを追加する機構として扱わない。
対象Queue、ShaderTag、Passが一致しないRendererは描画されないことを前提にする。

## Step 4 — Confirm attachment and resource correctness

- Color / Depthのsize、sample、format整合
- DepthStencilFormat
- TextureHandleの有効範囲
- Pass外での未初期化Handle使用
- Global texture設定とGlobal State許可
- Import / transient / persistent resource
- Historyのdouble bufferingとreset条件
- Camera stacking / Output Textureの経路

RenderGraphとCompatibility APIを同じ実装経路へ混在させない。

## Step 5 — Confirm shader, branching, and render-state contracts

- Shader name
- Properties and defaults
- CBUFFER layout / SRP Batcher
- Keywords and local/global scope
- Pass Name / LightMode
- Cull / ZWrite / ZTest / Blend / ColorMask / Stencil
- RenderQueue and material override behavior
- Instancing / DOTS / GPU Driven compatibility
- MotionVectors、DepthOnly、ShadowCaster
- Precision-sensitive values
- Branch condition classification: compile-fixed / draw-uniform / spatially-coherent runtime / lane-divergent runtime
- Static variant化した場合のvariant pressure / build cost / Player availability
- Dynamic branchの場合のskipped work / divergence / worst-case register pressure
- `clip` / `discard`がある場合のEarly-Z / Hi-Z / tile impact

Shader名、Property、Keyword、Pass、LightMode、RenderStateを依頼なしで変更しない。
Visual Intentを実現するためでも、互換性契約を無断変更しない。必要なTrade-offは人間判断へ渡す。

Shaderの`if`を見つけただけで静的分岐へ変換せず、逆にbranchless化もしない。Material/draw-uniform branch、static variant、coherent dynamic branchを`BRANCHING_POLICY.md`のDecision orderで比較し、性能主張はtarget Player / GPU evidenceまで分離して扱う。

## Step 6 — Handle transparency and ordering explicitly

Transparentでは次を必ず確認する。

- Queue and sorting
- ZWrite and depth prepass assumptions
- Blend mode and premultiplication
- Backface / double-sided rendering
- Overdraw and full-screen coverage
- Outlineなど背面描画Pass
- Motion Vector participation
- Post-process and low-resolution composition order

`CommonTransparent`のback-to-front順序を壊す設計は、視覚的正しさとOverdrawのトレードオフを明示する。

## Step 7 — Handle temporal data explicitly

TAA / STP / temporal effectでは次を定義する。

- Motion vector source
- Current / previous transform
- Jittered / non-jittered matrices
- History UV
- Disocclusion rejection
- Reactive mask
- Transparent and outline behavior
- Camera cut / resolution change / quality change reset

Depth、Motion Vector、History UV、Reprojection、Disocclusionを安易に低精度化しない。

## Step 8 — Separate audit, patch, and evidence

1. Context Resolution
2. Read-only Audit
3. Branch / Variant Audit
4. Runtime Evidence plan
5. Safe Refactor
6. Review Gate

一つのPatchにつき主要仮説は一つにする。
性能変更はBefore/AfterとRevert条件を持つ。
美的評価は`unity-visual-direction`のBeauty gateへ委譲し、CompileやGPU evidenceと混ぜない。

## Output contract

- Rendering context
- Visual taskではSelected Definition IDと保持したVisual Intent
- Pass contract
- Draw selection conditions
- Resource ownership and lifetime
- Shader / RenderState compatibility
- Branch classification and branch-vs-variant decision
- Variant count / Player availability risk when applicable
- Changed or inspected files
- Static findings and confidence
- Validation performed
- Player / target-device evidence status
- Visual acceptance statusはHuman review未実施なら未承認
- Revert condition

## Scope — what this Skill does not do

- 仕様外のCamera Stack、XR、HDRP対応を追加しない。
- Hidden Shader、追加Pass、Controller、Debug UIを勝手に作らない。
- Shaderの`if`、`loop`、`half`、`discard`を一律禁止しない。
- static branch、dynamic branch、branchless、Material branchのいずれかを一律で最適解としない。
- Scanner結果だけでGPU問題を確定しない。
- Editor結果だけでSwitchやConsole実機を保証しない。
- 美的Definitionを作成または変更しない。
- Feature数、Light数、Bloom、Fog、Emissionを美しさとして採点しない。
- Human reviewなしに`VISUAL_ACCEPTED`としない。

## Checklist

- [ ] Unity / URP / Platform条件を対象ProjectのFactから先に確認した
- [ ] Project Profileを使用した場合は未解決FactのFallbackとしてのみ使用した
- [ ] Visual taskではDefinition IDとVisual Intentを確認した
- [ ] Passの入出力とInjection pointを定義した
- [ ] Queue / Layer / ShaderTag / Sortingを確認した
- [ ] AttachmentとResource lifetimeを確認した
- [ ] Shader / Keyword / Pass / RenderState契約を確認した
- [ ] Shader branchをcompile-fixed / draw-uniform / coherent / divergentへ分類した
- [ ] static variantとruntime branchの双方についてruntime costとvariant/build costを比較した
- [ ] `clip` / `discard`を通常ALU branchと同一視していない
- [ ] TransparentまたはTemporal固有条件を確認した
- [ ] Audit、Patch、Evidenceを分離した
- [ ] Beauty gateとTechnical gateを混同していない
- [ ] 未実施の実機確認とHuman reviewを明記した

## Common mistakes

- Project Profileの固定値で検出済みRendererやPipeline Factを上書きする。
- `RenderQueueRange.opaque`でTransparent対象を落とす。
- Override Materialが元Shaderへ追加Passを足すと誤解する。
- Outlineを無効化しても背面描画Pass自体が走り続ける状態を見逃す。
- Depth attachmentのsample/format不一致でRenderGraph errorを起こす。
- Pass内Global State設定を許可せず`SetGlobalTexture`する。
- Motion VectorをForwardLitだけへ追加し、Outlineや追加描画を履歴から漏らす。
- Material Propertyというだけでwave-uniformと断定する。
- `if`を見つけただけでvariant化、またはbranchless化する。
- variant削減だけを見てruntime divergenceを悪化させる。
- runtime branch削除だけを見てvariant explosionを起こす。
- EditorのFrame Debuggerだけで実機VariantやGPU時間を保証する。
- Visual IntentなしにLight、Bloom、Fog、Reflectionを追加して美しさを作ろうとする。
- Compile成功やCapture生成を美的完成と誤認する。
