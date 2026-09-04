# 現状構成と見取り図

> Review snapshot / non-authoritative。Canonicalな責務・契約は `AGENTS.md` と各Areaの正本を参照してください。

## リポジトリ規模

対象は `main@e8988ca7b8c656b6c3b6bc7ae592a9925d674d51` です。追跡ファイルは約502、Pythonは約212ファイル・約29.6k行、テストPythonは約7.3k行、Workflowは13本です。テストメソッドは約345件ありますが、標準の `Tools/validate_all.py` が収集するのは320件です。

## 責務と依存方向

| Area | 現在の責務 | 依存・境界 |
| --- | --- | --- |
| Policy | User Policy、Risk、Security、Approval、Evidence条件 | Provider選択・Tool実行・品質採点を持たない |
| Orchestration | Route、Parent/SubGraph、Task Contract、semantic replan、Runtime Handoff | subprocess、Provider dispatch、durable writeを持たない |
| Context | Context Pack、Retrieval、Knowledge、Budget、current-call materialization | Route authority、durable Memory/Evidenceを持たない |
| Runtime | Environment、Provider resolution、dispatch、timeout、retry、Scope、current-run Evidence | semantic replan、durable truth、Agent採点を持たない |
| Persistence | Execution/Workflow/Loop state、Checkpoint/Resume、Memory、durable Evidence | Provider選択・Runtime実行を持たない |
| Operations | Telemetry観測、Detection、Incident/Runbook、承認済みControl、Change Management | Policy/Approvalを迂回したMutationを行わない |
| Eval | Golden/Behavior、Attribution、Replay、Rebaseline、Regression、ChangeProposal | Production execution・definition変更を行わない |

Canonicalな依存方向は次の通りです。

```text
Policy defines
  → Orchestration decides
  → Context materializes
  → Runtime executes
  → Persistence remembers
  → Operations observes/controls、Eval measures/proposes
```

## 宣言された構成と確認できた構成

`docs/architecture/architecture.md` と `docs/architecture/production-tool-runtime.md` は、CapabilityRequestをRuntime Handoffへ渡し、Guard、ToolBroker、Resolver、Provider、Evidence Normalizer、Persistenceへ進む構成を定義しています。Resolver側にはProject binding、Environment health、Safety/Evidence floor、同一Capability fallbackなどの防御が実装されています。

しかし、今回確認した本番Smokeの入口（`.github/ProductionSmoke/run_one_repo_smoke.py`）は、RouteSelectorとContext Materializerを直接呼び出し、独自のCodex実行とEvidence変換へ進みます。ParentGraph、OrchestratorのHandoff、CapabilityRequestBuilder、ToolBrokerの本番利用者は確認できません。したがって、文書上の構成は個別部品として存在するものの、全トランザクションのCanonical経路として結線された状態とは判定できません。

## 維持すべき強み

- Authorityの責務分離とimport方向が概ね一方向である。
- Resolverが環境、Project、Health、Safety、Evidence条件を再確認して候補を絞る。
- Fallbackが同一Capabilityを維持し、Safety/Evidenceを下げない設計になっている。
- Native Editor、Unity CLI、Player、MyUnityMCPの各AdapterにBinding、Revision、Allowlistなどの防御がある。
- EvidenceStoreは不変IDとidempotent appendを意図し、`not_observed`を品質分母から除外している。
- クリーンなHEADではPolicy、Context、Runtime、Orchestration、Persistence、Eval、Operationsを横断する320テストが成功する。

## 未接続・未観測

- Runtime HandoffからToolBroker、ProviderResult、Evidence Persistenceまでの本番E2E。
- Approval Decision Storeと、Capability/Project/Scope/Diff/Revisionに束縛された承認。
- MyUnityMCPの実変更対象とMutation ScopeのExact Diff照合。
- Unity Editor、Unity CLI、MyUnityMCP、Player、Windows、対象機器、ProfilerのライブEvidence。
- OperationsのTelemetry→Detection→Incident接続と、変更・Rollbackの実運用Evidence。
- 現行v4.0と、181コミット遅れた旧v3.1 Baselineとの差分を再現するRegression Evidence。
