# LocalPatch Mutation Fixture

MUTATION Evalで既存C#への局所変更を検証する読み取り専用Source Fixtureです。

- Sourceは`CameraDebugger.cs`だけです。
- RuntimeはSandbox Copyを作り、そのCopyだけを変更します。
- 元Fixtureは変更しません。結果はEval用の局所Patch検証であり、実Projectへの承認済みMutationを示すものではありません。
