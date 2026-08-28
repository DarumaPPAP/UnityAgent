<!-- unityagent-bootstrap-map:v2 -->
# UnityAgent Bootstrap Map

> `bootstrap_map_only: true`

`AGENTS.md` は起動用の地図です。詳細規約を複製せず、各 Authority の Canonical Source へ委譲します。

## 1. Authority

1. 今回のユーザー明示指示
2. `Policy/User/user-policy.yaml`
3. 対象Project固有Policy
4. Unity Domain Standard
5. 外部Reference
6. 一般的Best Practice

ユーザー固有Policyを一般論で上書きしません。Policyの削除・簡略化は `Policy/User/user-policy.yaml` の保護契約に従います。

## 2. Bootstrap sequence

1. `Policy/User/user-policy.yaml` を読む。
2. Policy Risk / Security / Approval / Evidence は `Policy/` を正本として適用する。
3. Route は Orchestration authority または Phase 4 までの既存互換 routing から明示的に受け取る。Context 自身が technology keyword から route を決めない。
4. `Context/Selection/context-catalog.yaml` から選択済み Route の Context Pack、Primary Skill、Task Contract参照を解決する。
5. `Context/Assembly/materialize_context.py` で current-call `MaterializedContextView` を構築する。
6. `Context/Budget/context-budget.yaml` で Retrieval / Context / Compression Budget を評価する。Required Contextを無言削除しない。
7. MCP が必要な場合、Context は `Context/Selection/mcp-selection.yaml` で必要Description/Manifestだけを選択し、Policy が許可条件を定義し、Runtime が `Runtime/Permissions/mcp-activation.yaml` に従って実際のTool Groupを公開する。
8. `Context/Manifest/` は current-call Context provenanceを記録する。WorkflowState / Checkpoint / Evidence truth / Graph topologyの正本にはしない。
9. User Policy / Context Pack / Prompt / Budget変更時は対応する Contract Test / Golden Regressionを確認する。
10. 旧Pathを必要とする未移行機能は `Context/Compatibility/legacy-path-map.yaml` の read-only key経由だけで参照する。新規writeは禁止する。

## 3. Canonical map

| Area | Canonical Source | Responsibility |
|---|---|---|
| User Policy | `Policy/User/user-policy.yaml` | ユーザー固有の正しさ、Preference、禁止事項 |
| Risk / Security / Approval / Evidence | `Policy/` | Rule / Authority |
| Prompt | `Context/Prompt/` | versioned prompt specification |
| Context Packs | `Context/Packs/` | Required / Conditional / Excluded Context |
| Knowledge Retrieval | `Context/Retrieval/Knowledge/` | bounded knowledge projection |
| Memory Retrieval | `Context/Retrieval/Memory/` | Persistence Memoryのcurrent-call projection interface |
| Context Selection | `Context/Selection/` | selected source/pack/tool schema selection |
| Context Budget / Compression | `Context/Budget/` + `Context/Compression/` | bounded model input |
| Context Assembly / Manifest | `Context/Assembly/` + `Context/Manifest/` | Materialized Context View / provenance |
| Runtime Contracts | `Runtime/Contracts/` | canonical execution facts |
| Runtime Tool Exposure | `Runtime/Permissions/` | actual tool exposure/enforcement |
| Persistence Contracts | `Persistence/Contracts/` | state/checkpoint/memory/evidence contracts |
| Eval Contracts | `Eval/` | quality measurement / attribution |

## 4. Responsibility guards

- Policy defines; Context materializes; Orchestration decides; Runtime executes; Persistence remembers; Operations observes/controls; Eval measures/proposes.
- Contextは保存庫ではない。Durable Memory / WorkflowState / Checkpoint / Evidence truthを所有しない。
- Context CatalogはRoute decision authorityではない。明示Routeに必要な入力だけをmaterializeする。
- User Policy、Context Pack、Primary Skill、Task Contract、Project FactをLossy Compressionしない。
- Unknown Project Factや不足Bindingを推測で埋めず、unresolvedとして残す。
- `unavailable`を成功扱いしない。CompileだけでRuntime / Visual / Performance / Player / 実機を承認しない。
- EvalのGolden expected contentをProduction Promptへ注入しない。
- Runtimeのhard timeout / hard retry / process kill と Graph semantic replan を混同しない。
- Compatibilityはread-only。旧Sourceの削除はPhase 8の明示Human Gateまで行わない。

## 5. Current execution compatibility

- Phase 3 / Phase 4 の cutover までは、実 Production Agent Execution、Loop / Graph、Execution Retry、Checkpoint、Human Gate の既存実装は `DarumaPPAP/Unity-Graph-Engineering` を compatibility execution owner として利用する。
- これは最終 Authority ではなく移行中の互換境界であり、UnityAgent 内へ同じ Runtime / Graph 実装を二重作成しない。
- `DarumaPPAP/MyUnityMCP` は MCP manifest / tool schema / package implementation の外部 owner のままとし、Context は必要な記述だけを選択する。
- Phase 2 では Policy / Context の canonical source だけを切り替え、Runtime / Orchestration / Persistence の ownership cutover は先取りしない。

## 6. User-specific entrypoints

- Comments: `Policy/User/user-policy.yaml#comment_system`
- C# / Formatting: `.agents/skills/` と `SkillReferences/CODING_STANDARDS.md`
- Architecture / ECS: `.agents/skills/unity-architecture-design/` と対応 `SkillReferences/`
- Rendering / Shader: `.agents/skills/unity-rendering/` + 選択 Context Pack / Knowledge
- Runtime / Performance: `.agents/skills/unity-runtime-evidence/`
- Context Budget: `Context/Budget/context-budget.yaml`
- Prompt Templates: `Context/Prompt/Templates/`
- Golden / Actual Behavior Eval: `Eval/` と既存 Tests。Production execution ownershipの統合は後続Phaseで行う。

## 7. Completion handoff

Execution Ownerへ、適用Policy revision / Route / Context Pack / Primary Skill / Task Contract / Context ID / Context Fingerprint / Budget decision / Compression / unresolved bindings / validation requirementsを渡します。ContextはExecution結果やdurable stateを正本として保持しません。

## 8. Anti-regression

- `AGENTS.md`へ詳細規約本文を戻さない。
- Policy canonical sourceを互換Sourceで上書きしない。
- ContextからRoute/Graph/Retry authorityを新設しない。
- ContextからDurable Memory/Checkpoint/Evidence storeを書き込まない。
- 新しい旧Path直参照・writeを追加しない。
- Golden expectationをPromptへ混入させない。
