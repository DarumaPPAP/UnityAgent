#if UNITY_EDITOR && !ARTIST_AUTHORITY_STANDALONE
using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;

namespace UnityArtist.Tests
{
	public sealed class CinematicApprovalTests
	{
		[Test]
		public void TrackPlanReportsExactAbsentStateAndDoesNotCreateTrack()
		{
			WithTimeline((session, director, timeline) =>
			{
				ArtistResult plan = Invoke(session, "plan", new CinematicRequest { directorName = director.name, trackKind = "activation", trackName = "Owned Activation" });
				try
				{
					Assert.That(plan.errors, Is.Empty);
					Assert.That(plan.exactDiff.Single().before, Is.EqualTo("absent"));
					Assert.That(plan.exactDiff.Single().after, Does.Contain("Owned Activation"));
					Assert.That(RootTracks(timeline).Count(), Is.Zero, "Plan はテスト所有Timelineも変更しません。");
				}
				finally { ForgetPlan(session, plan.planId); }
			});
		}

		[Test]
		public void BindingPlanRejectsMissingTargetBeforeApproval()
		{
			WithTimeline((session, director, timeline) =>
			{
				ArtistResult plan = Invoke(session, "plan", new CinematicRequest { directorName = director.name, trackKind = "binding", trackName = "Missing Track", bindingTargetName = "Missing Target" });
				try
				{
					Assert.That(plan.errors.Any(error => error.code == "CINEMATIC_TARGET_NOT_FOUND"), Is.True);
					Assert.That(plan.planId, Is.Null.Or.Empty);
				}
				finally { ForgetPlan(session, plan.planId); }
			});
		}

		[Test]
		public void TimelineChangesInvalidatePreparedApprovalBeforeAuthorityContact()
		{
			WithTimeline((session, director, timeline) =>
			{
				ArtistResult plan = Invoke(session, "plan", new CinematicRequest { directorName = director.name, trackKind = "activation", trackName = "Planned Track" });
				try
				{
					Type trackType = Type.GetType("UnityEngine.Timeline.ActivationTrack, Unity.Timeline", true);
					timeline.GetType().GetMethod("CreateTrack", new[] { typeof(Type), trackType.BaseType, typeof(string) }).Invoke(timeline, new object[] { trackType, null, "Concurrent Track" });
					ArtistResult applied = Invoke(session, "apply", null, plan.planId, plan.revision, "forged-token");
					Assert.That(applied.errors.Any(error => error.code == "STALE_REVISION"), Is.True, "Timeline変更を承認通信より前に検出します。");
					Assert.That(RootTracks(timeline).Count(), Is.EqualTo(1));
				}
				finally { ForgetPlan(session, plan.planId); }
			});
		}

		[TestCase("activation")]
		[TestCase("animation")]
		[TestCase("control")]
		[TestCase("signal")]
		[TestCase("marker")]
		public void PlannedExactStateMatchesActualTimelineArtifact(string kind)
		{
			WithTimeline((session, director, timeline) =>
			{
				CinematicRequest request = new CinematicRequest { directorName = director.name, trackKind = kind, trackName = "Owned " + kind, markerTime = 0.1234567f };
				ArtistResult plan = Invoke(session, "plan", request);
				try
				{
					Assert.That(plan.errors, Is.Empty);
					Assert.That(plan.exactDiff.Single().before, Is.Not.Empty);
					ArtistResult applied = new ArtistResult();
					Assert.That((bool)session.GetMethod("ApplyCinematic", BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, new object[] { request, applied }), Is.True, string.Join("; ", applied.errors.Select(error => error.message)));
					object[] arguments = { director, request, new ArtistResult(), null };
					Assert.That((bool)session.GetMethod("TryObserveCinematicChange", BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, arguments), Is.True);
					Assert.That(((ArtistChange)arguments[3]).before, Is.EqualTo(plan.exactDiff.Single().after), "実際のTimeline状態をPlanのExact Diffと比較します。認可E2Eとは別のUnit Testです。");
				}
				finally { ForgetPlan(session, plan.planId); }
			});
		}

		[Test]
		public void BindingExactDiffMatchesActualObjectReferences()
		{
			WithTimeline((session, director, timeline) =>
			{
				Type trackType = Type.GetType("UnityEngine.Timeline.ActivationTrack, Unity.Timeline", true);
				timeline.GetType().GetMethod("CreateTrack", new[] { typeof(Type), trackType.BaseType, typeof(string) }).Invoke(timeline, new object[] { trackType, null, "Owned Binding" });
				CinematicRequest request = new CinematicRequest { directorName = director.name, trackKind = "binding", trackName = "Owned Binding", bindingTargetName = director.name };
				AssertPlannedStateMatches(session, director, request);
			});
		}

