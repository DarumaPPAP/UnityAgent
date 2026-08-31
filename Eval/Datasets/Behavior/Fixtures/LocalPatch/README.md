# LocalPatch 挙動評価Fixture

MUTATION系Evalが既存C#への局所変更を観測するための読み取り専用Source Fixtureです。

- Sourceは `CameraDebugger.cs` だけです。
- RuntimeはSandbox Copyを作成し、そのCopyだけを変更します。
- 元のSource Fixture自体は変更しません。
