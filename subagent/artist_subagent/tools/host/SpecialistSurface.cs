namespace UnityArtist.Cli;

/// <summary>
/// Typed capability vocabulary used by the Runtime-owned specialist session.
/// This is intentionally not a CLI command and has no executable/process API.
/// </summary>
internal static class SpecialistSurface
{
    public static readonly IReadOnlySet<string> AllowedCapabilities = new HashSet<string>(StringComparer.Ordinal)
    {
        "artist.camera.inspect", "artist.camera.refine", "visual.capture"
    };

    public static readonly IReadOnlySet<string> AllowedMessages = new HashSet<string>(StringComparer.Ordinal)
    {
        "hello", "grant", "inspect", "propose_action", "capture", "evaluate", "complete"
    };

    public static bool IsInstallerCapability(string capability) =>
        capability.Contains("install", StringComparison.OrdinalIgnoreCase) ||
        capability.Contains("package", StringComparison.OrdinalIgnoreCase) ||
        capability.Contains("shell", StringComparison.OrdinalIgnoreCase);

    public static CameraFovRequest ValidateCameraFovRequest(
        string targetGuid,
        string componentType,
        string propertyPath,
        float value,
        float minimum,
        float maximum,
        string expectedRevision)
    {
        if (string.IsNullOrWhiteSpace(targetGuid)) throw new ArgumentException("targetGuid is required", nameof(targetGuid));
        if (!string.Equals(componentType, "UnityEngine.Camera", StringComparison.Ordinal)) throw new ArgumentException("Only UnityEngine.Camera is supported.", nameof(componentType));
        if (!string.Equals(propertyPath, "Camera.fieldOfView", StringComparison.Ordinal)) throw new ArgumentException("Only Camera.fieldOfView is supported.", nameof(propertyPath));
        if (float.IsNaN(value) || float.IsInfinity(value) || float.IsNaN(minimum) || float.IsInfinity(minimum) || float.IsNaN(maximum) || float.IsInfinity(maximum) || minimum <= 0 || minimum > maximum || maximum >= 180 || value < minimum || value > maximum)
            throw new ArgumentOutOfRangeException(nameof(value), "Camera FOV is outside the approved finite envelope.");
        if (string.IsNullOrWhiteSpace(expectedRevision)) throw new ArgumentException("expectedRevision is required", nameof(expectedRevision));
        return new CameraFovRequest(targetGuid, componentType, propertyPath, value, minimum, maximum, expectedRevision);
    }
}

internal sealed record CameraFovRequest(
    string TargetGuid,
    string ComponentType,
    string PropertyPath,
    float Value,
    float Minimum,
    float Maximum,
    string ExpectedRevision)
{
    public string Unit => "degree";
    public string ValueType => "float";
    public string MutationChannel => "serialized_property";
}
