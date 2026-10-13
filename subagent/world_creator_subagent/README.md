# WorldCreatorSubAgent Production契約

`manifest.yaml`はManifest v5のactive reasoning Specialist登録です。`contracts/production-capability-contract.yaml`がProduction境界、`contracts/capability-contracts.yaml`が過去の候補契約です。`world.plan`はHigh-levelなWorld GoalをStructured World Planへ分解します。Work Packageの`domain_hint`はUnityAgentが後でRouteを再解決するためのヒントであり、WorldCreatorによるSubAgent呼出しではありません。

実行は`reasoning` / `planning_only`で、semantic capabilityにTool Providerを要求しません。Provider、ProviderResult、Provider向けGenerated→Transported→Received Receiptは存在しません。Plan Artifactは生成元Context IDとFingerprintを参照し、UnityAgentが一致を検証します。Human Reviewは必須で、自動Visual Acceptanceと直接Unity Mutationは禁止です。

旧`world.compile_workflow`の知識は、Visual Goal、Scene Scope、Environment Type、Mood、Target Platform、禁止変更、Acceptance Criteriaを明示し、未観測値を`open_decisions`へ残すPlan入力契約へ移しました。旧Toolの`expectedRevision`やAgent Graph IDは現在のPlanning APIへ持ち込みません。実行時のProject revisionとContext bindingはUnityAgentが検証します。

旧`world.create_review_handoff`の知識は、制作GoalとAcceptance Criteriaを維持したStructured Plan、`human_review_required`、必要Evidenceへ移しました。Review結果の受付、Approval、後続Execution、PersistenceはUnityAgentが所有します。旧`world.start_preflight`は旧Agent Execution Frontendなので移植しません。

Hub登録とUnityAgentのReasoning Runtime経路はRepository / fixtureで検証しています。これはLive Reasoningや実Unity Projectでの検証成功を意味しません。Compile / Editor / Player / Target Deviceは`NOT_EVALUATED_RUNTIME`です。旧Legacy Runtimeの削除は、残る依存と置換Evidenceの監査が完了するまで保留します。
