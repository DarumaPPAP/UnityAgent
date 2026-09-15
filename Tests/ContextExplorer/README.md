# Context Explorer Tests

Issue #32の完了条件を固定するための回帰テストです。

- `test_context_map.py` — `Context/Packs/*.yaml` からの決定的Map生成、Provenance、Schema、7 Human Concepts
- `test_security.py` — Static / Offline / Read-only FrontendとRepository Path境界
- `test_migration.py` — 旧GraphObservatory層の不在、generic graph engine非復活、`validate_all.py`統合

このSuiteは `Tools/validate_all.py` の標準Gateから実行します。
