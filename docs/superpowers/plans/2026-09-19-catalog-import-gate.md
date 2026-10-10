# Plan: UnityAgent Catalog Import Gate

日付: 2026-09-19

## 目的

Hubの既存SnapshotをOfflineで検証し、現在のCatalogへ安全に取り込むための読取専用Import PlanをUnityAgentへ追加する。契約変更は別PRに分離し、Mergeは行わない。

## 実装順序

1. `src/unityagent/runtime/reference_implementation/profiles.py` に厳密なMapping入口と正規化済みCatalog表現を追加し、Snapshot parserが既存Profile形式だけを受け取れるようにする。
2. `src/unityagent/runtime/reference_implementation/catalog_import_gate.py` を追加する。Unique-key YAML parse、SHA-256照合、Profile/Provider/Environment/semantic validation、Added/Removed/Changed/No-op diff、protected-fieldとRiskを実装する。
3. `tools/import_subagent_catalog.py` と `tools/validate_catalog_import_gate.py` を追加し、JSON Import Planを出力する。既存Catalogへのwrite pathは持たせない。
4. 失敗テストを先に追加し、正常Snapshot、Hub現行producer mismatch、unknown Fact、duplicate Capability、削除、protected Field、tamper、途中失敗、Runtime eligibility保持を検証する。
5. `src/unityagent/cli.py` とReference fingerprintの `runtime_profile_revision` にProvider RegistryとSubAgent Catalogを含め、既存Resume/Evidence契約を変更せずにRevisionを追跡する。
6. `tools/validate_all.py` へImport Gate validatorを追加し、既存CIでCatalog GateとRuntime testsが実行される状態にする。
7. UnityAgentの運用文書とHubのArchitecture文書を、Environment FactをHubが生成せずUnityAgent discoveryが三値観測する現行実装に合わせて更新する。

## 検証

- 変更前に対象Unit/Integration/Negative testをREDで確認する。
- 変更後に対象テスト、Hub validator/tests、UnityAgent `tools/validate_all.py`、Git diff、workflow statusを確認する。
- Unity 2022/Unity 6の実Editor実行や実Backend availabilityはこのOffline Gateの対象外として未実施と報告する。
