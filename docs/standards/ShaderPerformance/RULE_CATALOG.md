# Shader Performance Rule Catalog

Rule IDは固定する。既存IDを変更しない。

## EXEC: 実行頻度と重複処理

### EXEC-001 Fragmentで不変値を再計算

**症状:** Object、Material、Draw、Vertex単位で不変な値をFragmentごとに計算する。

**リスク:** Fragment Invocation数がVertex数やDraw数を大きく上回る場合、演算が増幅する。

**確認:** Screen Coverage、Overdraw、MSAA、Stereo、Render Scale。

**修正候補:** CPU、Material Constant、Vertex、Bakeへ移動。ただし補間誤差と精度を確認する。

### EXEC-002 重複Normalize / Basis再構築

**症状:** 同じVectorを複数回Normalizeする。同じTBNを複数回組み立てる。

**リスク:** ALU / SFUとTemporary Register増加。

**例外:** 値が途中で変化する、補間後の再正規化が必要、CompilerがCSEする場合。

### EXEC-003 Hot Pathの高コスト関数

**対象:** `sin`、`cos`、`tan`、`asin`、`acos`、`atan`、`pow`、`exp`、`log`、`sqrt`。

**リスク:** SFU Throughputまたは複数命令へ展開。

**修正候補:** 代数簡略化、近似、Recurrence、LUT、低頻度Stageへ移動。

**注意:** LUTはMemory BandwidthとCacheを消費する。

### EXEC-004 定数指数のpow

**症状:** `pow(x, 2)`、`pow(x, 4)`など。

**修正候補:** Semantic差を許容できる場合は乗算へ置換。

**判定:** Compilerが既に最適化する可能性があるため、Generated Codeまたは計測を確認する。

### EXEC-005 結果がゼロと確定後も重い処理を続行

**症状:** Mask、Opacity、Attenuation、Tile Classificationで寄与がないのにTexture SampleやLightingを実行。

**修正候補:** Coherent Early Exit、Stencil、Tile Classification、Specialized Pass。

### EXEC-006 巨大Uber Shader

**症状:** 無関係な機能と大きな非対称Branchを1つのProgramへ集約。

**リスク:** Worst-case Register、Instruction Cache、Compile時間、Variant複雑化。

**修正候補:** 意味のある少数VariantまたはPass分類。無制限Permutationは禁止。

## FLOW: 分岐と発散

### FLOW-001 Lane-divergent Branch

**症状:** Wave / Warp内でConditionが不規則に変化。

**高リスク:** Noise、Pixel単位Material ID、Checker Pattern、Random Data。

**低リスク:** 大きな連続領域、Draw-uniform、重い処理を大幅にSkipするEarly Exit。

### FLOW-002 非対称Branch

**症状:** 片側だけ高コスト、Temporaryが多い。

**リスク:** Cheap PathでもWorst-case Register Allocationの影響を受ける可能性。

### FLOW-003 機械的Branchless化

**症状:** `if`を無条件に`lerp`、Mask、Arithmeticへ変更。

**リスク:** 両Pathの重い処理を全Lane実行する。

### FLOW-004 Branch Hintの乱用

**対象:** `[branch]`、`[flatten]`、`UNITY_BRANCH`、`UNITY_FLATTEN`。

**原則:** Hintは実験として扱い、正しさの制御に使わない。

### FLOW-005 Divergent Loop Exit

**症状:** LaneごとにLoop回数や終了条件が異なる。

**リスク:** 最も遅いLaneが終わるまでWaveが継続。

**修正候補:** Bucket、Compaction、Fixed Upper Bound、Separate Dispatch。

### FLOW-006 非Uniform Flow内のDerivative

**対象:** `ddx`、`ddy`、Implicit LOD Sample。

**リスク:** Derivative不安定、LOD誤り、Helper Lane負荷。

**修正候補:** Branch前にDerivative計算、Explicit Gradient / LOD。

## REG: レジスタ圧とOccupancy

### REG-001 長寿命Temporary

**症状:** 早く宣言し、かなり後で使用。

**修正候補:** Scopeを狭め、最初の使用直前で定義。

### REG-002 大きなLocal Array / Struct

**リスク:** Register爆発またはScratch / Local Memory Spill。

### REG-003 過剰Unroll

**利点:** Loop制御削減、最適化機会増加。

**欠点:** Code Size、Instruction Cache、Live Temporary、Spill増加。

### REG-004 過剰Inlining / 巨大Function

**リスク:** Live RangeとRegister Allocationが増える。

### REG-005 全値を32-bitで保持

**リスク:** Native 16-bit対応GPUではRegisterとBandwidthを余計に使用。

**Precisionを下げない対象例:** World Position、大きなUV Domain、Depth Reconstruction、Motion Vector、Temporal History、数値不安定な演算。

### REG-006 大きな引数 / Return Struct

**リスク:** Move、Inlining Pressure、Live Value増加。

### REG-007 大きなRay / Mesh / Task Payload

**リスク:** Thread単位Storage増加とOccupancy低下。

## MEM: Texture、Buffer、Cache

### MEM-001 重複Texture Sample

**条件:** Texture、Sampler、UV、LOD、Gradientが同一。

**修正候補:** Sample結果を再利用。ただしCompiler CSEとTexture Side Effectを確認。

### MEM-002 不要Channel / Format

**症状:** RGBAを読むが1Channelしか使わない。過剰精度Formatを使用。

**修正候補:** Texture Packing、Format縮小、Compression。ただし品質とPlatform対応を検証。

### MEM-003 Incoherent Read

**症状:** Laneごとに遠いAddress、Random Index。

**リスク:** Cache Miss、Memory Transaction増加。

