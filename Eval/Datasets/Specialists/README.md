# Registered Specialist Pilot

`graphics-pilot.yaml` はGraphicsSubAgentの評価ケース定義、`graphics-pilot-instructions.md` はC Arm専用のRead-only指示です。状態は `pending_live_evaluation` であり、Editor、Player、Target Deviceの実測結果を含みません。対象Unity Projectを決め、同じTaskと条件でA: UnityAgentのみ、B: Skill + deterministic Tool、C: Specialistを実行します。

実行結果は同一 `task_id` のContext Manifest、Runtime result、永続化済みEvidenceと人手Reviewを各Armで記録します。`Eval/Regression/compare_specialist_promotion.py` は既存のContext / Evidence検証を再利用し、Context bytes / tokens、不要Context、Tool call / Retry、誤前提、Tool選択誤り、Approval違反、未裏付けClaim、Trace可読性、Latencyを比較します。Context Receiptが不正なC Armは拒否します。ComparatorはProduction昇格を自動決定しません。

Graphicsの初期PilotはRead-onlyです。RendererFeatureやShaderのMutationは、実測Eval、Exact Diff、Approval、実行Providerの契約を確認した後に独立して扱います。`rendering-incident`、`shader-change`、`renderer-feature-change` の既存Routeを優先し、Route数をSpecialist数に合わせて増やしません。

Repository-level契約は `Runtime/ReferenceImplementation/candidate-specialists.yaml`、`graphics-pilot-profile.yaml`、`candidate_profiles.py`、`graphics_read_only.py` に置きます。候補CatalogはProduction `subagent-catalog.yaml` と分離し、ResolverはRouteのProfile IDから共通Loaderを使います。ProfileはActivation FactとCapabilityごとのContext要件を別に宣言します。後者が不足した場合は `unavailable` と機械判定可能な `reason_code: required_context_missing`、必要Observationを返します。Source読み取り、Compile / Editor観測は既存ToolBrokerの実在Providerへ要求します。Graphics独自ProviderやProduction Catalog登録はありません。

`specialist_profile` はRoute内の **semantic analysis owner** であり、Mutation実行権限ではありません。`rendering-incident` は診断をPrimaryとし、`shader-change` と `renderer-feature-change` の `entry_action: implement` でもGraphicsはanalysis / preflight / reviewに限定します。Task全体の変更要求は `graphics.diagnose` を排除しません。ApplyはUnityAgentのPolicy、Approval、Runtimeが別に判断します。未対応Capability、Read-only候補への変更Capability要求、Unity 2022.3は `unsupported`、Pilot無効・Activation Fact不足は `unavailable` です。

Entry v2の `rendering_diagnosis` は `symptom` と `target_scope` を受け、既存 `rendering-incident` に決定的に到達します。Repository fixtureは Entry → Route → Candidate → Context → Generated / Transported / Received Receipt → Static Evidence を一体で確認します。Hub #72の候補契約は固定fixtureでIdentity、Capability、Evidence、互換性、実行境界を比較します。FixtureはApplyもUnity実行もしません。Compile、Editor、Player、Target Device、Live A/B/Cは `NOT_EVALUATED_RUNTIME` で、Production Verifiedではありません。
