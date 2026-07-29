# UnityAgent Execution Compatibility Adapter

汎用Supervisor、Execution Mode、Task Graph、Retry、Token Budget、Checkpoint、Human Gateの正本は`DarumaPPAP/Unity-Graph-Engineering`へ移行しました。

このFileは旧参照Pathとの互換性を保つAdapterです。状態遷移やBudget数値をここへ再定義しません。

## Execution owner

参照先:

- `Unity-Graph-Engineering/AGENTS.md`
- `Unity-Graph-Engineering/policies/execution-mode.yaml`
- `Unity-Graph-Engineering/policies/prompt-budget.yaml`
- `Unity-Graph-Engineering/policies/graph-loop-budget.yaml`
- `Unity-Graph-Engineering/policies/mode-escalation.yaml`
- `Unity-Graph-Engineering/skills/unity-execution-router/SKILL.md`
- `Unity-Graph-Engineering/schemas/execution-state.schema.yaml`
- `Unity-Graph-Engineering/schemas/evidence.schema.yaml`

## Default behavior

- 無指定時はPrompt Engineering。
- Graph / Loopへ無断変更しない。
- Prompt Budgetを超える見込み、複数Subsystem、Runtime / Visual / Performance反復、Migration、Platform固有再現ではMode変更を提案する。
- ユーザー承認後だけGraph / Loopへ移行する。
- 同一GoalでMode確認を繰り返さない。

## UnityAgent responsibility

UnityAgentはExecution Ownerへ次を提供します。

- Domain route
- Context Pack
- Unity / C# / Rendering / Shader / Performance / Visual固有Skill
- Compatibility constraints
- Required validation
- Domain evidence requirements

`.ai/context-index.yaml`からPrimary Context Packを一つ選びます。

## Execution contract mapping

旧Supervisorの概念は次へ移行します。

| 旧概念 | 新しい正本 |
|---|---|
| Goal / Constraints | Unity-Graph-Engineering Goal Contract |
| Observability | Evidence SchemaとDomain Context Pack |
| Recovery | Graph / Loop Failure Routing |
| Supervisor State | Execution State Schema |
| Tool exposure | Execution Mode PolicyとContext Pack |
| Human decision | Graph Human Gate |

## Compatibility rule

旧SkillまたはPromptがこのFileを要求した場合:

1. このAdapterだけを読む。
2. 現在Modeに必要なGraph側Policyだけを読む。
3. `.ai/context-index.yaml`からUnity Domain Contextを選ぶ。
4. 旧Supervisor本文を別Fileから再構築しない。

## Deprecation

このPathは既存PromptとSkillの移行期間中だけ維持します。削除はHuman Gate対象とし、Routing Testと外部参照の移行完了後に別Taskで判断します。