### MEM-004 Buffer Stride / Alignment不良

**症状:** 不自然なStruct Layout、Padding、非整列Access。

**リスク:** 追加Transaction、Backend差異。

### MEM-005 UAV / Atomic集中

**リスク:** Serialization、Contention、Cache Flush。

**修正候補:** Group Shared集約、Prefix Sum、分割Dispatch、Atomic回数削減。

### MEM-006 過剰Barrier

**リスク:** Wave / Thread Group待機。

### MEM-007 Shared Memory過剰

**リスク:** Group数制限、Occupancy低下、Bank Conflict。

### MEM-008 不要Intermediate RenderTexture

**リスク:** Allocation、Bandwidth、Resolve、Store / Load増加。

## RASTER: Raster、Depth、Blend、Overdraw

### RASTER-001 Transparent Overdraw

**症状:** 大面積、Layer多数、Particle重なり。

**リスク:** Depth Rejectionが効きにくく、BlendとShaderが重複実行。

**修正候補:** Bounds、Particle Count、Soft Particle範囲、Downscale、Layer分類、Mesh形状改善。

### RASTER-002 Alpha TestとEarly-Z

**症状:** `clip` / `discard`を多用。

**注意:** 不要Pixelを除外できる一方、Early-Z、Tile効率、Quad実行に影響する場合がある。

### RASTER-003 Fragment Depth Write

**対象:** `SV_Depth`。

**リスク:** Early-Z制約、Hi-Z効率低下。

### RASTER-004 Small Triangle

**症状:** 1〜数Pixel以下のTriangleが大量。

**リスク:** Quad Utilization低下、Raster Setup増加、Overdraw増加。

### RASTER-005 Interpolator過多

**リスク:** Bandwidth、Register、Platform Limit。

**修正候補:** Pack、再構築、不要Varying削除。ただしFragment再計算とのトレードオフを測る。

### RASTER-006 Fullscreen Passの連鎖

**リスク:** 解像度に比例するBandwidthとFragment実行。

**修正候補:** Pass統合、低解像度化、Tile / Compute化、必要領域限定。

### RASTER-007 Depth Prepassの誤用

**注意:** Overdraw削減に効く場合がある一方、Geometryを二重描画するためCPU / Vertex負荷が増える。

## PREC: 精度

### PREC-001 half化による範囲不足

**症状:** Large Coordinate、Depth、指数、累積、Temporal Dataを16-bit化。

**リスク:** Overflow、Underflow、Banding、Jitter、Ghosting。

### PREC-002 Precision MixによるConversion増加

**症状:** half / float間の頻繁な変換。

**リスク:** BackendによってConvert命令とRegister増加。

### PREC-003 Normal / Colorのみ安全域

**候補:** Normalized Vector、LDR Color、Mask、限定範囲係数。

**条件:** 対象GPUのNative 16-bit対応と誤差検証。

## LOOP: Loopと反復

### LOOP-001 Compile-time固定小Loop

**候補:** UnrollでOverhead削減可能。

**注意:** Compilerが既にUnrollする場合がある。

### LOOP-002 大Loopの全Unroll

**リスク:** Code Size、Compile時間、Instruction Cache、Register Pressure。

### LOOP-003 Fragment内の可変回数探索

**例:** Ray March、Parallax、Blur、Light Loop。

**修正候補:** Adaptive Step、Hierarchical Search、Temporal Reuse、Tile Classification、Quality Tier。

### LOOP-004 早期終了が不規則

**リスク:** Divergence。

**評価:** 平均StepだけでなくWave内最大Stepを見る。

## COMP: Compute Shader

### COMP-001 Thread Group Size不整合

**症状:** Wave Size、Data Tile、Hardware Limitと不整合。

**リスク:** Idle Lane、Occupancy低下、Boundary処理増加。

### COMP-002 Bounds Checkの全Thread実行

**注意:** 安全性に必要。Dispatch Sizeを丸めるか、Coherent Checkにする。

### COMP-003 Group Shared Bank Conflict

**症状:** 同一Bankへ集中。

### COMP-004 Group Shared使用量過多

**リスク:** Resident Group数低下。

### COMP-005 Global Synchronizationを1Dispatchで実現しようとする

**リスク:** 正しさの破綻または過剰Atomic。

**修正候補:** Dispatch分割。

## UNITY: Unity固有

### UNITY-001 Shader Graph Branch誤認

Shader Graph Branchは通常、両Inputを評価してSelectする。実Branchを期待する場合はGenerated Codeを確認する。

### UNITY-002 Global Keyword乱用

**リスク:** Project全体Keyword Space、Variant増加、意図しない連動。

### UNITY-003 multi_compileの無制限追加

**リスク:** Variant直積増加。

### UNITY-004 Runtime切替Keywordをshader_feature化

**リスク:** Build時に未使用と判断され、実機でVariant欠落。

### UNITY-005 SRP Batcher破壊

**症状:** `UnityPerMaterial` CBUFFER不一致、Material Property配置差。

### UNITY-006 Pass / LightModeの無断追加

**リスク:** Draw Call、Variant、Render順、Build負荷増加。

### UNITY-007 RenderStateの性能事故

**対象:** Blend、ZWrite、ZTest、ColorMask、Stencil、Cull、Queue。

### UNITY-008 EditorとPlayerのVariant差

**リスク:** Editor正常、Player Pink / Fallback / Incorrect Pass。

### UNITY-009 Strict Variant事故

**症状:** 実機だけ必要Variantがなく描画不正。

### UNITY-010 Platform Macroの分岐肥大

**リスク:** 保守性低下、検証漏れ、Variant / Program分裂。
