# Unity Shader Variant監査プロンプト

対象Shader群のKeywordとVariantを監査してください。

Use `unity-shader-variant-governor`, its Skill, `VARIANT_POLICY.md` and `UNITY_URP_POLICY.md`.

Requirements:

1. `multi_compile`、`shader_feature`、Local/Global、Stage Scopeを一覧化する。
2. Build固定、Material固定、Runtime切替、Pass限定へ分類する。
3. Pragmaごとの直積上限を算出する。
4. URP Asset、RendererFeature、Material、Addressables、AssetBundle、Resources、Runtime生成を確認する。
5. Variant削減候補と欠落リスクを別表にする。
6. Strict Variantで必要な組合せを明記する。
7. 根拠なしにStripまたは`shader_feature`化しない。
