# Context Explorer Tests

Issue #32のContextExplorer migrationと、Issue #131のGraph Visualization最終境界を固定する回帰テストです。

- `test_context_map.py` — `Context/Packs/*.yaml` からの決定的Map生成、Provenance、Schema、7 Human Concepts、Static Bundleへの`ContextMap` injection
- `test_security.py` — Static / Offline / Read-only Frontend、Context Map vocabulary、explicit one-hop relation projection、Repository Path境界
- `test_migration.py` — 旧GraphObservatory層の不在、generic graph engine非復活、`__CONTEXT_GRAPH__`非復活、`Orchestration/Graph`とのAuthority分離、`validate_all.py`統合

このSuiteは `Tools/validate_all.py` の標準Gateから実行します。
