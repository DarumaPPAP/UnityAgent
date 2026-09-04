# 課題一覧

> Review snapshot / non-authoritative。優先度は受入判断への影響順です。Findingの修正はこの資料の範囲外です。

## P0 / Critical

### UA-Q-001 — RunnerのMutation隔離が事後検査のみ

- **Category / Severity / Confidence**: Correctness / Critical / High
- **Location**: `Runtime/Runner/Codex/codex_runner.py:130-159`
- **Evidence**: analysis/verificationを含む実行が `--sandbox workspace-write` で起動され、完了後に変更パスを `evaluate_mutation_scope` へ渡す。
- **Failure condition**: 実行中に許可外ファイルを書き換えると、検査は失敗を返せるが、対象Workspaceへ変更がすでに残る。Rollbackもない。
- **Impact**: read-only契約の破壊、作業木・Project資産の汚染、Team Safe Importの前提崩壊。
- **Minimal proposal**: analysis/verificationはread-only sandbox、Mutationは隔離worktreeまたはstaging copyで実行し、Exact Diffを検査してから対象へ適用する。Runtime profileの`project_access`、`direct_mutation`、`staging_required`もGuardで強制する。
- **Validation required**: read-only中の書込み試行でWorkspaceがbyte-for-byte不変、Scope外変更が対象へ到達しない、隔離失敗時に安全停止すること。

## P1 / Error

### UA-Q-002 — Canonical Production経路がComposition Rootで結線されていない

- **Category / Severity / Confidence**: Correctness / Error / High
- **Location**: `Orchestration/Orchestrator/orchestrator.py:43-48`、`Runtime/Runner/Codex/codex_runner.py:32-43`、`.github/ProductionSmoke/run_one_repo_smoke.py:489-529`
- **Evidence**: OrchestratorのHandoff形状とCodex RunnerのRequest形状が異なり、SmokeはParentGraph、CapabilityRequestBuilder、ToolBroker、Production Dispatcherを直接経由しない。
- **Failure condition**: 部品単体の契約が成功しても、実行時にPolicy→Handoff→Broker→Provider→Evidence→Persistenceの一貫した保証が適用されない。
- **Impact**: Approval、Budget、Evidence、Fallback、Persistenceの保証がケースごとに分岐し、受入可能な本番経路を特定できない。
- **Minimal proposal**: 厳格なRuntimeHandoff schemaを定義し、全Production入口が同一Composition Rootを呼ぶ。HandoffからCapabilityRequest、ProviderResult、durable Evidenceまでを通すE2Eを1本追加する。
- **Validation required**: read-only、source patch、scene mutate、unavailable providerの各ケースで同一経路とdurable Evidenceを確認する。

### UA-Q-003 — 必須EvidenceがDispatcherの完了Gateになっていない

- **Category / Severity / Confidence**: Correctness / Error / High
- **Location**: `Runtime/Dispatcher/tool_runtime_dispatcher.py:85-101,206-215`
- **Evidence**: ProviderResultのstatusとdict形状は検証するが、`evidence=[]`でも`passed`/`not_applicable`をcompletedとして返し得る。
- **Failure condition**: `source.read`などで必須Evidenceを宣言したProviderが空Evidenceを返す。
- **Impact**: 観測されていない実行が成功扱いとなり、Eval・Persistenceに過大な成功Truthが流れる。
- **Minimal proposal**: ProviderResult schema、宣言されたrequired/observed Evidence、capability固有の`not_applicable`理由を完了前に検証し、不足時は`partial`または`implemented_unverified`で停止する。
- **Validation required**: 空Evidence、部分Evidence、未宣言Evidence、誤ったProvider参照、正当な`not_applicable`を個別テストする。

### UA-Q-004 — MyUnityMCPのMutation ScopeがExact Diffと照合されない

- **Category / Severity / Confidence**: Security/Correctness / Error / High
- **Location**: `Runtime/Tooling/Providers/MyUnityMcp/myunitymcp_provider.py:370-421,475-479`
- **Evidence**: Scopeはdigest化・凍結されるが、prepareへ完全なScopeが渡されず、planの変更対象Path/Object IDとScopeの照合がない。applyはdigest一致だけを確認する。
- **Failure condition**: Scope digestは一致していても、Provider planの変更対象が許可範囲外になる。
- **Impact**: 承認済み範囲を越えたScene/Asset変更を防げない。
- **Minimal proposal**: prepareにcanonical Scope/digestを渡し、structured Exact DiffにPath/Object IDを必須化する。承認前とapply直前の2回、Scope evaluatorで照合し、Providerが同じdigestをechoする。
- **Validation required**: 範囲内、範囲外、空Diff、対象ID変更、Revision変更の各ケースを実Editorまたは厳密なProvider fixtureで検証する。

