namespace CameraDebugging;

public sealed class CameraDebugger
{
    public float FarClip { get; private set; } = 1000f;

    public void SetFarClip(float value)
    {
        FarClip = value;
    }
}
