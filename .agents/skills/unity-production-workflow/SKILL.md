---
name: unity-production-workflow
description: Compatibility adapter for legacy Unity production prompts. Redirects execution ownership to DarumaPPAP/Unity-Graph-Engineering and Unity domain routing to `.ai/context-index.yaml`. Does not act as an independent Supervisor, choose domain routes itself, or own state and budgets.
allowed-tools:
  - Read
metadata:
  version: "4.0.0"
  kind: compatibility
  deprecated: true
  entrypoint: false
---

# Unity Production Workflow Compatibility Adapter

このSkillは旧`unity-production-workflow`参照を現在の正本へ転送するだけのCompatibility Adapterです。

## Canonical flow

1. `DarumaPPAP/Unity-Graph-Engineering`でExecution Mode、State、Budget、Recovery、Human Gateを管理する。
2. `.ai/user-policy.yaml`を読み、ユーザー固有Policyを最優先する。
3. `.ai/context-index.yaml`からPrimary Route、Task Contract、Context Packを一つずつ選ぶ。
4. 選択されたPrimary Domain Skillと必要なConditional Operationだけを読む。
5. Domain結果をExecution Ownerへ返す。

```text
Unity-Graph-Engineering
  ↓
UnityAgent user-policy
  ↓
UnityAgent context-index
  ↓
One Route / One Task Contract / One Context Pack
  ↓
One Primary Domain Skill
```

## Ownership boundary

このSkillは次を所有しません。

- Supervisor State Machine
- Prompt / Graph / Loop選択
- Task Graph
- Retry
- Token Budget
- Checkpoint
- Recovery orchestration
- Human Gate
- Unity Domain Routeの独自選択表

## Compatibility rule

旧PromptがこのSkillを明示した場合も、このSkill自身をPrimary Skillとして実行しません。
現在の正本へ転送し、旧Stateや旧Routing Tableを再構築しません。

## Output

- execution_owner
- user_policy
- selected_route
- selected_task_contract
- selected_context_pack
- primary_domain_skill
- unresolved_bindings

## Common mistakes

- このCompatibility SkillへSupervisor処理を戻す
- `.ai/context-index.yaml`を読まずにSkill名だけでRoutingする
- 全Skillと全Referenceを読み込む
- 一般的Best Practiceでユーザー固有Policyを上書きする
