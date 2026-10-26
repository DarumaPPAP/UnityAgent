#if UNITY_EDITOR && !ARTIST_AUTHORITY_STANDALONE
using System;
using System.Collections;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;

namespace UnityArtist.Tests
{
	public sealed class CameraBindingTests
	{
		[Test]
		public void CameraPlanUsesInvariantNumbersUnderGermanCulture()
		{
			Type session = typeof(ArtistResult).Assembly.GetType("UnityArtist.ArtistSession", true);
			if ((bool)session.GetField("persistentBatchSession", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null))
			{
				Assert.Ignore("テストの Plan を永続 Batch 状態へ保存しないため、実行しません。");
			}
			using SceneFixture sceneFixture = new SceneFixture();
			CultureInfo previousCulture = CultureInfo.CurrentCulture;
			GameObject owned = new GameObject("artist-culture-test-" + Guid.NewGuid().ToString("N"));
			ArtistResult plan = null;
			try
			{
				Camera camera = owned.AddComponent<Camera>();
				camera.enabled = false;
				camera.fieldOfView = 40.25f;
				Assert.That(camera.gameObject.scene.IsValid(), Is.True, "Plan が列挙できる Scene Camera を自前で用意します。");
				CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("de-DE");
				string request = JsonUtility.ToJson(new ArtistIntent { targetName = owned.name, setCameraFieldOfView = true, cameraFieldOfView = 43.5f });
				plan = (ArtistResult)session.GetMethod("Plan", BindingFlags.Public | BindingFlags.Static).Invoke(null, new object[] { request, "" });
				Assert.That(plan.errors, Is.Empty, string.Join("; ", plan.errors.Select(error => error.code + ":" + error.message)));
				ArtistChange change = plan.exactDiff.Single();
				Assert.That(change.before, Is.EqualTo("40.25"));
				Assert.That(change.after, Is.EqualTo("43.5"));
				Assert.That(camera.fieldOfView, Is.EqualTo(40.25f), "Plan は自前 Camera の値も変更しません。");
			}
			finally
			{
				CultureInfo.CurrentCulture = previousCulture;
				if (plan != null && !string.IsNullOrEmpty(plan.planId))
				{
					((IDictionary)session.GetField("plans", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(plan.planId);
					((IList)session.GetField("history", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(plan.planId);
				}
				UnityEngine.Object.DestroyImmediate(owned);
			}
		}

		[Test]
		public void CaptureWithDuplicateExplicitCameraNameIsRejectedBeforeArtifacts()
		{
			Type session = typeof(ArtistResult).Assembly.GetType("UnityArtist.ArtistSession", true);
			if ((bool)session.GetField("persistentBatchSession", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null))
			{
				Assert.Ignore("旧実装の RED 確認でも永続 Batch 状態を変更しないため、実行しません。");
			}
			string name = "artist-duplicate-test-" + Guid.NewGuid().ToString("N");
			GameObject first = new GameObject(name);
			GameObject second = new GameObject(name);
			string capturesRoot = Path.Combine(Directory.GetParent(Application.dataPath).FullName, "Library", "UnityArtist", "Captures");
			string[] before = Directory.Exists(capturesRoot) ? Directory.GetDirectories(capturesRoot).OrderBy(value => value, StringComparer.Ordinal).ToArray() : new string[0];
			ArtistResult capture = null;
			try
			{
				Camera firstCamera = first.AddComponent<Camera>();
				Camera secondCamera = second.AddComponent<Camera>();
				firstCamera.enabled = false;
				secondCamera.enabled = false;
				Assert.That(firstCamera.gameObject.scene.IsValid() && secondCamera.gameObject.scene.IsValid(), Is.True, "同名 Camera が2つとも列挙対象になることを検証の前提とします。");
				capture = (ArtistResult)session.GetMethod("Capture", BindingFlags.Public | BindingFlags.Static).Invoke(null, new object[] { JsonUtility.ToJson(new ArtistIntent { captureCameraName = name }) });
				Assert.That(capture.errors.Any(error => error.code == "CAMERA_TARGET_AMBIGUOUS"), Is.True, "同名 Camera の先頭候補を撮影してはいけません。" + string.Join("; ", capture.errors.Select(error => error.code + ":" + error.message)));
				Assert.That(capture.captureId, Is.Null.Or.Empty);
				Assert.That(capture.evidence.Any(value => value.StartsWith("color_path:", StringComparison.Ordinal)), Is.False);
				string[] after = Directory.Exists(capturesRoot) ? Directory.GetDirectories(capturesRoot).OrderBy(value => value, StringComparer.Ordinal).ToArray() : new string[0];
				Assert.That(after, Is.EqualTo(before), "撮影先を一意に識別できない段階では出力先も作成しません。");
			}
			finally
			{
				try
				{
					// RED 確認で旧実装が生成した場合も、この呼出しの capture だけを破棄する。
					if (capture != null && !string.IsNullOrEmpty(capture.captureId))
					{
						string ownedPath = Path.GetFullPath(Path.Combine(capturesRoot, capture.captureId));
						Assert.That(Path.GetDirectoryName(ownedPath), Is.EqualTo(Path.GetFullPath(capturesRoot)));
						Assert.That(before, Does.Not.Contain(ownedPath), "テスト開始前から存在した出力は削除しません。");
						if (Directory.Exists(ownedPath))
						{
							Directory.Delete(ownedPath, true);
						}
						((IDictionary)session.GetField("captures", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(capture.captureId);
						((IList)session.GetField("history", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(capture.captureId);
					}
				}
				finally
				{
					UnityEngine.Object.DestroyImmediate(first);
					UnityEngine.Object.DestroyImmediate(second);
				}
			}
		}
	}
}
#endif
