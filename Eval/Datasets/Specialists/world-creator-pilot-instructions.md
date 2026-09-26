# WorldCreatorSubAgent Planning-only Pilot Instructions

**Status:** Candidate / Pilot。Unity ProjectのScene完成やProduction昇格を示さない。C ArmだけでWorldCreator候補を使用し、同一GoalとProject条件でA/B/Cを比較する。

## Domain

高水準World GoalをStructured World Planに分解する。Scene Scope、Environment Type、Visual Intent、Zones、Camera / Lighting / Content Requirements、Technical / Performance / Platform Constraints、禁止変更、Acceptance Criteria、Work Packages、Dependencies、Required Evidence、Open Decisionsを保持する。`domain_hint`はUnityAgentが後でRouteを決めるためのヒントであり、直接SubAgentを呼ばない。

## Input / Result

UnityAgentが選択したRouteとContext Manifestを受け取る。未指定のPlatform、Mood、Performance Budget、Camera Distanceなどを推測せずOpen Decisionsに残す。World Plan Resultの`source_context_id`と`source_context_fingerprint`は生成元Manifestと一致させる。Provider、ProviderResult、Received Receiptを作らない。Human Reviewは必須で、自動Visual AcceptanceとUnity Mutationは行わない。

## Legacy salvage

`world.compile_workflow`のGoal / Scope / Mood / Platform / 制約 / Dependency分解と、`world.create_review_handoff`のHuman Review / Acceptance / Open QuestionsをKnowledgeとして使う。`world.start_preflight`はExecution Frontendなので復活させない。旧Graphics Preflight Graphを固定手順としてコピーしない。

## Evaluation

静的fixtureではWorld Plan Artifactの形とContext bindingだけを評価する。実Scene生成、Compile、Editor、Player、Target Deviceは`NOT_EVALUATED_RUNTIME`。昇格可否は`requires_human_review`であり、Planner reasoningのProduction実行Authorityが定義されるまで登録しない。
