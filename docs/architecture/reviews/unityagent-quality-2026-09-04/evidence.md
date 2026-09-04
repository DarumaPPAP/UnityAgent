# Evidence台帳

> Review snapshot / non-authoritative。ここにない実行を成功・観測済みとは扱いません。

## 対象と再現条件

| 項目 | 値 |
| --- | --- |
| Repository | [DarumaPPAP/UnityAgent](https://github.com/DarumaPPAP/UnityAgent) |
| Branch / commit | `main` / `e8988ca7b8c656b6c3b6bc7ae592a9925d674d51` |
| Review date | 2026-09-04（Asia/Tokyo） |
| Comparison base | `origin/main`、指定merge baseと同一HEAD |
| Scope | Canonical repository、公開GitHub履歴、静的コード、単体/Validator実行 |
| Out of scope | Unity Editor/Playerのライブ接続、実機性能、GitHubへの書込み |

## 実行した検証

### Clean tracked snapshot

- 一時的なclean checkoutへtracked sourceを展開し、`python Tools/validate_all.py` を実行。
- 結果：成功。Policy 2、Context 11、Runtime 173（symlink unavailableによる2 skip）、Orchestration 15、Persistence 34、Eval 57、Operations 19、HarnessProjection 9を含む計320テストと関連Validatorが通過。
- `Tools/DocumentationValidator/validate_documentation.py` は、この資料追加後に再実行する。

### 通常Workspaceとの差

- 通常Workspaceではignored `__pycache__`等を旧Cutover Validatorが検査対象として扱い、12件のForbidden pathとGoldenTasks存在を報告した。
- 同じtracked sourceをclean snapshotで実行すると成功したため、現象は生成物依存のValidator入力差として課題化した（UA-Q-015）。

### 収集外・Workflow

- tracked test methodは約345件だが、`Tools/validate_all.py` の標準収集は320件。
- `.github/ProductionSmoke`の追加11件は個別実行では成功したが、標準Gateへ統合されていない。
- `Tests/GraphObservatory`は14件中1件が失敗。Foundation testが`Tools/validate_all.py`で`graph.schema.json`を検証することを要求するが、現行validatorはContext Explorer検証のみを呼ぶ。
- `.github/workflows/validate-eval.yml`はContext Explorer投影テストだけを実行する。
- `.github/workflows/actual-behavior-eval.yml`の`test_phase6_eval.py`指定は現行テスト構成と一致せず、`Ran 0 tests / NO TESTS RAN`（exit 5）を再現した。
- `Tools/RouteGraphValidator/validate_route_graph.py`は旧Compatibility実装をimportし、単独実行でFileNotFoundErrorになる。標準Gateからも呼ばれていない。

## GitHub履歴

- PR [#92 policy: add shader branching decision policy](https://github.com/DarumaPPAP/UnityAgent/pull/92) はmerge済み。PR headでProduction Tool Runtime、Policy Context、Eval、UnityAgent Contractsの4 Workflowが成功。
- PR [#91 Production Runtime cutover](https://github.com/DarumaPPAP/UnityAgent/pull/91) は関連Workflowの成功を報告する一方、実Unity Editor、MyUnityMCP、console deviceのlive smokeは実施していないと明記。
- Issue [#32 ContextExplorer Full Refactor Migration - Remove Graph Engine Overdesign](https://github.com/DarumaPPAP/UnityAgent/issues/32) はopenのまま。ContextExplorerの移行とGraph検証の整理が未完了。

## 実装上の根拠

- Runner：`Runtime/Runner/Codex/codex_runner.py:130-159`。
- Orchestrator Handoff：`Orchestration/Orchestrator/orchestrator.py:43-69`。
- Dispatcher：`Runtime/Dispatcher/tool_runtime_dispatcher.py:85-215`。
- MyUnityMCP Scope：`Runtime/Tooling/Providers/MyUnityMcp/myunitymcp_provider.py:370-479`。
- Approval Guard：`Runtime/Guardrails/tool_runtime_guard.py:96-154`。
- Evidence append：`Persistence/Evidence/runtime_adapter.py:105-170`、`Persistence/Evidence/evidence_store.py:64-100`。
- Context Budget/Fingerprint：`Context/Assembly/materialize_context.py:252-337`。

## 未観測・未承認

- Unity Editor上のScene状態、MyUnityMCPの実際の変更対象、Unity CLIのBuild/Test、Player起動、Windows固有挙動。
- 対象GPU/CPUでのProfiler、GC、Build時間、Shader variant、描画品質のBefore/After。
- Runtime実行からPersistence Evidence、Eval Attribution、Operations DetectionまでのライブRun ID付きE2E。
- 現行v4.0と旧v3.1 Baselineの同一条件比較。旧Baselineを現行品質の証明には使わない。

## 証拠の扱い

- `not_observed`、`unavailable`、`implemented_unverified`は成功として集計しない。
- Compile結果だけでRuntime、Visual、Performance、Player、実機を承認しない。
- 本台帳のコマンドと結果は再実行可能な事実、Findingの改善案はレビュー判断として分離する。
