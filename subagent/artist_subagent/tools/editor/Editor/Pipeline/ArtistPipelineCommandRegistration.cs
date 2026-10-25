#if UNITY_EDITOR && UNITY_ARTIST_PIPELINE

using System;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEngine;
using Unity.Pipeline.Commands;

namespace UnityArtist
{
	public static class ArtistPipelineCommands
	{
		[Serializable]
		private sealed class ContextRequest
		{
			public string contextId;
			public string contextFingerprint;
			public string projectRoot;
			public string runId;
		}

		[CliCommand("artist.inspect", "Inspect visual targets, render pipeline support and cinematic objects.")]
		public static string Inspect([CliArg("context-json", "Current-call Context binding.", Required = false)] string contextJson = "") => Execute("artist.inspect", contextJson, _ => ArtistSession.Inspect());

		[CliCommand("artist.plan", "Create a read-only visual intent plan with an exact diff.")]
		public static string Plan([CliArg("request-json", "Structured visual intent JSON.", Required = false)] string requestJson = "{}", [CliArg("expected-revision", "Expected Editor revision.", Required = false)] string expectedRevision = "", [CliArg("context-json", "Current-call Context binding.", Required = false)] string contextJson = "") => Execute("artist.plan", contextJson, _ => ArtistSession.Plan(requestJson, expectedRevision));

		[CliCommand("artist.preview", "Return an exact visual plan without mutating the Editor.")]
		public static string Preview([CliArg("plan-id", "Plan id.", Required = true)] string planId, [CliArg("expected-revision", "Expected Editor revision.", Required = false)] string expectedRevision = "", [CliArg("context-json", "Current-call Context binding.", Required = false)] string contextJson = "") => Execute("artist.preview", contextJson, _ => ArtistSession.Preview(planId, expectedRevision));

		[CliCommand("artist.apply", "Apply an approved visual plan with revision and Undo guards.")]
		public static string Apply([CliArg("plan-id", "Plan id.", Required = true)] string planId, [CliArg("expected-revision", "Expected Editor revision.", Required = true)] string expectedRevision, [CliArg("approval-token", "Opaque UnityAgent approval token.", Required = true)] string approvalToken, [CliArg("context-json", "Current-call Context binding.", Required = false)] string contextJson = "") => Execute("artist.apply", contextJson, _ => ArtistSession.Apply(planId, expectedRevision, approvalToken));

		[CliCommand("artist.capture", "Capture visual evidence from an exact camera binding.")]
		public static string Capture([CliArg("request-json", "Structured capture request JSON.", Required = false)] string requestJson = "{}", [CliArg("context-json", "Current-call Context binding.", Required = false)] string contextJson = "") => Execute("artist.capture", contextJson, _ => ArtistSession.Capture(requestJson));

		[CliCommand("artist.evaluate", "Record an authenticated human visual review decision for a capture.")]
		public static string Evaluate([CliArg("capture-id", "Capture id.", Required = true)] string captureId, [CliArg("decision", "accepted, rejected, or needs_refine.", Required = true)] string decision, [CliArg("notes", "Human review notes.", Required = false)] string notes = "", [CliArg("approval-token", "Opaque human review approval token.", Required = false)] string approvalToken = "", [CliArg("context-json", "Current-call Context binding.", Required = false)] string contextJson = "") => Execute("artist.evaluate", contextJson, context => ArtistSession.EvaluateAuthenticated(captureId, decision, notes, approvalToken, context));

		[CliCommand("artist.refine", "Create a linked refinement plan from an authenticated human visual review.")]
		public static string Refine([CliArg("evaluation-id", "Evaluation id.", Required = true)] string evaluationId, [CliArg("request-json", "Structured refinement intent JSON.", Required = true)] string requestJson, [CliArg("context-json", "Current-call Context binding.", Required = false)] string contextJson = "") => Execute("artist.refine", contextJson, context => context == null ? ArtistSession.Refine(evaluationId, requestJson) : ArtistSession.RefineAuthenticated(evaluationId, requestJson, context));

		[CliCommand("artist.history", "Read the current session's redacted visual evidence history.")]
		public static string History([CliArg("context-json", "Current-call Context binding.", Required = false)] string contextJson = "") => Execute("artist.history", contextJson, _ => ArtistSession.History());

