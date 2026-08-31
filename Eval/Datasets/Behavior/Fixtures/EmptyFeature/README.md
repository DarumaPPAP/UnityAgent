# EmptyFeature 挙動評価Fixture

MUTATION系Evalが本番Repositoryを変更せずに「新規C#を作成する」経路を観測するための空Fixtureです。

- 恒久的なC#ファイルは配置しません。
- Runtimeが `CameraDebugger.cs` を生成します。
- Working Treeの差分はFixture内の生成物だけを観測します。