### UA-Q-005 — Approvalが呼出側の文字列・真偽値を信頼する

- **Category / Severity / Confidence**: Security / Error / High
- **Location**: `Runtime/Guardrails/tool_runtime_guard.py:96-114`
- **Evidence**: `approval_ref`は非空文字列、`ResolutionContext.approval_complete`は`True`であることだけを確認する。対象Capability、Project、Scope、Diff、Revision、期限、失効との束縛がない。
- **Failure condition**: 任意の文字列とcaller-supplied booleanでmutation requestを作る。
- **Impact**: scene.mutate等の承認付きCapabilityをPolicy/Approvalなしで通過させ得る。
- **Minimal proposal**: Persistenceの不変ApprovalDecisionを参照し、Capability、Project binding、Scope fingerprint、plan/diff digest、revision、expiry/revocationを全て照合する。raw booleanをTrust boundaryから除去する。
- **Validation required**: 任意ref、対象不一致、期限切れ、失効済み、Scope変更、Revision変更を拒否すること。

### UA-Q-006 — PersistenceがEvidenceの相互条件を完全検証しない

- **Category / Severity / Confidence**: Correctness / Error / High
- **Location**: `Persistence/Evidence/runtime_adapter.py:105-152`、`Persistence/Evidence/evidence_store.py:79-100`
- **Evidence**: 必須フィールド、durability、値域を確認するが、Provider参照、completion、observation state、mutation provenanceの組み合わせを完全なschemaとして検証しない。
- **Failure condition**: provider_ref空、completion verified、observation_state not_observed等の不整合Recordをappendする。
- **Impact**: durable Evidenceが不正な成功Truthとなり、Resume・Eval・Operationsの根拠が汚染される。
- **Minimal proposal**: EvidenceRecord schemaとcross-field invariantをappend前に一元検証し、違反は永続化しない。schema revisionを実装から生成・検証する。
- **Validation required**: 正常、重複、空Provider、verified/not_observed、壊れたmutation provenanceをappendテストする。

### UA-Q-007 — Context Budgetの`unmeasured`がMutationを止めない

- **Category / Severity / Confidence**: Correctness / Error / High
- **Location**: `Context/Assembly/materialize_context.py:79-100,276-277`、`.github/ProductionSmoke/run_one_repo_smoke.py:491`
- **Evidence**: semantic bindingを一律にpathとして扱い、必須bindingでもBudget decisionが`unmeasured`になり得る。Materializerは`blocked`だけをthrowし、SmokeはBudget結果を無視してRuntimeへ進む。
- **Failure condition**: Budgetが未計測またはcompression_requiredのままMutation requestを作る。
- **Impact**: 不十分なContextでScope、Policy、Validation条件を欠いたMutationが実行される。
- **Minimal proposal**: semantic/repository/external bindingを型分離し、HandoffへBudget decisionを含める。Mutation境界で`within_budget`以外を停止する。
- **Validation required**: `within_budget`、`compression_required`、`unmeasured`、`blocked`をMutation/read-only別に確認する。

### UA-Q-008 — DefinitionFingerprintが静的文字列である

- **Category / Severity / Confidence**: Maintainability/Correctness / Error / High
- **Location**: `Context/Assembly/materialize_context.py:326-337`
- **Evidence**: graph、runtime、tool、checkpoint、evidence、eval revisionがハードコードされ、Resumeはその文字列差分を信頼する。
- **Failure condition**: Canonical fileや契約を変更してもrevisionの手動更新を忘れる。
- **Impact**: ResumeがreplanやHuman Reviewを要求せず、旧定義との互換性を誤判定する。
- **Minimal proposal**: canonical bundle/file hashまたはVersionManifestから各Fingerprintを導出し、変更時に必ず差分を検出する。
- **Validation required**: 各sourceの1行変更でFingerprintが変化し、compatible/migration/replanがfail-closedに分岐すること。

