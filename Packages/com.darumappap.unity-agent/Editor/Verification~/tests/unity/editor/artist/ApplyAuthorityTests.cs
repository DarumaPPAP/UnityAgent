#if UNITY_EDITOR && !ARTIST_AUTHORITY_STANDALONE
using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;

namespace UnityArtist.Tests
{
	public sealed class ApplyAuthorityTests
	{
		[Test]
		public void DirectApplyWithoutControlPlaneCannotChangeScene()
		{
			string descriptor = Path.Combine(Directory.GetParent(Application.dataPath).FullName, "Library", "UnityAgent", "ArtistAuthority.json");
			// 実行中の Control Plane が所有する descriptor をテスト都合で削除・上書きしない。
			if (File.Exists(descriptor))
			{
				Assert.Ignore("Control Plane の承認セッションが実行中です。");
			}
			Type session = typeof(ArtistResult).Assembly.GetType("UnityArtist.ArtistSession", true);
			// Batch の永続状態は呼出し元が所有するため、テストから Plan を保存しない。
			if ((bool)session.GetField("persistentBatchSession", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null))
			{
				Assert.Ignore("永続 Batch セッションでは実行しません。");
			}
			using SceneFixture sceneFixture = new SceneFixture();
			ArtistResult plan = (ArtistResult)session.GetMethod("Plan", BindingFlags.Public | BindingFlags.Static).Invoke(null, new object[] { "{\"setFog\":true,\"fogDensity\":0.1234}", "" });
			if (!plan.support.supported)
			{
				Assert.Ignore("この Editor は Artist の対応対象外です。");
			}
			// HDRP 等の外部 Volume 設定を fixture として要求しない。
			if (plan.errors.Count != 0)
			{
				Assert.Ignore("この Project では Fog Plan の前提が成立しません。");
			}
			bool fogBefore = RenderSettings.fog;
			float densityBefore = RenderSettings.fogDensity;
			try
			{
				ArtistResult applied = (ArtistResult)session.GetMethod("Apply", BindingFlags.Public | BindingFlags.Static).Invoke(null, new object[] { plan.planId, plan.revision, "arbitrary-nonempty-token" });
				Assert.That(applied.errors.Any(error => error.code == "APPROVAL_REQUIRED"), Is.True);
				Assert.That(applied.status, Is.EqualTo("blocked"));
				Assert.That(applied.authorityReservationId, Is.Null.Or.Empty);
				Assert.That(RenderSettings.fog, Is.EqualTo(fogBefore));
				Assert.That(RenderSettings.fogDensity, Is.EqualTo(densityBefore));
			}
			finally
			{
				((IDictionary)session.GetField("plans", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(plan.planId);
				((IList)session.GetField("history", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(plan.planId);
			}
		}
	}
}
#endif
