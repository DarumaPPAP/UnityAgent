# Context Manifest 旧互換ツール

`Tools/ContextManifest/` は、旧Context Manifest構成を対象にした互換・検証用実装です。**現在のUnityAgent Productionで使用するCanonical Context Manifestの入口ではありません。**

このDirectory内の実装には、single-repo cutover以前のdot-ai layoutを読む処理が残っています。そのため、現在のProduction Routeへ接続したり、現行Authorityとして扱ったりしません。

## 現在の正本

現行UnityAgentでは、Context Manifestとその入力Authorityを次のように分離しています。

| 役割 | 現在の正本 |
| --- | --- |
| Context Manifest Builder | `Context/Manifest/build_context_manifest.py` |
| Context Manifest Schema | `Context/Manifest/context-manifest.schema.yaml` |
| Context Materialization | `Context/Assembly/materialize_context.py` |
| Context Pack | `Context/Packs/` |
| Context Budget | `Context/Budget/context-budget.yaml` |
| User Policy | `Policy/User/user-policy.yaml` |
| Quality Gate | `Policy/Evidence/quality-gates.yaml` |
| Risk | `Policy/Risk/risk-levels.yaml` |
| MCP Activation | `Runtime/Permissions/mcp-activation.yaml` |
| Parent Graph | `Orchestration/Definitions/development-parent-graph.yaml` |

## 現行Context Manifestの流れ

```text
User Request / Route
        ↓
Context Catalog
        ↓
Context Materialization
        ├─ Context Pack
        ├─ Task Contract
        ├─ Policy
        ├─ Skill
        └─ Required Source / Reference
        ↓
Context Budget
        ↓
Context Manifest
        ↓
Runtime Handoff / Evidence
```

Context ManifestはContextの実行Traceを表しますが、Policy、Route、Runtime Profile、Quality Gateなどの正本を置き換えません。

## 現行Builderの利用

```powershell
python .\Context\Manifest\build_context_manifest.py `
  --run-id <RUN_ID> `
  --route <ROUTE_ID> `
  --output .\Artifacts\ContextManifests\<RUN_ID>.yaml
```

Retry時は前Attemptを暗黙に現在値として扱わず、必要なProject Factを再観測または再検証したうえで `--previous-manifest-ref` を渡します。

## このDirectoryの扱い

- Current Productionの実行入口として使用しない
- 旧dot-ai layoutをCurrent Authorityへ戻す理由にしない
- 旧実装の互換確認・削除判断・Migration調査のためだけに参照する
- 現行Context Contractへ機能を移す場合は `Context/` 側のAuthority Boundaryを維持する
- `Tools/ContextManifest/` の生成物をPolicy / Route / Evidence / Production StateのSource of Truthとして扱わない

Repository全体の現行Contractを確認する場合は、次を使用します。

```powershell
python .\Tools\validate_all.py
```
