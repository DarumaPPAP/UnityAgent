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
	public sealed class ContextReceiptTests
	{
		[Serializable]
		private sealed class ContextInput
		{
			public string contextId;
			public string contextFingerprint;
			public string projectRoot;
			public string runId;
		}

		[Serializable]
		private sealed class Receipt
		{
			public string receivedContextId;
			public string receivedContextFingerprint;
			public string projectRoot;
			public string runId;
		}

		[Serializable]
		private sealed class ProtocolSupport
		{
			public string approvalProtocol;
			public string contextProtocol;
		}

		[Serializable]
		private sealed class Response
		{
			public Receipt contextReceipt;
			public ArtistError[] errors;
			public bool humanReview;
			public ProtocolSupport support;
		}

		[Test]
		public void InspectionIdentifiesTheImplementedAuthorityAndContextProtocols()
		{
			Response result = JsonUtility.FromJson<Response>(Invoke("Inspect", ContextJson("context-protocol", "fingerprint-protocol", "run-protocol")));
			Assert.That(result.support.approvalProtocol, Is.EqualTo("control_plane_authority_v1"));
			Assert.That(result.support.contextProtocol, Is.EqualTo("artist_context_v1"));
		}
		[TestCase("empty")]
		[TestCase("number")]
		[TestCase("unknown")]
		[TestCase("duplicate")]
		[TestCase("project")]
		[TestCase("malformed")]
		public void EveryCommandRejectsInvalidContextBeforeExecution(string kind)
		{
			string context = ContextJson("context-a", "fingerprint-a", "run-a");
			if (kind == "empty")
			{
				context = context.Replace("\"context-a\"", "\"\"");
			}
			if (kind == "number")
			{
				context = context.Replace("\"context-a\"", "42");
			}
			if (kind == "unknown")
			{
				context = context.Substring(0, context.Length - 1) + ",\"extra\":\"value\"}";
			}
			if (kind == "duplicate")
			{
				context = context.Substring(0, context.Length - 1) + ",\"contextId\":\"context-other\"}";
			}
			if (kind == "project")
			{
				context = JsonUtility.ToJson(new ContextInput { contextId = "context-a", contextFingerprint = "fingerprint-a", projectRoot = ProjectRoot() + "-other", runId = "run-a" });
			}
			if (kind == "malformed")
			{
				context = "{";
			}
			foreach (string command in new[] { "Inspect", "Plan", "Preview", "Apply", "Capture", "Evaluate", "Refine", "History", "Cinematic" })
			{
				Response result = JsonUtility.FromJson<Response>(Invoke(command, context));
				Assert.That(result.errors.Any(error => error.code == "CONTEXT_INVALID"), Is.True, command + " は Context 検証より先に実行されてはいけません。");
				AssertNoReceivedContext(result.contextReceipt);
			}
		}

		[Test]
		public void ContextReceiptMatchesEachRunAndIsNotReusedByLegacyCall()
		{
			Response first = JsonUtility.FromJson<Response>(Invoke("Inspect", ContextJson("context-a", "fingerprint-a", "run-a")));
			Response second = JsonUtility.FromJson<Response>(Invoke("Inspect", ContextJson("context-b", "fingerprint-b", "run-b")));
			Response legacy = JsonUtility.FromJson<Response>(Invoke("Inspect", ""));
			Assert.That(first.contextReceipt.receivedContextId, Is.EqualTo("context-a"));
			Assert.That(first.contextReceipt.receivedContextFingerprint, Is.EqualTo("fingerprint-a"));
			Assert.That(first.contextReceipt.projectRoot, Is.EqualTo(ProjectRoot()));
			Assert.That(first.contextReceipt.runId, Is.EqualTo("run-a"));
			Assert.That(second.contextReceipt.receivedContextId, Is.EqualTo("context-b"));
			Assert.That(second.contextReceipt.receivedContextFingerprint, Is.EqualTo("fingerprint-b"));
			Assert.That(second.contextReceipt.runId, Is.EqualTo("run-b"));
			AssertNoReceivedContext(legacy.contextReceipt);
		}

		[Test]
		public void NonemptyFakeApprovalCannotCreateHumanAcceptance()
		{
			string descriptor = Path.Combine(ProjectRoot(), "Library", "UnityAgent", "ArtistAuthority.json");
			if (File.Exists(descriptor))
			{
				Assert.Ignore("他の呼出しが所有する承認セッションを変更しないため実行しません。");
			}
			Type session = typeof(ArtistResult).Assembly.GetType("UnityArtist.ArtistSession", true);
			IDictionary captures = (IDictionary)session.GetField("captures", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);
			string captureId = "artist-capture-auth-test-" + Guid.NewGuid().ToString("N");
			// 描画品質とは独立した認証境界なので、このテストが所有する最小 Capture 記録だけを使う。
			captures.Add(captureId, new ArtistResult { captureId = captureId, command = "artist.capture", status = "passed", verified = true });
			try
			{
				Response result = JsonUtility.FromJson<Response>(Invoke("Evaluate", ContextJson("context-review", "fingerprint-review", "run-review"), captureId));
				Assert.That(result.errors.Any(error => error.code == "APPROVAL_REQUIRED" || error.code == "APPROVAL_INVALID"), Is.True);
				Assert.That(result.humanReview, Is.False);
			}
			finally
			{
				captures.Remove(captureId);
			}
		}

		[Test]
		public void LegacyEvaluationCannotAuthorizeProductionRefinement()
		{
			Type session = typeof(ArtistResult).Assembly.GetType("UnityArtist.ArtistSession", true);
			if ((bool)session.GetField("persistentBatchSession", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null))
			{
				Assert.Ignore("低レベル互換呼出しを永続 Batch 状態へ保存しないため実行しません。");
			}
			IDictionary captures = (IDictionary)session.GetField("captures", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);
			string captureId = "artist-capture-legacy-test-" + Guid.NewGuid().ToString("N");
			captures.Add(captureId, new ArtistResult { captureId = captureId, command = "artist.capture", status = "passed", verified = true });
			ArtistResult legacy = null;
			try
			{
				legacy = (ArtistResult)session.GetMethod("Evaluate", BindingFlags.Public | BindingFlags.Static).Invoke(null, new object[] { captureId, "needs_refine", "" });
				Assert.That(legacy.errors, Is.Empty, "低レベル Evaluate の既存互換動作を前提として分離します。");
				Response refined = JsonUtility.FromJson<Response>(Invoke("Refine", ContextJson("context-refine", "fingerprint-refine", "run-refine"), captureId, legacy.evaluationId));
				Assert.That(refined.errors.Any(error => error.code == "EVALUATION_AUTHORITY_REQUIRED"), Is.True);
			}
			finally
			{
				captures.Remove(captureId);
				if (legacy != null)
				{
					((IList)session.GetField("history", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Remove(legacy.evaluationId);
				}
			}
		}
		private void AssertNoReceivedContext(Receipt receipt)
		{
			// Unity の JSON 表現では null class も空 field object になるため、受領値の不在を検証する。
			Assert.That(receipt == null || string.IsNullOrEmpty(receipt.receivedContextId) && string.IsNullOrEmpty(receipt.receivedContextFingerprint) && string.IsNullOrEmpty(receipt.projectRoot) && string.IsNullOrEmpty(receipt.runId), Is.True, "未受信の Context を別の呼出しから補完しません。");
		}
		private string Invoke(string command, string contextJson, string captureId = "missing-capture", string evaluationId = "missing-evaluation")
		{
			Type registration = Assembly.Load("DarumaPPAP.UnityArtist.Pipeline.Editor").GetType("UnityArtist.ArtistPipelineCommands", true);
			MethodInfo method = registration.GetMethod(command, BindingFlags.Public | BindingFlags.Static);
			ParameterInfo[] parameters = method.GetParameters();
			Assert.That(parameters.Any(parameter => parameter.Name == "contextJson"), Is.True, command + " に Context の受信引数が必要です。");
			object[] arguments = parameters.Select(parameter => parameter.Name == "contextJson" ? (object)contextJson : parameter.Name == "captureId" ? captureId : parameter.Name == "evaluationId" ? evaluationId : parameter.Name == "decision" ? "accepted" : parameter.Name == "approvalToken" ? new string('0', 64) : parameter.HasDefaultValue ? parameter.DefaultValue : (object)"missing").ToArray();
			return (string)method.Invoke(null, arguments);
		}

		private string ContextJson(string contextId, string fingerprint, string runId) => JsonUtility.ToJson(new ContextInput { contextId = contextId, contextFingerprint = fingerprint, projectRoot = ProjectRoot(), runId = runId });
		private string ProjectRoot() => Directory.GetParent(Application.dataPath).FullName;
	}
}
#endif
