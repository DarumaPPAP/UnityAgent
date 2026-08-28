# Shader実行時計測プロンプト

指定Rule IDの最適化をBefore/Afterで検証する計測計画と判定レポートを作成してください。

Use `shader-runtime-evidence-reviewer`, `shader-runtime-evidence`, `SHADER_REVIEW_GATE.md` and `Templates/SHADER_AUDIT_REPORT.md`.

Requirements:

1. Scene、Camera、Resolution、Quality、URP Asset、Keyword、Build、Deviceを固定する。
2. Warm-upとSample数を定義する。
3. CPU Bound、VSync、Dynamic Resolutionを除外する。
4. GPU Time、Register、Spill、Occupancy、Bandwidth、Wave利用率を可能な範囲で取得する。
5. 画像差分、Motion Vector、Depth、Temporal Stabilityを確認する。
6. Adopt / Rework / Revert / Inconclusiveで判定する。
7. 取得不能な値を推測で埋めない。
