#if UNITY_EDITOR

using System;

namespace UnityArtist
{
	public enum E_ARTIST_API_PATCH_BUCKET
	{
		BASE,
		UNITY_6000_4,
		UNITY_6000_5,
		UNITY_6000_7
	}

	/// <summary>
	/// Maintains the release matrix in coarse API buckets. No per-patch-version
	/// source fork is allowed; the Editor command layer selects the pipeline adapter.
	/// </summary>
	public static class ArtistCompatibility
	{
		public static bool IsSupported(string unityVersion, string renderPipeline)
		{
			if (string.IsNullOrWhiteSpace(unityVersion) || string.IsNullOrWhiteSpace(renderPipeline)) return false;
			return unityVersion.StartsWith("6000.", StringComparison.Ordinal)
				&& (renderPipeline == "builtin" || renderPipeline == "urp" || renderPipeline == "hdrp");
		}

		public static string SupportTier(string unityVersion, string renderPipeline)
		{
			return IsSupported(unityVersion, renderPipeline) ? "primary" : "unsupported";
		}

		public static string Backend(string renderPipeline)
		{
			return renderPipeline == "builtin" ? "builtin_editor_api" : renderPipeline + "_native_api";
		}
	}
}

#endif
