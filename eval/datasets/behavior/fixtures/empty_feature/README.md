# EmptyFeature Mutation Fixture

MUTATION Evalで「新規C#を作成する」経路を、本番Repositoryを変更せずに検証する空Fixtureです。

- Fixtureに恒久C#ファイルは置きません。
- Runtimeが`CameraDebugger.cs`を生成し、評価対象はFixture内の生成物です。
- 実Projectへの変更、Unity EditorでのCompile、SubAgentのeligibilityを示すFixtureではありません。
