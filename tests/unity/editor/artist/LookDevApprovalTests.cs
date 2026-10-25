#if UNITY_EDITOR && !ARTIST_AUTHORITY_STANDALONE
using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;

namespace UnityArtist.Tests
{
	public sealed class LookDevApprovalTests
	{
		[Test]
		public void FogMutationDoesNotDirtyOtherLoadedScene()
		{
			using SceneFixture other = new SceneFixture();
			using SceneFixture target = new SceneFixture();
			UnityEngine.SceneManagement.Scene otherScene = UnityEngine.SceneManagement.SceneManager.GetSceneByPath(other.ScenePath);
			Assert.That(otherScene.isDirty, Is.False);
			ArtistResult result = new ArtistResult();
			bool applied = (bool)Session().GetMethod("ApplyIntent", BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, new object[] { new ArtistIntent { setFog = true, fogDensity = 0.02f }, result });
			Assert.That(applied, Is.True);
			Assert.That(otherScene.isDirty, Is.False, "承認対象外のSceneへdirty状態を広げてはいけません。");
		}

		[TestCase(true)]
		[TestCase(false)]
		public void AmbiguousNamedTargetsCannotCreateApprovalPlan(bool cameraTarget)
		{
			using SceneFixture fixture = new SceneFixture();
			string name = "Owned duplicate " + Guid.NewGuid().ToString("N");
			for (int index = 0; index < 2; index++)
			{
				GameObject owned = new GameObject(name);
				if (cameraTarget) { owned.AddComponent<Camera>(); } else { owned.AddComponent<Light>(); }
			}
			ArtistResult plan = Plan(new ArtistIntent { targetName = name, setCameraFieldOfView = cameraTarget, cameraFieldOfView = 45f, setLightIntensity = !cameraTarget, lightIntensity = 2f });
			try { Assert.That(plan.errors, Is.Not.Empty, "同名候補から任意の対象を承認してはいけません。"); }
			finally { Forget(plan); }
		}

		[TestCase(true)]
		[TestCase(false)]
		public void ReplacementTargetInvalidatesReviewedRevision(bool cameraTarget)
		{
			using SceneFixture fixture = new SceneFixture();
			string name = "Owned replacement " + Guid.NewGuid().ToString("N");
			GameObject original = new GameObject(name);
			if (cameraTarget) { original.AddComponent<Camera>(); } else { original.AddComponent<Light>(); }
			ArtistResult plan = Plan(new ArtistIntent { targetName = name, setCameraFieldOfView = cameraTarget, cameraFieldOfView = 45f, setLightIntensity = !cameraTarget, lightIntensity = 2f });
			try
			{
				Assert.That(plan.errors, Is.Empty);
				Component originalTarget = cameraTarget ? (Component)original.GetComponent<Camera>() : original.GetComponent<Light>();
				string previousIdentity = UnityEditor.GlobalObjectId.GetGlobalObjectIdSlow(originalTarget) + ":instance:" + SessionIdentity(originalTarget);
				UnityEngine.Object.DestroyImmediate(original);
				GameObject replacement = new GameObject(name);
				if (cameraTarget) { replacement.AddComponent<Camera>(); } else { replacement.AddComponent<Light>(); }
				Component replacementTarget = cameraTarget ? (Component)replacement.GetComponent<Camera>() : replacement.GetComponent<Light>();
				string replacementIdentity = UnityEditor.GlobalObjectId.GetGlobalObjectIdSlow(replacementTarget) + ":instance:" + SessionIdentity(replacementTarget);
				ArtistResult result = (ArtistResult)Session().GetMethod("Apply").Invoke(null, new object[] { plan.planId, plan.revision, "forged-token" });
				Assert.That(result.errors.Any(error => error.code == "STALE_REVISION"), Is.True, "同値の別オブジェクトへ承認を移してはいけません。" + previousIdentity + " -> " + replacementIdentity + "; errors=" + string.Join(",", result.errors.Select(error => error.code)));
			}
			finally { Forget(plan); }
		}

		[Test]
		public void LightPlanUsesObservedValueAndExactOwnedScenePath()
		{
			using (SceneFixture fixture = new SceneFixture())
			{
				GameObject owned = new GameObject("Artist Light " + Guid.NewGuid().ToString("N"));
				Light light = owned.AddComponent<Light>();
				light.intensity = 1.25f;
				ArtistResult plan = Plan(new ArtistIntent { targetName = light.name, setLightIntensity = true, lightIntensity = 2.5f });
				try
				{
					Assert.That(plan.errors, Is.Empty);
					Assert.That(plan.exactDiff.Single().before, Is.EqualTo("1.25"));
					IEnumerable paths = (IEnumerable)typeof(ArtistResult).GetField("mutationPaths").GetValue(plan);
					Assert.That(paths.Cast<string>().ToArray(), Is.EqualTo(new[] { fixture.ScenePath }));
				}
				finally { Forget(plan); }
			}
		}

		[Test]
		public void FogPlanIncludesEnabledStateAndFogChangesInvalidateRevision()
		{
			using (SceneFixture fixture = new SceneFixture())
			{
				RenderSettings.fog = false;
				RenderSettings.fogDensity = 0.01f;
				ArtistResult plan = Plan(new ArtistIntent { setFog = true, fogDensity = 0.02f });
				try
				{
					Assert.That(plan.errors, Is.Empty);
					Assert.That(plan.exactDiff.Any(change => change.property == "fog" && change.before == "false" && change.after == "true"), Is.True);
					RenderSettings.fogDensity = 0.03f;
					ArtistResult result = (ArtistResult)Session().GetMethod("Apply").Invoke(null, new object[] { plan.planId, plan.revision, "forged-token" });
					Assert.That(result.errors.Any(error => error.code == "STALE_REVISION"), Is.True);
				}
				finally { Forget(plan); }
			}
		}

		private Type Session() => typeof(ArtistResult).Assembly.GetType("UnityArtist.ArtistSession", true);
		private string SessionIdentity(UnityEngine.Object value)
		{
#if UNITY_6000_6_OR_NEWER
			return value.GetEntityId().ToString();
#else
			return value.GetInstanceID().ToString(System.Globalization.CultureInfo.InvariantCulture);
#endif
		}
		private ArtistResult Plan(ArtistIntent intent) => (ArtistResult)Session().GetMethod("Plan").Invoke(null, new object[] { JsonUtility.ToJson(intent), "" });
		private void Forget(ArtistResult plan)
		{
			// Plan作成前に拒否された場合はテスト所有の保存状態がない。
			if (string.IsNullOrEmpty(plan.planId)) return;
			((IDictionary)Session().GetField("plans", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(plan.planId);
			((IList)Session().GetField("history", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(plan.planId);
		}
	}
}
#endif
