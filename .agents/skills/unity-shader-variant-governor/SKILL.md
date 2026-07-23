---
name: unity-shader-variant-governor
description: Use when auditing or changing Unity Shader keywords, variant counts, URP stripping, Shader Variant Collections, Strict Variant behavior, runtime keyword switching, or platform-only missing-variant failures. Separates safe reduction candidates from required runtime combinations and produces a verified variant policy. Does not strip combinations from Editor usage alone or modify unrelated shader visuals.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "2.0.0"
---

# Unity Shader Variant Governor

Unity Shader Keyword、Variant、URP Strip、SVC、Strict Variant、Runtime切替を、実際のAssetとBuild経路から管理する。

## When to use

- `Shader variant not found`
- Strict Variantで実機だけ失敗する
- Variant数を削減したい
- local/global keyword、multi_compile、shader_featureを見直す
- SVC、Warmup、IPreprocessShaders、URP strippingを扱う

ShaderのALUやBandwidth監査には`shader-performance-auditor`を使う。原因未確定の実機障害は`unity-incident-investigation`をPrimaryにする。

## Workflow

1. Shader pragmas、keyword scope、Pass単位の定義をInventory化する。
2. Keywordをbuild-fixed、material-fixed、runtime-switchable、pass-limitedに分類する。
3. source-level Cartesian productを算出する。
4. URP Assets、RendererFeatures、Materials、Scenes、Addressables、AssetBundles、Resources、runtime creationを確認する。
5. Editorで見える組み合わせとPlayerで必要な組み合わせを分離する。
6. Reduction candidateとMissing-variant riskを別リストにする。
7. Strict Variantで必要な組み合わせを確認する。
8. `VARIANT_POLICY.md`に従い、Strip/Keep根拠を記録する。
9. 対象Player Buildと実機経路で検証する。

## Output contract

- Shader / Pass / Keyword inventory
- Keyword classification
- Estimated source product
- Runtime creation paths
- Keep / Strip decision and evidence
- Strict Variant coverage
- Build / Player verification
- Missing evidence and rollback

## Scope — what this Skill does not do

- Editor使用状況だけでStripしない。
- Addressables、AssetBundle、Resources、runtime material生成を無視しない。
- Variant削減のために無関係なShader表現を変更しない。
- source-level productを最終build variant数として断定しない。
- 実機未確認でStrict Variant安全を保証しない。

## Checklist

- [ ] pragmaとkeyword scopeをInventory化した
- [ ] runtime-switchableを分類した
- [ ] AssetBundle/Addressables/Resourcesを確認した
- [ ] ReductionとMissing riskを分離した
- [ ] Strict Variant組み合わせを確認した
- [ ] Player/実機検証とRollbackを記録した

## Common mistakes

- Editorで使われていないkeywordを不要と断定する。
- global keywordとlocal keywordの切替契約を壊す。
- RendererFeatureが要求するPass/keywordをInventoryから漏らす。
- Addressables内MaterialをBuild時に見落とす。
- `shader_feature`へ変えれば常に安全と判断する。