		[CliCommand("artist.cinematic", "Inspect, plan, preview or apply bounded Timeline, camera-shot and binding workflows.")]
		public static string Cinematic([CliArg("operation", "inspect, plan, preview, or apply.", Required = false)] string operation = "inspect", [CliArg("request-json", "Structured cinematic request JSON.", Required = false)] string requestJson = "{}", [CliArg("plan-id", "Plan id for preview/apply.", Required = false)] string planId = "", [CliArg("expected-revision", "Expected revision.", Required = false)] string expectedRevision = "", [CliArg("approval-token", "Opaque approval token.", Required = false)] string approvalToken = "", [CliArg("context-json", "Current-call Context binding.", Required = false)] string contextJson = "") => Execute("artist.cinematic", contextJson, _ => ArtistSession.Cinematic(operation, requestJson, planId, expectedRevision, approvalToken));

		private static string Execute(string command, string contextJson, Func<ContextReceipt, ArtistResult> operation)
		{
			ContextReceipt receipt;
			try
			{
				receipt = ReadContext(contextJson);
			}
			catch (Exception exception) when (exception is ArgumentException || exception is IOException || exception is NotSupportedException || exception is RegexMatchTimeoutException)
			{
				// Capture や人間レビューの記録を開始する前に、不正な Context を拒否する。
				ArtistResult invalid = new ArtistResult { command = command, status = "blocked" };
				invalid.errors.Add(new ArtistError { code = "CONTEXT_INVALID", message = "Context は現在の Project に束縛された4つの非空文字列で指定してください。" });
				return JsonUtility.ToJson(invalid);
			}
			ContextReceipt priorContext = ArtistSession.CurrentContext;
			ArtistResult result;
			try
			{
				ArtistSession.CurrentContext = receipt;
				result = operation(receipt);
			}
			finally
			{
				ArtistSession.CurrentContext = priorContext;
			}
			ContextReceipt previous = result.contextReceipt;
			try
			{
				// StoredPlan.preview 等の共有結果には、別 run の受領 Context を残さない。
				result.contextReceipt = receipt;
				return JsonUtility.ToJson(result);
			}
			finally
			{
				result.contextReceipt = previous;
			}
		}

		private static ContextReceipt ReadContext(string contextJson)
		{
			if (string.IsNullOrEmpty(contextJson))
			{
				// 既存の手動 CLI 呼出しは維持するが、未受信の Context は補完しない。
				return null;
			}
			if (contextJson.Length > 16384)
			{
				throw new ArgumentException("Context exceeds the bounded request size.");
			}
			// JsonUtility の型変換へ依存せず、この flat object の各値が JSON string であることを先に確定する。
			const string quotedString = @"""(?:[^""\\\x00-\x1f]|\\(?:[""\\/bfnrt]|u[0-9a-fA-F]{4}))*""";
			const string spacing = @"[ \t\r\n]*";
			string member = @"""(?<key>contextId|contextFingerprint|projectRoot|runId)""" + spacing + ":" + spacing + quotedString;
			Match shape = Regex.Match(contextJson, @"\A" + spacing + @"\{" + spacing + member + "(?:" + spacing + "," + spacing + member + ")*" + spacing + @"\}" + spacing + @"\z", RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(100));
			if (!shape.Success || shape.Groups["key"].Captures.Count != 4 || shape.Groups["key"].Captures.Cast<System.Text.RegularExpressions.Capture>().Select(value => value.Value).Distinct(StringComparer.Ordinal).Count() != 4)
			{
				throw new ArgumentException("Context must contain exactly four distinct string fields.");
			}
			ContextRequest request = JsonUtility.FromJson<ContextRequest>(contextJson);
			if (request == null || string.IsNullOrWhiteSpace(request.contextId) || string.IsNullOrWhiteSpace(request.contextFingerprint) || string.IsNullOrWhiteSpace(request.projectRoot) || string.IsNullOrWhiteSpace(request.runId))
			{
				throw new ArgumentException("Context fields cannot be empty.");
			}
			string projectRoot = Directory.GetParent(Application.dataPath).FullName;
			if (!Path.IsPathRooted(request.projectRoot) || !string.Equals(Path.GetFullPath(request.projectRoot).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar), Path.GetFullPath(projectRoot).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar), Application.platform == RuntimePlatform.WindowsEditor ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
			{
				throw new ArgumentException("Context belongs to another Project.");
			}
			return new ContextReceipt { receivedContextId = request.contextId, receivedContextFingerprint = request.contextFingerprint, projectRoot = request.projectRoot, runId = request.runId };
		}
	}
}

#endif