## P2 / Warning

### UA-Q-009 — 通常のread-only fallbackが実質到達不能

- **Category / Severity / Confidence**: Correctness / Warning / Medium
- **Location**: `Orchestration/Routing/task-routes.yaml`、`Orchestration/Routing/route_selector.py:52-55`
- **Evidence**: generic-planningが空のfingerprint matchで通常候補として常に一致し、候補なし時のanswer-only fallbackへ到達しない。
- **Failure condition**: 未知のread-only入力が明示的な候補なしでもplan系Routeへ分類される。
- **Impact**: 不要なContext/Runtime処理と、意図しない実行プロファイル選択。
- **Minimal proposal**: generic routeを候補外fallbackとして扱い、通常のmatch判定から空matchを除外する。
- **Validation required**: 既知、未知read-only、mutation、候補なしのRoute判定表。

### UA-Q-010 — Context Budgetが同一Policyを重複計上する

- **Category / Severity / Confidence**: Maintainability / Warning / Medium
- **Location**: `Context/Assembly/materialize_context.py:252-269`
- **Evidence**: catalogのPolicyとarchitecture packのPolicyが重複して追加され、同一revisionのdedupがない。
- **Failure condition**: Budgetが厳しいContextで同じPolicyが二重にmaterializeされる。
- **Impact**: 有効なContext容量を消費し、圧縮や未計測状態を誘発する。
- **Minimal proposal**: source revisionとroleをキーに一度だけ計上し、dedupをBudget reportへ明示する。
- **Validation required**: 同一sourceを複数packから要求した場合のbyte countとdecision。

### UA-Q-011 — Provider RegistryのPotentialとConcrete/Live実装の差が見えない

- **Category / Severity / Confidence**: Maintainability / Warning / Medium
- **Location**: `Runtime/Tooling/Providers/` とProvider registry/manifest
- **Evidence**: Registryは複数ProviderのPotential Capabilityを掲げる一方、source.read/source.patch以外は実装・Live接続の粒度が揃わず、Coplay MCP等はConcrete executorを確認できない。
- **Failure condition**: Registry掲載だけを実行可能Capabilityと誤認する。
- **Impact**: unavailable、backend_not_implemented、unsupportedの判定が運用上不透明になる。
- **Minimal proposal**: Potential、Concrete adapter、Live discovery、Environment requirementを別フィールドで示すSupport Manifestを作る。
- **Validation required**: 各Provider・Capabilityの登録、実装、Live接続、Evidence対応を一覧で検証する。

### UA-Q-012 — OperationsのTelemetryからDetection/Incidentが本番接続されていない

- **Category / Severity / Confidence**: Maintainability / Warning / Medium
- **Location**: `Operations/Observability/`、`Operations/Detection/`、`Operations/Incidents/`
- **Evidence**: Event Store、Detector、Incident生成、Provider metricsに非テストの呼出経路を確認できない。Dashboardは定義ファイル中心である。
- **Failure condition**: Runtime FailureやEvidence不足がOperationsへ到達しない。
- **Impact**: 検知・Runbook・承認済みControlが実行結果と連動しない。
- **Minimal proposal**: Runtime telemetry adapter→Event Store→Detector→Incidentのread-only経路を接続し、ControlはPolicy/Approval済みAPIだけへ限定する。
- **Validation required**: failure、evidence gap、provider unavailable、retention、schema破損を含むintegration test。

## 検証基盤・資料品質

### UA-Q-013 — `validate_all`が全テストと0件実行を保証しない

- **Category / Severity / Confidence**: Maintainability / Error / High
- **Location**: `Tools/validate_all.py:31`、`.github/workflows/validate-eval.yml:68-70`、`.github/workflows/actual-behavior-eval.yml:25-28`
- **Evidence**: Graph Observatory等の収集外テストがあり、Behavior Eval Workflowは削除済みパターンを指定して`Ran 0 tests / NO TESTS RAN`（exit 5）になる。
- **Failure condition**: CIが成功表示でも重要テストを実行しない、または手動Workflowが0件のまま運用される。
- **Impact**: 回帰検知の信頼性低下と、品質状態の過大評価。
- **Minimal proposal**: test manifestを一元化し、全サポートテストを収集する。0件実行を必ず失敗にし、Workflowを現行テスト名へ更新する。
- **Validation required**: 収集件数、各スイートの実行件数、0件・import error時の非0終了。

