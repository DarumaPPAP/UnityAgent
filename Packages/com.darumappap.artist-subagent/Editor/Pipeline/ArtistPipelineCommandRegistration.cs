#if UNITY_EDITOR && UNITY_ARTIST_PIPELINE

using UnityEngine;
using Unity.Pipeline.Commands;

namespace UnityArtist
{
	public static class ArtistPipelineCommands
	{
		[CliCommand("artist.inspect", "Inspect visual targets, render pipeline support and cinematic objects.")]
		public static string Inspect() => JsonUtility.ToJson(ArtistSession.Inspect());

		[CliCommand("artist.plan", "Create a read-only visual intent plan with an exact diff.")]
		public static string Plan([CliArg("request-json", "Structured visual intent JSON.", Required = false)] string requestJson = "{}", [CliArg("expected-revision", "Expected Editor revision.", Required = false)] string expectedRevision = "") => JsonUtility.ToJson(ArtistSession.Plan(requestJson, expectedRevision));

		[CliCommand("artist.preview", "Return an exact visual plan without mutating the Editor.")]
		public static string Preview([CliArg("plan-id", "Plan id.", Required = true)] string planId, [CliArg("expected-revision", "Expected Editor revision.", Required = false)] string expectedRevision = "") => JsonUtility.ToJson(ArtistSession.Preview(planId, expectedRevision));

		[CliCommand("artist.apply", "Apply an approved visual plan with revision and Undo guards.")]
		public static string Apply([CliArg("plan-id", "Plan id.", Required = true)] string planId, [CliArg("expected-revision", "Expected Editor revision.", Required = true)] string expectedRevision, [CliArg("approval-token", "Opaque UnityAgent approval token.", Required = true)] string approvalToken) => JsonUtility.ToJson(ArtistSession.Apply(planId, expectedRevision, approvalToken));

		[CliCommand("artist.capture", "Capture visual evidence from an exact camera binding.")]
		public static string Capture([CliArg("request-json", "Structured capture request JSON.", Required = false)] string requestJson = "{}") => JsonUtility.ToJson(ArtistSession.Capture(requestJson));

		[CliCommand("artist.evaluate", "Record a human visual review decision for a capture.")]
		public static string Evaluate([CliArg("capture-id", "Capture id.", Required = true)] string captureId, [CliArg("decision", "accepted, rejected, or needs_refine.", Required = true)] string decision, [CliArg("notes", "Human review notes.", Required = false)] string notes = "") => JsonUtility.ToJson(ArtistSession.Evaluate(captureId, decision, notes));

		[CliCommand("artist.refine", "Create a linked refinement plan from a human visual review.")]
		public static string Refine([CliArg("evaluation-id", "Evaluation id.", Required = true)] string evaluationId, [CliArg("request-json", "Structured refinement intent JSON.", Required = true)] string requestJson) => JsonUtility.ToJson(ArtistSession.Refine(evaluationId, requestJson));

		[CliCommand("artist.history", "Read the current session's redacted visual evidence history.")]
		public static string History() => JsonUtility.ToJson(ArtistSession.History());

		[CliCommand("artist.cinematic", "Inspect, plan, preview or apply bounded Timeline, camera-shot and binding workflows.")]
		public static string Cinematic([CliArg("operation", "inspect, plan, preview, or apply.", Required = false)] string operation = "inspect", [CliArg("request-json", "Structured cinematic request JSON.", Required = false)] string requestJson = "{}", [CliArg("plan-id", "Plan id for preview/apply.", Required = false)] string planId = "", [CliArg("expected-revision", "Expected revision.", Required = false)] string expectedRevision = "", [CliArg("approval-token", "Opaque approval token.", Required = false)] string approvalToken = "") => JsonUtility.ToJson(ArtistSession.Cinematic(operation, requestJson, planId, expectedRevision, approvalToken));
	}
}

#endif
