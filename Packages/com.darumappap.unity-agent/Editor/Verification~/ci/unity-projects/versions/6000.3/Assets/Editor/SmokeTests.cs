using NUnit.Framework;
using UnityEngine;
using UnityArtist;
namespace UnityCi {
 public class MinimalTests {
  [Test] public void ArtistPackageImportsAndRejectsHistoricalEditor() {
   Assert.IsTrue(ArtistCompatibility.IsSupported(Application.unityVersion, "builtin"));
   Assert.IsFalse(ArtistCompatibility.IsSupported("2022.3.62f1", "builtin"));
   Assert.IsFalse(ArtistCompatibility.IsSupported(Application.unityVersion, "unknown"));
  }
 }
}
