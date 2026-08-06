# Unity Skill Routing Compatibility Reference

> このFileは旧参照Pathとの互換性だけを維持します。Routingの正本ではありません。

Unity Domain Routeの唯一の正本は`.ai/context-index.yaml`です。
ユーザー固有Policyの正本は`.ai/user-policy.yaml`です。
実行Mode、Task Graph、Retry、Budget、State、Recovery、Human Gateは`DarumaPPAP/Unity-Graph-Engineering`が所有します。

## Compatibility behavior

旧Promptまたは旧SkillがこのPathを要求した場合は、次だけを行います。

1. `.ai/user-policy.yaml`を読む。
2. `.ai/execution-profiles.yaml`からExecution Profileを選ぶ。
3. `.ai/context-index.yaml`からPrimary Route、Task Contract、Context Packを一つずつ選ぶ。
4. 選択されたPrimary Domain Skillと必要なConditional Operationだけを読む。
5. このFileから旧Supervisor State、旧Lane、旧Skill選択表を再構築しない。

## Comment operations

コメント関連はユーザー固有Policyとして保護されています。

- 本番コード用: `production-code-comments`
- 学習・コードリーディング用: `learning-code-comments`
- 既存コメント監査: `comment-quality-reviewer`

詳細は`.ai/user-policy.yaml#comment_system`を正本とします。

## Prohibited use

- このFileをPrimary Routerとして使わない。
- `unity-production-workflow`を独立Supervisorとして使わない。
- 旧State Machineや旧Failure Routingを復元しない。
- 一般的Best Practiceでユーザー固有Policyを上書きしない。
