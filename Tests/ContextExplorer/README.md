# Context Explorer Test Suite

このSuiteは、Context ExplorerがCanonical Context Contractを決定的に表示することを検証します。Production Routing、SubAgent Resolution、ExecutionのAuthorityをテストするSuiteではありません。

## Coverage

- `test_context_map.py`: `Context/Packs/*.yaml`からの決定的Map、Provenance、Schema、Human Concept、Static Bundleへの注入
- `test_security.py`: Static / Offline / Read-only Frontend、Context Map用語、One-hop Relation、Repository Path境界
- `test_migration.py`: 旧GraphObservatory層やgeneric graph engineの再導入禁止、Authority境界、`validate_all.py`統合

基本Gate:

```bash
python Tools/validate_all.py
```

Context Explorerの実装と表示制約は`../../Tools/ContextExplorer/README.md`を参照してください。
