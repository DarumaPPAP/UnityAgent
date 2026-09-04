# 改善ロードマップ

> Review snapshot / non-authoritative。各Stageは実装順序と受入条件を示す提案であり、Production変更の承認ではありません。

## Stage 0 — 安全境界とTruthの封鎖

**目的**：変更が対象へ残る前に止め、Approval・Scope・Evidenceを不正な成功にしない。

- Runnerのanalysis/verificationをread-only、Mutationを隔離worktree/stagingへ分離する。
- Runtime profileの`project_access`、`direct_mutation`、`staging_required`をGuardで強制する。
- Approval DecisionをPersistenceから取得し、Capability、Project、Scope fingerprint、plan/diff digest、Revision、期限・失効を照合する。
- MyUnityMCP prepare/applyでExact Diff（Path/Object ID）とScopeを照合する。
- EvidenceRecordのschemaとcross-field invariantをappend前に一元検証する。

**Exit criteria**：read-only書込み試行がbyte-for-byte不変、Scope外変更が対象へ到達しない、任意Approvalが拒否される、必須Evidence不足がcompletedにならない。

**依存・Rollback**：既存Mutationを一時的にstaging-onlyへ制限する。失敗時は対象Workspaceへのapplyを停止し、staging成果物だけを保持する。

## Stage 1 — Canonical Composition Rootと完了Gate

**目的**：本番入口をPolicyからdurable Evidenceまで一つの経路へ統一する。

- 厳格なRuntimeHandoff schemaにBudget decision、Mutation Scope、validation requirements、CapabilityRequestを必須化する。
- Orchestrator → Context → Runtime Guard → ToolBroker → Resolver → Dispatcher → ProviderResult → Evidence Normalizer → Persistenceを接続するComposition Rootを一つ定義する。
- Dispatcherでrequired/observed Evidence、capability固有の`not_applicable`、Provider identity、completionを検証する。
- `unmeasured`/`compression_required` BudgetはMutation境界で停止する。
- DefinitionFingerprintをcanonical bundle/file hashまたはVersionManifestから導出する。

**Exit criteria**：read-only、source patch、scene mutate、unavailable providerが同じRootを通り、完了はdurable Evidence append成功後だけになる。HandoffとProviderResultの契約テストが同じschemaを検証する。

**依存・Rollback**：Stage 0のGateが前提。結線不備時はRuntime実行を`implemented_unverified`へ降格し、成功扱いを止める。

## Stage 2 — 検証基盤の信頼性回復

**目的**：CIが実際に必要なテストを実行し、Workspace状態に左右されない。

- test manifestを作成し、`validate_all`へGraph Observatory等の収集外テストを追加する。
- 0件実行、import error、未解決test patternを非0終了にする。
- Graph Foundation/Security/Expansion/Projectionを標準Gateへ組み込む。不要な旧テストはHistorical Recordではなく、現行構成に合わせて整理する。
- Documentation/Eval Validatorの入力をtracked manifestまたは明示Rootへ限定し、ignored生成物を除外する。
- 廃止済み契約・Fixture参照を現行schemaへ移行し、暗黙canonicalize/fallbackを失敗扱いにする。
- Python依存とGitHub Actionのversion pin、Workflow共通化、coverageのreport-first導入を行う。

**Exit criteria**：clean/dirty Workspaceで判定が一致し、標準Gateが全テスト件数を報告し、0件実行が成功扱いにならない。Graph Observatory全テストが成功する。

**依存・Rollback**：既存Gateを並走させ、件数差を比較する。誤検知時は新manifestを無効化して旧Gateへ戻せるが、0件成功だけは許可しない。

## Stage 3 — 現行版の実環境Evidence

**目的**：現行v4.0の品質を旧Baselineではなく再現可能な実行で証明する。

- 現行commit、Policy、Runtime、Tool、Evidence schemaからBaselineを再生成する。
- Run ID、commit、OS、Unity/package、Provider、入力、出力、artifact digest、保持期限を記録する。
- Windows環境、Unity Editor/CLI、MyUnityMCP、Player、対象機器のSmokeを段階的に追加する。
- Golden 54ケースとProduction Smoke 4ケースの差を整理し、observed/unobservedをケース別に報告する。
- 性能主張は固定したBefore/After、warm-up、sample数、Target device、CPU/GPU/GC指標でのみ承認する。

**Exit criteria**：現行commitに紐づく再現可能なArtifactとログがあり、未観測領域を成功分母に含めない。Editor結果だけでPlayer/実機を承認しない。

**依存・Rollback**：環境ごとにCapabilityを`unavailable`へ戻せるようにし、証拠不足時はRelease判定をEvidence Requiredへ戻す。

## Stage 4 — Operationsと長期保守

**目的**：実行後の失敗・Evidence不足・Provider劣化を継続観測できる状態にする。

- Runtime Telemetry → Event Store → Detection → Incident/Runbookのread-only接続を作る。
- ControlはPolicy/Approval済みの明示APIだけへ渡す。
- Provider Support ManifestでPotential/Concrete/Live/Evidence対応を分離する。
- Workflowの重複セットアップを共通Action/Scriptへ集約し、skill validatorの警告を優先度付きで解消する。
- Issue [#32 ContextExplorer Full Refactor Migration](https://github.com/DarumaPPAP/UnityAgent/issues/32) の残課題を、現行GraphテストとCanonical relationの受入条件に結び付けて完了させる。

**Exit criteria**：Runtime failureとEvidence gapがRun IDでOperationsへ到達し、検知・Incident・Runbookの結果を確認できる。Graph/Contextの関係が実際のCanonical relationと一致する。

## 推奨する意思決定順

1. Stage 0完了まではMutationを本番対象へ適用しない。
2. Stage 1でCanonical E2Eを1本通し、成功Truthの入口を一つにする。
3. Stage 2でCIの「実行したテスト」を信頼できる状態にする。
4. Stage 3で現行版の実環境・性能Evidenceを揃え、Release可否を判断する。
5. Stage 4を運用開始条件とし、継続的な劣化検知へ移行する。
