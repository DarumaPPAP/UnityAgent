# Local Patch Behavior Eval Fixture

`CameraDebugger.cs`には既知Compile Errorを1件だけ意図的に含める。

Actual Behavior Evalでは、このFixtureをSandboxへCopyし、`CameraDebugger.cs`以外への変更、Rename、新規File、無関係RefactorをMutation Regressionとして扱う。
