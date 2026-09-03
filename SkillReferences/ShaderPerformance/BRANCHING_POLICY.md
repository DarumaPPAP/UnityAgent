# Unity Shader Branching Policy

## Purpose

Shader/HLSL の条件分岐を「static は常に正義」「dynamic は常に悪」と機械的に判断せず、実行コスト、wave divergence、register pressure、shader variant 数、compile/build time、memory、Player variant availability を同時に評価するための判断規約。

このPolicyは Unity / URP の Shader 実装・監査・最適化・レビューで適用する。

## Core decision

条件分岐を見つけたら、まず条件値を次の4種類へ分類する。

1. **Compile-fixed** — preprocessor / build target / pipeline 固定値。コンパイル時に不要Pathを除去できる候補。
2. **Material / draw-uniform** — Material Property、CBUFFER、draw 単位で同一と確認できる値。runtime branch候補。
3. **Spatially coherent runtime** — screen / tile / primitive / region 単位で近傍laneが同じ条件になりやすい値。dynamic branch候補。
4. **Lane-divergent runtime** — pixel/noise/random/per-lane dataなど、同一wave内で条件がばらつく値。dynamic branch高リスク。

分類できない場合は推測せず `UNKNOWN_BRANCH_UNIFORMITY` とする。

## Static branching

### Use when

- 条件が compile/build 時に確定する。
- branch body が十分重く、runtime branch costやworst-case register pressureを除去する価値がある。
- variant 数が bounded で、必要variantをPlayerへ確実に残せる。
- `clip` / `discard` や大きな非対称Pathを機能単位で完全除去する必要がある。

### Benefits

- 不要Pathをコンパイル結果から除去できる。
- runtime divergenceを発生させない。
- 条件判定命令を除去できる可能性が高い。
- feature-off variantでは重い処理やtemporaryを丸ごと消せる可能性がある。

### Costs

- `multi_compile` / `shader_feature` の組合せによるvariant増加。
- compile / import / build time増加。
- Player build size / runtime shader memory増加の可能性。
- stripping / Strict Variant Matching / Addressables / runtime keyword切替で必要variant欠落の危険。

**Static branchを採用するだけで「高速」と結論しない。variant costとPlayer availabilityも同じDecisionに含める。**

## Material / draw-uniform branching

Material parameterによるruntime branchは、対象値が本当に同一draw内でuniformであることを確認できる場合、variantを増やさず機能を切り替える有力候補とする。

### Prefer when

- feature組合せが多く、static variant化すると直積が大きくなる。
- branch body が小〜中規模。
- 同一draw内で条件が揃う。
- runtimeで値を切り替える必要がある。
- build size / compile time / variant governanceを優先したい。

### Do not assume uniformity when

- 条件が interpolator / texture / procedural value / screen-space data から来る。
- instancing等により同一draw内でinstanceごとに条件が変わり得る。
- Shader Graphや生成コード上で期待したdynamic branchになっていることを未確認。

Material Propertyという名前だけでlow-cost branchと断定せず、generated code と draw semantics を確認する。

## Runtime divergent branching

同一wave / warp内でlaneごとに条件Pathが分かれる場合、各Pathの実行がserial化・predicationされ、有効laneが減る可能性がある。

### High-risk examples

- noise / random / checker pattern を直接条件にする。
- pixel単位IDやtexture sample結果で重いPathを切り替える。
- laneごとにloop終了回数が大きく異なる。
- 非uniform flow内で derivative / implicit LOD sample を使う。

### Acceptable candidates

- 大きな連続領域で条件が揃う。
- off側でtexture sample、lighting、raymarch等の大きな処理をskipできる。
- screen coverage上、多数のwaveが同一Pathへ収束する。
- profileでbranchless版よりGPU timeが改善している。

## Decision order

Shader branchの設計・レビューでは次の順で判断する。

1. **Semantics** — 条件値はcompile-fixed / draw-uniform / coherent / divergentのどれか。
2. **Skipped work** — branchで実際に何命令、何sample、何loopをskipできるか。
3. **Divergence** — wave内でPathがどの程度分かれるか。
4. **Register pressure** — branch両Pathを含むworst-case temporary / occupancy影響。
5. **Variant pressure** — static化した場合のvariant直積、compile/build/memory影響。
6. **Player correctness** — stripping、runtime keyword、Strict Variant、Addressables等で必要variantが残るか。
7. **Evidence** — target Player / GPUでBefore/Afterを比較する。

## Preferred default

ユーザーまたはProject固有Policyが無い場合の既定判断は次とする。

- **小〜中規模のfeature toggleでdraw-uniform条件なら、まずMaterial/draw-uniform runtime branchを検討する。**
- **重いPathを完全除去する価値が高く、variant数をboundedに保てる場合のみstatic variantを優先候補へ上げる。**
- **lane-divergent runtime branchは、skipできる処理量とcoherenceを確認せず追加しない。**
- **branchless化も自動最適化扱いしない。両Pathの重い処理を常時実行するなら悪化し得る。**

これは「Material branchを常に採用する」という規則ではない。最終判断は対象GPUとPlayer evidenceで行う。

## `clip` / `discard`

`clip` / `discard` を含む機能は通常のALU branchと同一視しない。

- Early-Z / Hi-Z / tile efficiency / helper laneへの影響を確認する。
- feature全体を無効化できるならstatic variantで命令自体を除去する価値を検討する。
- ただしalpha-testとしてdiscardが本質的に必要なShaderを、性能だけを理由に削除しない。

## Variant guardrail

Static branchを提案する場合は必ず以下を報告する。

- keyword scope: local / global
- directive: `shader_feature*` / `multi_compile*`
- mutually-exclusive groupか独立booleanか
- 理論variant増加数
- runtime switch有無
- stripping strategy
- Strict Variant / AssetBundle / Addressables / remote content risk

Boolean keywordを増やす前に、mutually exclusive groupへの統合、local keyword、runtime draw-uniform branchの方が合理的でないか比較する。

## Review findings

以下をFindingとして扱う。

- `BRANCH-001`: Lane-divergent heavy branch
- `BRANCH-002`: Draw-uniform条件を不要なvariantへ分割しvariant直積を増やしている
- `BRANCH-003`: Heavy featureをruntime branchへ残しworst-case register / instruction pressureが高い
- `BRANCH-004`: Runtime切替が必要なfeatureをstrip可能なvariantとして扱っている
- `BRANCH-005`: `if`を機械的にbranchless化し両Pathの重い処理を常時実行している
- `BRANCH-006`: `clip` / `discard` featureをEarly-Z等の影響なしに通常branchとして評価している
- `BRANCH-007`: Material Propertyという理由だけでwave-uniformと断定している
- `BRANCH-008`: Branch最適化の効果をtarget Player evidenceなしに確定している

## Evidence contract

Performance claimは次を分離して報告する。

- Static source inspection
- Generated shader / compiler output inspection
- Editor profiling
- Player profiling
- Target-device GPU profiling
- Build / variant count / compile time evidence

Editor上の命令数や理論だけでSwitch / Console / Mobile GPUの勝敗を確定しない。

## Source rationale

このPolicyはユーザー提供ShaderMemoの中核である、静的分岐と動的分岐の区別、shader variantのruntime costとcompile/memory costのtrade-off、SIMT/wave内divergence、Material parameter branchをvariant抑制の候補として扱う指針を、UnityAgentの既存Variant/Runtime Evidence規約へ統合したもの。
