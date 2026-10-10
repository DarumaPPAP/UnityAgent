# 監査結果からShaderを安全に最適化するプロンプト

Rule ID付き監査結果に基づき対象Shaderを最小差分で修正してください。

Use `shader-performance-optimizer`, `shader-performance-refactor`, `REFACTOR_POLICY.md` and `SHADER_REVIEW_GATE.md`.

Requirements:

1. 対象Rule IDを列挙する。
2. External Contractを列挙する。
3. 1回の変更で1仮説だけ扱う。
4. Shader名、Property、Keyword、Pass、LightMode、RenderState、CBUFFERを無断変更しない。
5. Motion Vector、Depth、STP/TAA、SRP Batcher、Variantへの影響を確認する。
6. Before/After計測方法とRevert条件を付ける。
7. Unity未コンパイル、Player未確認、実機未計測は明記する。
