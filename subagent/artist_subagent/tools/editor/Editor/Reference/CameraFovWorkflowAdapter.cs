#if UNITY_EDITOR

using System;
using UnityEditor;
using UnityEngine;

namespace UnityArtist
{
	/// <summary>
	/// The single typed Camera FOV mutation adapter used by the existing Artist
	/// pipeline. UnityAgent owns approval and the Runtime owns dispatch; this
	/// adapter only applies an already-approved, exact Camera field change.
	/// </summary>
	public static class CameraFovWorkflowAdapter
	{
		public const string ComponentType = "UnityEngine.Camera";
		public const string PropertyPath = "Camera.fieldOfView";
		public const string MutationChannel = "serialized_property";
		public const string Unit = "degree";
		public const string ValueType = "float";

		public static bool Validate(Camera camera, string targetGuid, string componentType, string propertyPath, float minimum, float maximum, out string error)
		{
			error = string.Empty;
			if (camera == null)
			{
				error = "An exact Camera target is required.";
				return false;
			}
			if (string.IsNullOrWhiteSpace(targetGuid))
			{
				error = "The real GlobalObjectId of the Camera target is required.";
				return false;
			}
			if (!string.Equals(componentType, ComponentType, StringComparison.Ordinal) || !string.Equals(propertyPath, PropertyPath, StringComparison.Ordinal))
			{
				error = "The Camera FOV target/property contract is invalid.";
				return false;
			}
			string observedGuid;
			try { observedGuid = GlobalObjectId.GetGlobalObjectIdSlow(camera).ToString(); }
			catch (Exception exception)
			{
				error = "The Camera GlobalObjectId could not be observed: " + exception.Message;
				return false;
			}
			if (!string.Equals(observedGuid, targetGuid, StringComparison.Ordinal))
			{
				error = "The Camera GlobalObjectId does not match the approved target.";
				return false;
			}
			if (float.IsNaN(minimum) || float.IsInfinity(minimum) || float.IsNaN(maximum) || float.IsInfinity(maximum) || minimum <= 0.0f || minimum > maximum || maximum >= 180.0f)
			{
				error = "Camera FOV envelope must be finite and within (0, 180).";
				return false;
			}
			return true;
		}

		public static bool TryApply(Camera camera, string targetGuid, string componentType, string propertyPath, float value, float minimum, float maximum, out float before, out float after, out string error)
		{
			before = 0.0f;
			after = 0.0f;
			if (!Validate(camera, targetGuid, componentType, propertyPath, minimum, maximum, out error)) return false;
			return TryApply(camera, value, minimum, maximum, out before, out after, out error);
		}

		public static bool TryApply(Camera camera, float value, float minimum, float maximum, out float before, out float after, out string error)
		{
			before = 0.0f;
			after = 0.0f;
			error = string.Empty;
			if (camera == null)
			{
				error = "An exact Camera target is required.";
				return false;
			}
			if (float.IsNaN(value) || float.IsInfinity(value) || float.IsNaN(minimum) || float.IsInfinity(minimum) || float.IsNaN(maximum) || float.IsInfinity(maximum) || minimum <= 0.0f || minimum > maximum || maximum >= 180.0f)
			{
				error = "Camera FOV envelope must be finite and within (0, 180).";
				return false;
			}
			if (value < minimum || value > maximum)
			{
				error = "Camera FOV is outside the approved parameter envelope.";
				return false;
			}

			Undo.RecordObject(camera, "UnityArtistCLI Camera FOV Refinement");
			before = camera.fieldOfView;
			camera.fieldOfView = value;
			after = camera.fieldOfView;
			return true;
		}
	}
}

#endif
