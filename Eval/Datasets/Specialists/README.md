# Registered Specialist Pilot

`graphics-pilot.yaml` はGraphicsSubAgentの評価ケース定義、`graphics-pilot-instructions.md` はC Arm専用のRead-only指示です。状態は `pending_live_evaluation` であり、Editor、Player、Target Deviceの実測結果を含みません。対象Unity Projectを決め、同じTaskと条件でA: UnityAgentのみ、B: Skill + deterministic Tool、C: Specialistを実行します。

実行結果は同一 `task_id` のContext Manifest、Runtime result、永続化済みEvidenceと人手Reviewを各Armで記録します。`Eval/Regression/compare_specialist_promotion.py` は既存のContext / Evidence検証を再利用し、Context bytes / tokens、不要Context、Tool call / Retry、誤前提、Tool選択誤り、Approval違反、未裏付けClaim、Trace可読性、Latencyを比較します。Context Receiptが不正なC Armは拒否します。ComparatorはProduction昇格を自動決定しません。

Graphicsの初期PilotはRead-onlyです。RendererFeatureやShaderのMutationは、実測Eval、Exact Diff、Approval、実行Providerの契約を確認した後に独立して扱います。`rendering-incident`、`shader-change`、`renderer-feature-change` の既存Routeを優先し、Route数をSpecialist数に合わせて増やしません。

Repository-level契約は `Runtime/ReferenceImplementation/graphics-pilot-profile.yaml` と `graphics_read_only.py` に置きます。Source読み取り、Compile / Editor観測は既存ToolBrokerの実在Providerへ要求します。Graphics独自ProviderやProduction Catalog登録はありません。Orchestrationの3 RouteにはPilot bindingがありますが、`resolve_specialist(..., pilot_enabled=True)` を明示し、Unity 6.xの観測と読み取り可能なProject Factが揃う場合だけ候補になります。通常選出、必要Fact不足は `unavailable`、対象外Capability、変更要求、Unity 2022.3は `unsupported` です。

Fixture ContractはGenerated → Transported → ReceivedのContext ID / Fingerprint、選択Context、`graphics_diagnosis` Evidence、Read-only、`NOT_EVALUATED_RUNTIME` を検証します。この検証はUnityでの動作やGraphicsSubAgentのProduction Verifiedを示しません。現行Control Planeのv2 EntryはGraphics診断Intentを受け付けないため、実Projectに対するA/B/C Runtime実行とProduction統合は後続です。
