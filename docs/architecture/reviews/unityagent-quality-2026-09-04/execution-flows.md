# 実行フローと安全Gate

> Review snapshot / non-authoritative。図はレビュー対象の構成を説明するもので、実行経路を新設する契約ではありません。

## 1. Canonicalとして宣言されたフロー

```mermaid
flowchart LR
    U[User Request] --> P[Policy]
    P --> O[Orchestration Route / Graph / Task Contract]
    O --> C[Context Materialization]
    C --> H[Authoritative Runtime Handoff]
    H --> G[Runtime Guard]
    G --> B[ToolBroker]
    B --> R[Resolver + Environment Health]
    R --> D[Dispatcher]
    D --> PR[ProviderResult]
    PR --> N[Evidence Normalizer]
    N --> S[Persistence Evidence]
    S --> E[Eval]
    S --> OP[Operations Telemetry / Detection]
```

この構成では、OrchestrationはCapabilityを要求し、ProviderとTransportの選択はRuntimeへ委譲します。Runtimeは実行直前にもPolicy、Project、Approval、Mutation Scopeを再確認し、Providerの人間向けログを品質Truthにしません。

## 2. 今回確認したProduction Smokeの経路

```mermaid
flowchart TD
    T[Smoke Case] --> RS[RouteSelector]
    RS --> CM[Context Materializer]
    CM --> CR[Custom Codex Request]
    CR --> WR[CodexRunner]
    WR --> DS[Post-run Diff / Mutation Evidence]
    DS --> PB[Legacy-style Evidence Bridge]
    PB --> PS[Persistence Adapter]
    PS --> EV[Eval Envelope]
    RS -. bypass .-> OG[Orchestrator / ParentGraph]
    CR -. bypass .-> CB[CapabilityRequestBuilder / ToolBroker]
    WR -. bypass .-> TD[Production Dispatcher]
```

これは、Smokeが動作していることの証拠ではあっても、Canonical Production Tool Runtimeが全ケースを通過している証明ではありません。`CodexRunner` は `workspace-write` で起動した後に差分を検査するため、違反変更が発生してから失敗を記録し得ます。

## 3. Mutationを許可する目標シーケンス

```mermaid
sequenceDiagram
    participant O as Orchestration
    participant G as Runtime Guard
    participant A as Approval Store
    participant B as ToolBroker/Dispatcher
    participant P as Provider
    participant N as Evidence Normalizer
    participant S as Persistence

    O->>G: RuntimeHandoff (Budget, Scope, required Evidence)
    G->>A: immutable ApprovalDecision lookup
    A-->>G: capability + project + scope + diff + revision + expiry
    G->>B: approved CapabilityRequest
    B->>P: prepare(scope digest, revision)
    P-->>B: plan + exact diff + target IDs
    B->>G: re-check scope and approval against exact diff
    G->>P: apply only after final gate
    P-->>N: structured ProviderResult + required Evidence
    N->>S: append durable Evidence
    S-->>B: append accepted
    B-->>O: completed only when Evidence gate passes
```

`unmeasured` Budget、空の必須Evidence、Scope外のExact Diff、期限切れ・対象不一致のApprovalは、完了ではなく停止または失敗として扱う必要があります。

## 4. 証拠・観測フロー

```mermaid
flowchart LR
    X[Runtime execution] --> CE[Current-run Evidence Capture]
    CE --> PE[Persistence/Evidence append]
    PE --> AT[Eval Attribution / Regression]
    PE --> OT[Runtime Telemetry]
    OT --> OD[Operations Detection]
    OD --> IN[Incident / Runbook]
    IN --> AC[Policy/Approval-gated Control API]
```

現状はEvidenceの個別部品とEvalのデータセットは存在しますが、Production実行から永続Evidence、Eval、Operationsまでをライブに確認できるRun ID・Artifact Digest付きの証跡が不足しています。