### UA-Q-014 — Graph ObservatoryのFoundation契約が標準検証に入っていない

- **Category / Severity / Confidence**: Correctness / Error / High
- **Location**: `Tests/GraphObservatory/test_graph_observatory_foundation_contract.py:70-73`、`Tools/validate_all.py`
- **Evidence**: Foundation testは`graph.schema.json`を`validate_all.py`が参照することを要求するが、現行validatorはContext Explorer検証しか呼ばない。Graph testは1件失敗した。
- **Failure condition**: Graph schema/foundationの不整合が標準Gateを通過する。
- **Impact**: 見取り図・Graph Contractの回帰を検知できない。
- **Minimal proposal**: Foundation、security、expansion、projectionの全Graph testを標準Gateへ追加し、不要な旧テストは削除または明示的に移行する。
- **Validation required**: Graph Observatory全14件の収集・成功、意図したedge/node数の契約確認。

### UA-Q-015 — Validatorがignoredファイルに依存する

- **Category / Severity / Confidence**: Maintainability / Warning / High
- **Location**: `Tools/DocumentationValidator/validate_documentation.py:34-55`、`Eval/Behavior/validate_cutover.py`
- **Evidence**: `ROOT.rglob("README.md")` とpath存在判定がignored `Artifacts`/`__pycache__`を含み、通常Workspaceでは失敗するがclean tracked snapshotでは成功した。
- **Failure condition**: ローカル生成物の有無だけでValidator結果が変わる。
- **Impact**: CIと開発者の結果が一致せず、失敗原因を誤認する。
- **Minimal proposal**: tracked manifestまたは明示的な入力Rootだけを検証し、ignored生成物を対象外にする。clean/dirty差をdiagnosticへ出す。
- **Validation required**: ignored生成物の追加・削除で判定が変わらないこと、tracked file欠落だけが失敗すること。

### UA-Q-016 — 現行契約に廃止済み参照と古い状態名が残る

- **Category / Severity / Confidence**: Maintainability / Warning / High
- **Location**: `Eval/Behavior/behavior-eval-contract.yaml:2-15`、`Eval/Datasets/Behavior/suites.yaml`
- **Evidence**: contractに旧phase状態名と廃止済みCompatibility参照、datasetに廃止済みテストFixture参照が残り、paths helperが暗黙にcanonicalizeする。
- **Failure condition**: canonical cutover後も古い参照が静かに解決され、削除漏れが検知されない。
- **Impact**: 旧契約がProduction/Eval authorityへ逆流し、再現性と保守性を損なう。
- **Minimal proposal**: 現行schemaへ明示移行し、旧参照は監査用のHistorical Recordへ隔離する。暗黙fallbackを禁止し、unknown referenceをfail-closedにする。
- **Validation required**: 旧参照がactive docs/contractにないこと、未知pathがcanonicalizeされず失敗すること。

### UA-Q-017 — BaselineとProduction Evidenceの世代が一致しない

- **Category / Severity / Confidence**: Evidence Required / Warning / High
- **Location**: `Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml`
- **Evidence**: Baselineは旧v3.1・`08d915...`を参照し、現行HEAD v4.0とは181コミット差がある。Production smokeは4ケース、Golden datasetは54ケースで、実Unity実行のRun ID/Artifact保管は確認できない。
- **Failure condition**: 旧Baselineを現行Runtimeの品質基準として比較する。
- **Impact**: Regression判定が現行実装を表さず、未観測領域を品質分母へ混入させる。
- **Minimal proposal**: 現行定義でBaselineを再生成し、Run ID、commit、environment、artifact digest、保存期限を不変台帳へ記録する。`not_observed`は分母から除外する。
- **Validation required**: 同一commit・環境での再実行、一致するdigest、ケース別のobserved/unobserved集計。

## 判定への反映

UA-Q-001〜UA-Q-008は安全性・正しさのBlocking相当で、修正なしにApproveできません。UA-Q-013〜UA-Q-017は、修正後の品質を証明するための検証基盤・Evidence条件です。UA-Q-009〜UA-Q-012は、Blocking解消後に運用コストと将来の回帰を抑える項目です。
