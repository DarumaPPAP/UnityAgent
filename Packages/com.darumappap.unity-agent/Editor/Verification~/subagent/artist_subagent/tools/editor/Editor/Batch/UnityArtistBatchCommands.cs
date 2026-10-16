#if UNITY_EDITOR

using System;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace UnityArtist
{
	[Serializable]
	internal sealed class BatchRequest
	{
		public string command;
		public string requestJson;
		public string planId;
		public string captureId;
		public string evaluationId;
		public string expectedRevision;
		public string approvalToken;
		public string decision;
		public string notes;
		public string operation;
		public string scenePath;
	}

	public static class UnityArtistBatchCommands
	{
		private const string RequestEnvironmentVariable = "UNITY_ARTIST_BATCH_REQUEST";
		private const string ResponseEnvironmentVariable = "UNITY_ARTIST_BATCH_RESPONSE";
		private const string FallbackTransport = "official_unity_cli_bounded_batch_fallback";

		public static void Dispatch()
		{
			string responsePath = Environment.GetEnvironmentVariable(ResponseEnvironmentVariable);
			ArtistResult result = null;
			int exitCode = 2;
			try
			{
				result = Execute(ReadRequest());
				if (result != null && string.Equals(result.status, "passed", StringComparison.OrdinalIgnoreCase)) exitCode = 0;
			}
			catch (Exception exception)
			{
				result = Failure("batch", "BATCH_BRIDGE_FAILURE", exception.Message);
			}

			try
			{
				if (string.IsNullOrWhiteSpace(responsePath)) throw new InvalidOperationException("The batch response path was not supplied.");
				string directory = Path.GetDirectoryName(responsePath);
				if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);
				File.WriteAllText(responsePath, JsonUtility.ToJson(result, true));
			}
			catch (Exception exception)
			{
				Debug.LogError("UnityArtistCLI batch response could not be written: " + exception.Message);
				exitCode = 2;
			}
			EditorApplication.Exit(exitCode);
		}

		private static BatchRequest ReadRequest()
		{
			string encoded = Environment.GetEnvironmentVariable(RequestEnvironmentVariable);
			if (string.IsNullOrWhiteSpace(encoded)) throw new InvalidOperationException("The batch request was not supplied.");
			string json = Encoding.UTF8.GetString(Convert.FromBase64String(encoded));
			BatchRequest request = JsonUtility.FromJson<BatchRequest>(json);
			if (request == null || string.IsNullOrWhiteSpace(request.command)) throw new InvalidOperationException("The batch request command is missing.");
			return request;
		}

		private static ArtistResult Execute(BatchRequest request)
		{
			if (!Application.unityVersion.StartsWith("2022.3.", StringComparison.OrdinalIgnoreCase))
				return Failure(request.command, "BATCH_FALLBACK_VERSION_NOT_ALLOWED", "The bounded batch fallback is restricted to Unity 2022.3 LTS.");
			if (GraphicsSettings.currentRenderPipeline != null)
				return Failure(request.command, "BATCH_FALLBACK_PIPELINE_NOT_ALLOWED", "The bounded batch fallback is restricted to the Built-in Render Pipeline.");
			string sceneError;
			if (!LoadTargetScene(request.scenePath, out sceneError))
				return Failure(request.command, "BATCH_FALLBACK_SCENE_REQUIRED", sceneError);

			ArtistSession.ConfigureBatchSession(FallbackTransport);
			switch ((request.command ?? string.Empty).Trim().ToLowerInvariant())
			{
				case "inspect": return ArtistSession.Inspect();
				case "plan": return ArtistSession.Plan(request.requestJson, request.expectedRevision);
				case "preview": return ArtistSession.Preview(request.planId, request.expectedRevision);
				case "apply": return ArtistSession.Apply(request.planId, request.expectedRevision, request.approvalToken);
				case "capture": return ArtistSession.Capture(request.requestJson);
				case "evaluate": return ArtistSession.Evaluate(request.captureId, request.decision, request.notes);
				case "refine": return ArtistSession.Refine(request.evaluationId, request.requestJson);
				case "history": return ArtistSession.History();
				case "cinematic": return ArtistSession.Cinematic(request.operation, request.requestJson, request.planId, request.expectedRevision, request.approvalToken);
				default: return Failure(request.command, "BATCH_COMMAND_NOT_ALLOWLISTED", "The requested Artist command is not allowlisted for the bounded batch fallback.");
			}
		}

		private static bool LoadTargetScene(string requestedPath, out string error)
		{
			error = string.Empty;
			string scenePath = (requestedPath ?? string.Empty).Trim();
			if (string.IsNullOrWhiteSpace(scenePath))
			{
				EditorBuildSettingsScene[] configured = EditorBuildSettings.scenes;
				if (configured == null || configured.Length == 0)
				{
					error = "The bounded batch fallback requires an explicit --scene-path or one enabled EditorBuildSettings scene.";
					return false;
				}
				var enabled = new System.Collections.Generic.List<EditorBuildSettingsScene>();
				foreach (EditorBuildSettingsScene scene in configured)
					if (scene != null && scene.enabled && !string.IsNullOrWhiteSpace(scene.path)) enabled.Add(scene);
				if (enabled.Count != 1)
				{
					error = "The bounded batch fallback requires exactly one enabled EditorBuildSettings scene when --scene-path is omitted.";
					return false;
				}
				scenePath = enabled[0].path;
			}
			if (!scenePath.StartsWith("Assets/", StringComparison.Ordinal) || !scenePath.EndsWith(".unity", StringComparison.OrdinalIgnoreCase))
			{
				error = "The bounded batch fallback only accepts an exact project-relative Assets/*.unity scene path.";
				return false;
			}
			Scene loadedScene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
			if (!loadedScene.IsValid() || !loadedScene.isLoaded)
			{
				error = "The exact fallback scene could not be loaded: " + scenePath;
				return false;
			}
			return true;
		}

		private static ArtistResult Failure(string command, string code, string message)
		{
			ArtistResult result = new ArtistResult
			{
				command = "artist." + (string.IsNullOrWhiteSpace(command) ? "batch" : command),
				status = "blocked",
				verified = false,
				savePerformed = false,
				undoAvailable = false,
				support = new ArtistSupport
				{
					supported = false,
					supportTier = "unsupported",
					unityVersion = Application.unityVersion,
					renderPipeline = "builtin",
					compatibilityBackend = "builtin_editor_api",
					transport = FallbackTransport,
					errorCode = code,
					reason = message
				}
			};
			result.errors.Add(new ArtistError { code = code, message = message });
			return result;
		}
	}
}

#endif
