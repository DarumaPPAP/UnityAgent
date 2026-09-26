# Registered Specialist Pilot

`graphics-pilot.yaml` はGraphicsSubAgentの評価ケース定義です。状態は `pending_live_evaluation` であり、Editor、Player、Target Deviceの実測結果を含みません。対象Unity Projectを決め、同じTaskと条件でA: UnityAgentのみ、B: Skill + deterministic Tool、C: Specialistを実行します。

実行結果は同一 `task_id` のContext Manifest、Runtime result、永続化済みEvidenceと人手Reviewを各Armで記録します。`Eval/Regression/compare_specialist_promotion.py` は既存のContext / Evidence検証を再利用し、Context bytes / tokens、不要Context、Tool call / Retry、誤前提、Tool選択誤り、Approval違反、未裏付けClaim、Trace可読性、Latencyを比較します。Context Receiptが不正なC Armは拒否します。ComparatorはProduction昇格を自動決定しません。

Graphicsの初期PilotはRead-onlyです。RendererFeatureやShaderのMutationは、実測Eval、Exact Diff、Approval、実行Providerの契約を確認した後に独立して扱います。`rendering-incident`、`shader-change`、`renderer-feature-change` の既存Routeを優先し、Route数をSpecialist数に合わせて増やしません。
