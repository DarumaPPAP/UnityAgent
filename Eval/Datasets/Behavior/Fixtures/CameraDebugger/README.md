# CameraDebugger 挙動評価Fixture

`RuntimeProfile: runtime_unity_ci` が参照する読み取り専用の評価Fixtureです。

- Runtimeは `TestHarness` を非対話で実行します。
- コンパイルEvidenceは、このFixtureに存在する `CameraDebugger.cs` が生成C#と組み合わせてコンパイル可能な場合だけ観測済みになります。
- Unity固有のRuntime / Visual Evidenceは、このFixtureには含めません。
