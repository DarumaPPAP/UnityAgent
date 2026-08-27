namespace CameraDebugging;

public sealed class CameraDebugger
{
    private float _farClipValue = 1000f;

    // Behavior Eval fixture: this symbol is intentionally invalid so the local-fix task has one bounded compile error.
    public float FarClip => _missingFarClipValue;
}
