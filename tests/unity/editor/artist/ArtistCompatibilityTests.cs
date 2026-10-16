#if UNITY_EDITOR

using NUnit.Framework;

namespace UnityArtist.Tests
{
	public sealed class ArtistCompatibilityTests
	{
		[Test]
		public void ReleaseMatrixAcceptsUnity6Pipelines()
		{
			Assert.That(ArtistCompatibility.IsSupported("6000.6.0f1", "builtin"), Is.True);
			Assert.That(ArtistCompatibility.IsSupported("6000.6.0f1", "urp"), Is.True);
			Assert.That(ArtistCompatibility.IsSupported("6000.6.0f1", "hdrp"), Is.True);
		}

		[Test]
		public void UnsupportedPipelineIsRejectedBeforeMutation()
		{
			Assert.That(ArtistCompatibility.IsSupported("2022.3.22f1", "builtin"), Is.False);
			Assert.That(ArtistCompatibility.IsSupported("2022.3.22f1", "urp"), Is.False);
			Assert.That(ArtistCompatibility.IsSupported("2022.3.22f1", "hdrp"), Is.False);
			Assert.That(ArtistCompatibility.IsSupported("2023.2.0f1", "builtin"), Is.False);
		}
	}
}

#endif
