# CameraDebugger Behavior Fixture

これは`runtime_unity_ci`が非対話の`TestHarness`で使う、読み取り専用の挙動評価Fixtureです。本番Projectや配布Packageではありません。

- Fixture内の`CameraDebugger.cs`と生成C#を組み合わせてコンパイルできたときだけ、Compile Evidenceを観測済みとします。
- Unity固有のRuntime / Visual EvidenceはこのFixtureに含まれません。
- この結果だけでUnity Editor、Player、SubAgentの実行可能性を証明したことにはなりません。
