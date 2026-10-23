# Python内部モジュールの命名方針

## 原則

`src/unityagent/` 配下の内部Pythonファイルは、**親パッケージと合わせて意味が一意に読める最短の名前**を優先する。短さだけのために `core.py`、`utils.py`、`manager.py` へ改名しない。

- `context/manifest/build.py`：親の `context/manifest` が対象を示すため `build_context_manifest.py` としない。
- `context/budget/evaluate.py`：Context Budgetを評価する責務を動詞で表す。
- `runtime/telemetry/builders.py`：Span・Metric・Log等を作成する実際の役割に一致させる。
- `control_plane/workspace_tasks.py`：Workspace上のTask実行を表し、`task_execution.py` と区別する。

## リネームの安全条件

1. 同名の新モジュールが存在しないこと。既存公開API名、CLI、Provider ID、Schema IDを勝手に変更しないこと。
2. Python import、文字列指定のpatch/dynamic import、テスト、配布検証、参照文書、現行パスマップを同一PRで更新すること。
3. 移行期のInventory CSV・過去のEvidence・過去のRelease Snapshotは書換えないこと。
4. `tests/architecture/test_python_module_names.py` に回帰検証を追加すること。
5. Build済みWheelとSource Checkoutの双方で検証し、未観測のUnity Editor E2EをPASSとしないこと。

## 今回の意図的な見送り

- `control_plane/unity_agent_control_plane.py`：CLI、UPM導入スクリプト、Layer契約にまたがる参照があり、単なる内部リネームではない。
- `runtime/runner/codex/codex_runner.py` と `runtime/tooling/providers/*/*_provider.py`：外部連携の識別可能性と公開Import互換性が重要。
- `persistence/*/*_store.py`：全て `store.py` にすると横断検索時の区別が難しくなる。

公開経路の改名が必要な場合は、互換性・移行期間・Release影響を別Decisionとして扱う。