		[TestCase("cinemachine_shot")]
		[TestCase("shot")]
		public void ShotExactDiffMatchesCreatedAndUpdatedClip(string kind)
		{
			WithTimeline((session, director, timeline) =>
			{
				Type cameraType = Type.GetType("Unity.Cinemachine.CinemachineCamera, Unity.Cinemachine", false) ?? Type.GetType("Cinemachine.CinemachineVirtualCamera, Cinemachine", false);
				if (cameraType == null)
				{
					Assert.Ignore("Cinemachine Packageを導入したFixtureで実行します。");
				}
				director.gameObject.AddComponent(cameraType);
				CinematicRequest request = new CinematicRequest { directorName = director.name, trackKind = kind, trackName = "Owned Shot", bindingTargetName = director.name, clipStart = 0.125f, clipDuration = 1.234567f };
				AssertPlannedStateMatches(session, director, request);
				object track = RootTracks(timeline).Single();
				object clip = ((IEnumerable)track.GetType().GetMethod("GetClips").Invoke(track, null)).Cast<object>().Single();
				object asset = clip.GetType().GetProperty("asset").GetValue(clip);
				FieldInfo referenceField = asset.GetType().GetField("VirtualCamera");
				object reference = referenceField.GetValue(asset);
				PropertyName referenceName = new PropertyName("owned-camera-reference");
				reference.GetType().GetField("exposedName").SetValue(reference, referenceName);
				referenceField.SetValue(asset, reference);
				GameObject other = new GameObject("Other owned camera");
				director.SetReferenceValue(referenceName, other.AddComponent(cameraType));
				request.clipStart = 1.125f;
				request.clipDuration = 2.234567f;
				AssertPlannedStateMatches(session, director, request);
				reference = referenceField.GetValue(asset);
				Assert.That(reference.GetType().GetMethod("Resolve").Invoke(reference, new object[] { director }), Is.EqualTo(director.GetComponent(cameraType)), "実際にDirector経由で解決されるCameraを検証します。");
			});
		}

		private void AssertPlannedStateMatches(Type session, PlayableDirector director, CinematicRequest request)
		{
			ArtistResult plan = Invoke(session, "plan", request);
			try
			{
				Assert.That(plan.errors, Is.Empty, string.Join("; ", plan.errors.Select(error => error.message)));
				ArtistResult applied = new ArtistResult();
				Assert.That((bool)session.GetMethod("ApplyCinematic", BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, new object[] { request, applied }), Is.True, string.Join("; ", applied.errors.Select(error => error.message)));
				object[] arguments = { director, request, new ArtistResult(), null };
				Assert.That((bool)session.GetMethod("TryObserveCinematicChange", BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, arguments), Is.True);
				Assert.That(((ArtistChange)arguments[3]).before, Is.EqualTo(plan.exactDiff.Single().after));
			}
			finally { ForgetPlan(session, plan.planId); }
		}

		private void WithTimeline(Action<Type, PlayableDirector, ScriptableObject> test)
		{
			Type session = typeof(ArtistResult).Assembly.GetType("UnityArtist.ArtistSession", true);
			if ((bool)session.GetField("persistentBatchSession", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null))
			{
				Assert.Ignore("テストのPlanを実行中の永続Batch状態へ保存しません。");
			}
			Type timelineType = Type.GetType("UnityEngine.Timeline.TimelineAsset, Unity.Timeline", false);
			if (timelineType == null)
			{
				Assert.Ignore("このProjectにはTimeline Packageが導入されていません。");
			}
			SceneFixture fixture = new SceneFixture();
			GameObject owned = new GameObject("artist-cinematic-test-" + Guid.NewGuid().ToString("N"));
			ScriptableObject timeline = ScriptableObject.CreateInstance(timelineType);
			AssetDatabase.CreateAsset(timeline, fixture.Folder + "/Timeline.playable");
			Undo.IncrementCurrentGroup();
			int undoGroup = Undo.GetCurrentGroup();
			try
			{
				PlayableDirector director = owned.AddComponent<PlayableDirector>();
				director.playableAsset = (PlayableAsset)timeline;
				test(session, director, timeline);
			}
			finally
			{
				Undo.RevertAllDownToGroup(undoGroup);
				fixture.Dispose();
			}
		}

		private ArtistResult Invoke(Type session, string operation, CinematicRequest request, string planId = "", string revision = "", string token = "") => (ArtistResult)session.GetMethod("Cinematic", BindingFlags.Public | BindingFlags.Static).Invoke(null, new object[] { operation, request == null ? "{}" : JsonUtility.ToJson(request), planId, revision, token });
		private System.Collections.Generic.IEnumerable<UnityEngine.Object> RootTracks(ScriptableObject timeline) => ((IEnumerable)timeline.GetType().GetMethod("GetRootTracks").Invoke(timeline, null)).Cast<UnityEngine.Object>();
		private void ForgetPlan(Type session, string planId)
		{
			// Plan作成前に拒否された場合には削除するテスト所有状態がありません。
			if (string.IsNullOrEmpty(planId)) return;
			((IDictionary)session.GetField("plans", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(planId);
			((IList)session.GetField("history", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(planId);
		}
	}
}
#endif
