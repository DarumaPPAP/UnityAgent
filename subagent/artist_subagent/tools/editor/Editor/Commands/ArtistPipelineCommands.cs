#if UNITY_EDITOR

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace UnityArtist
{
	[Serializable]
	public sealed class ArtistIntent
	{
		public string workflow;
		public string targetName;
		public bool setFog;
		public float fogDensity;
		public bool setVolumeLookDev;
		public float volumePostExposure;
		public float volumeContrast;
		public bool setLightIntensity;
		public float lightIntensity;
		public bool setCameraFieldOfView;
		public float cameraFieldOfView;
		public string targetGuid;
		public float cameraFovMinimum;
		public float cameraFovMaximum;
		public string captureCameraName;
		public string timelineAssetName;
		public string[] requestedChannels;
	}

	[Serializable]
	public sealed class CinematicRequest
	{
		public string directorName;
		public string trackKind;
		public string trackName;
		public string bindingTargetName;
		public float markerTime;
		public float clipStart;
		public float clipDuration;
	}

	[Serializable]
	public sealed class ArtistError
	{
		public string code;
		public string message;
	}

	[Serializable]
	public sealed class ArtistChange
	{
		public string target;
		public string property;
		public string before;
		public string after;
	}

	[Serializable]
	public sealed class ArtistTarget
	{
		public string kind;
		public string name;
		public string scenePath;
		public string hierarchyPath;
		public string globalObjectId;
		public float fieldOfView;
		public bool enabled;
	}

	[Serializable]
	public sealed class ArtistSupport
	{
		public bool supported;
		public string supportTier;
		public string unityVersion;
		public string renderPipeline;
		public string compatibilityBackend;
		public string transport;
		public string errorCode;
		public string reason;
	}

	[Serializable]
	public sealed class ArtistResult
	{
		public string schemaVersion = "2.0";
		public string product = "UnityArtistCLI";
		public string command;
		public string status;
		public bool verified;
		public string planId;
		public string captureId;
		public string evaluationId;
		public string revision;
		public string baseRevision;
		public bool approvalRequired;
		public bool savePerformed;
		public bool undoAvailable;
		public bool humanReview;
		public ArtistSupport support;
		public List<ArtistChange> exactDiff = new List<ArtistChange>();
		public List<ArtistTarget> targets = new List<ArtistTarget>();
		public List<string> evidence = new List<string>();
		public List<ArtistError> errors = new List<ArtistError>();
	}

	[Serializable]
	internal sealed class StoredPlan
	{
		public string planId;
		public string baseRevision;
		public ArtistIntent intent;
		public CinematicRequest cinematic;
		public ArtistResult preview;
	}

	[Serializable]
	internal sealed class StoredCapture
	{
		public string captureId;
		public ArtistResult result;
	}

	[Serializable]
	internal sealed class PersistentState
	{
		public List<StoredPlan> plans = new List<StoredPlan>();
		public List<StoredCapture> captures = new List<StoredCapture>();
		public List<string> history = new List<string>();
	}

	internal static class ArtistSession
	{
		private static readonly Dictionary<string, StoredPlan> plans = new Dictionary<string, StoredPlan>();
		private static readonly Dictionary<string, ArtistResult> captures = new Dictionary<string, ArtistResult>();
		private static readonly List<string> history = new List<string>();
		private static bool persistentBatchSession;
		private static bool persistentStateLoaded;
		private static string transportOverride;
		private static int captureWidthOverride;
		private static int captureHeightOverride;

		public static void ConfigureBatchSession(string transport)
		{
			persistentBatchSession = true;
			persistentStateLoaded = false;
			transportOverride = transport;
			captureWidthOverride = 1920;
			captureHeightOverride = 1080;
			EnsurePersistentStateLoaded();
		}

		public static ArtistResult Inspect()
		{
			EnsurePersistentStateLoaded();
			ArtistSupport support = Support();
			ArtistResult result = Base("artist.inspect", support);
			if (!support.supported) return Error(result, support.errorCode, support.reason);
			result.verified = support.supported;
			foreach (Camera camera in SceneObjects<Camera>())
			{
				result.targets.Add(Target("camera", camera, camera.enabled));
			}
			foreach (Light light in SceneObjects<Light>())
			{
				result.targets.Add(Target("light", light, light.enabled));
			}
			foreach (ReflectionProbe probe in SceneObjects<ReflectionProbe>())
			{
				result.targets.Add(Target("reflection_probe", probe, probe.enabled));
			}
			if (support.renderPipeline == "urp")
			{
				if (TryFindUrpVolume(out Component volume, out object profile, out string reason))
				{
					bool enabled = volume is Behaviour behaviour && behaviour.enabled;
					result.targets.Add(Target("volume", volume, enabled));
					result.evidence.Add("urp_volume_inspection");
					if (FindVolumeComponent(profile, FindType("UnityEngine.Rendering.Universal.ColorAdjustments", "Unity.RenderPipelines.Universal.Runtime")) != null)
						result.evidence.Add("urp_color_adjustments");
				}
				else
				{
					result.evidence.Add("urp_volume_missing:" + reason);
				}
			}
			foreach (PlayableDirector director in SceneObjects<PlayableDirector>())
			{
				result.targets.Add(Target("playable_director", director, director.enabled));
			}
			if (support.renderPipeline == "hdrp")
			{
				if (TryFindHdrpFog(false, out Component volume, out object fog, out string reason))
				{
					bool enabled = volume is Behaviour behaviour && behaviour.enabled;
					result.targets.Add(Target("volume", volume, enabled));
					result.evidence.Add("hdrp_volume_inspection");
					result.evidence.Add("hdrp_fog_override");
				}
				else
				{
					result.evidence.Add("hdrp_volume_missing:" + reason);
				}
			}
			result.evidence.Add("visual_art_inspection");
			result.evidence.Add("pipeline_support_fact");
			return result;
		}

		public static ArtistResult Plan(string requestJson, string expectedRevision)
		{
			EnsurePersistentStateLoaded();
			ArtistSupport support = Support();
			ArtistResult result = Base("artist.plan", support);
			if (!support.supported)
			{
				return Error(result, support.errorCode, support.reason);
			}
			ArtistIntent intent;
			try
			{
				intent = JsonUtility.FromJson<ArtistIntent>(string.IsNullOrWhiteSpace(requestJson) ? "{}" : requestJson);
			}
			catch (Exception exception)
			{
				return Error(result, "INVALID_INTENT", exception.Message);
			}
			if (intent == null || !HasChange(intent))
			{
				return Error(result, "INVALID_INTENT", "At least one explicit visual intent change is required.");
			}
			string currentRevision = CurrentRevision();
			if (!string.IsNullOrWhiteSpace(expectedRevision) && !string.Equals(expectedRevision, currentRevision, StringComparison.Ordinal))
			{
				return Error(result, "STALE_REVISION", "The requested revision does not match the current Editor state.");
			}

			string planId = "artist-plan-" + Guid.NewGuid().ToString("N");
			result.planId = planId;
			result.revision = currentRevision;
			result.baseRevision = currentRevision;
			result.approvalRequired = true;
			result.savePerformed = false;
			result.undoAvailable = true;
			if (!BuildDiff(result, intent)) return result;
			result.evidence.Add("visual_direction_plan");
			result.evidence.Add("exact_diff");
			result.evidence.Add("expected_revision");
			plans[planId] = new StoredPlan { planId = planId, baseRevision = currentRevision, intent = intent, preview = result };
			history.Add(planId);
			PersistState();
			return result;
		}

		public static ArtistResult Preview(string planId, string expectedRevision)
		{
			EnsurePersistentStateLoaded();
			if (!plans.TryGetValue(planId ?? string.Empty, out StoredPlan plan))
			{
				return Error(Base("artist.preview", Support()), "PLAN_NOT_FOUND", "The plan is not present in this Editor session.");
			}
			if (!string.IsNullOrWhiteSpace(expectedRevision) && !string.Equals(expectedRevision, plan.baseRevision, StringComparison.Ordinal))
			{
				return Error(Base("artist.preview", Support()), "STALE_REVISION", "The plan revision is stale.");
			}
			plan.preview.command = "artist.preview";
			return plan.preview;
		}

		public static ArtistResult Apply(string planId, string expectedRevision, string approvalToken)
		{
			EnsurePersistentStateLoaded();
			ArtistResult result = Base("artist.apply", Support());
			if (string.IsNullOrWhiteSpace(approvalToken)) return Error(result, "APPROVAL_REQUIRED", "Apply requires an opaque approval token from UnityAgent.");
			if (!plans.TryGetValue(planId ?? string.Empty, out StoredPlan plan)) return Error(result, "PLAN_NOT_FOUND", "The plan is not present in this Editor session.");
			string currentRevision = CurrentRevision();
			if (!string.Equals(plan.baseRevision, currentRevision, StringComparison.Ordinal) || !string.Equals(expectedRevision, currentRevision, StringComparison.Ordinal))
			{
				return Error(result, "STALE_REVISION", "The Editor state changed after the plan was prepared.");
			}
			ArtistSupport support = Support();
			if (!support.supported) return Error(result, support.errorCode, support.reason);
			if (!ApplyIntent(plan.intent, result)) return result;
			result.status = "passed";
			result.verified = true;
			result.planId = planId;
			result.baseRevision = currentRevision;
			result.revision = CurrentRevision();
			result.approvalRequired = true;
			result.savePerformed = false;
			result.undoAvailable = true;
			result.evidence.Add("mutation_evidence");
			result.evidence.Add("undo_registration");
			result.evidence.Add("save_not_performed");
			plans.Remove(planId);
			history.Add("applied:" + planId);
			PersistState();
			return result;
		}

		public static ArtistResult Capture(string requestJson)
		{
			EnsurePersistentStateLoaded();
			ArtistResult result = Base("artist.capture", Support());
			if (!result.support.supported) return Error(result, result.support.errorCode, result.support.reason);
			ArtistIntent intent;
			try
			{
				intent = string.IsNullOrWhiteSpace(requestJson) ? new ArtistIntent() : JsonUtility.FromJson<ArtistIntent>(requestJson);
			}
			catch (Exception exception)
			{
				return Error(result, "INVALID_CAPTURE_REQUEST", exception.Message);
			}
			Camera camera = FindCamera(intent == null ? null : intent.captureCameraName);
			if (camera == null) return Error(result, "CAMERA_NOT_FOUND", "Capture requires an exact camera target or a Main Camera.");
			string captureId = "artist-capture-" + Guid.NewGuid().ToString("N");
			string projectRoot = Directory.GetParent(Application.dataPath).FullName;
			string directory = Path.Combine(projectRoot, "Library", "UnityArtist", "Captures", captureId);
			Directory.CreateDirectory(directory);
			string colorPath = Path.Combine(directory, "color.png").Replace('\\', '/');
			string captureError;
			if (!CaptureCameraFrame(camera, colorPath, out captureError))
			{
				return Error(result, "CAPTURE_FAILED", captureError);
			}
			result.captureId = captureId;
			result.verified = true;
			result.status = "passed";
			result.savePerformed = false;
			result.evidence.Add("visual_capture");
			result.evidence.Add("camera_binding:" + camera.name);
			result.evidence.Add("capture_manifest");
			result.evidence.Add("color_path:" + colorPath);
			result.evidence.Add("depth_channel:not_configured");
			result.evidence.Add("object_id_channel:not_configured");
			captures[captureId] = result;
			history.Add(captureId);
			PersistState();
			return result;
		}

		private static bool CaptureCameraFrame(Camera camera, string path, out string error)
		{
			error = string.Empty;
			int width = Mathf.Max(1, captureWidthOverride > 0 ? captureWidthOverride : camera.pixelWidth);
			int height = Mathf.Max(1, captureHeightOverride > 0 ? captureHeightOverride : camera.pixelHeight);
			RenderTexture previousTarget = camera.targetTexture;
			RenderTexture previousActive = RenderTexture.active;
			RenderTexture capture = null;
			Texture2D texture = null;
			try
			{
				// Match the Official Unity Pipeline screenshot primitive. In SRP projects,
				// the default RenderTexture descriptor is pipeline-compatible; explicitly
				// forcing ARGB32/sRGB (or relying on a pooled descriptor) can produce a
				// valid but all-black frame after a fog/post-processing mutation.
				capture = new RenderTexture(width, height, 24);
				capture.Create();
				camera.targetTexture = capture;
				camera.Render();
				RenderTexture.active = capture;
				texture = new Texture2D(width, height, TextureFormat.RGB24, false, false);
				texture.ReadPixels(new Rect(0, 0, width, height), 0, 0, false);
				texture.Apply(false, false);
				File.WriteAllBytes(path, texture.EncodeToPNG());
				return File.Exists(path) && new FileInfo(path).Length > 0;
			}
			catch (Exception exception)
			{
				error = exception.Message;
				return false;
			}
			finally
			{
				camera.targetTexture = previousTarget;
				RenderTexture.active = previousActive;
				if (texture != null) UnityEngine.Object.DestroyImmediate(texture);
				if (capture != null)
				{
					capture.Release();
					UnityEngine.Object.DestroyImmediate(capture);
				}
			}
		}

		public static ArtistResult Evaluate(string captureId, string decision, string notes)
		{
			EnsurePersistentStateLoaded();
			if (!captures.ContainsKey(captureId ?? string.Empty)) return Error(Base("artist.evaluate", Support()), "CAPTURE_NOT_FOUND", "Capture Evidence was not found in this Editor session.");
			string normalized = (decision ?? string.Empty).Trim().ToLowerInvariant();
			if (normalized != "accepted" && normalized != "rejected" && normalized != "needs_refine") return Error(Base("artist.evaluate", Support()), "INVALID_REVIEW_DECISION", "decision must be accepted, rejected, or needs_refine.");
			ArtistResult result = Base("artist.evaluate", Support());
			result.captureId = captureId;
			result.evaluationId = "artist-evaluation-" + Guid.NewGuid().ToString("N");
			result.humanReview = true;
			result.verified = normalized == "accepted";
			result.status = "passed";
			result.evidence.Add("artist_validation");
			result.evidence.Add("human_review_decision");
			result.evidence.Add("review_decision:" + normalized);
			if (!string.IsNullOrWhiteSpace(notes)) result.evidence.Add("review_notes_present");
			history.Add(result.evaluationId);
			PersistState();
			return result;
		}

		public static ArtistResult Refine(string evaluationId, string requestJson)
		{
			EnsurePersistentStateLoaded();
			if (string.IsNullOrWhiteSpace(evaluationId)) return Error(Base("artist.refine", Support()), "EVALUATION_REQUIRED", "refine requires an evaluation id.");
			ArtistResult result = Plan(requestJson, string.Empty);
			result.command = "artist.refine";
			result.evaluationId = evaluationId;
			result.evidence.Add("refinement_plan");
			result.evidence.Add("evaluation_reference");
			PersistState();
			return result;
		}

		public static ArtistResult Cinematic(string operation, string requestJson, string planId, string expectedRevision, string approvalToken)
		{
			EnsurePersistentStateLoaded();
			ArtistResult result = Base("artist.cinematic", Support());
			if (!result.support.supported) return Error(result, result.support.errorCode, result.support.reason);
			string normalized = (operation ?? "inspect").Trim().ToLowerInvariant();
			if (normalized != "inspect" && normalized != "plan" && normalized != "preview" && normalized != "apply")
				return Error(result, "INVALID_CINEMATIC_OPERATION", "operation must be inspect, plan, preview, or apply.");

			CinematicRequest request;
			try
			{
				request = JsonUtility.FromJson<CinematicRequest>(string.IsNullOrWhiteSpace(requestJson) ? "{}" : requestJson);
			}
			catch (Exception exception)
			{
				return Error(result, "INVALID_CINEMATIC_REQUEST", exception.Message);
			}
			if (request == null) return Error(result, "INVALID_CINEMATIC_REQUEST", "The cinematic request must be a JSON object.");

			if (normalized == "inspect")
			{
				foreach (PlayableDirector director in SceneObjects<PlayableDirector>())
				{
					if (string.IsNullOrWhiteSpace(request.directorName) || string.Equals(director.name, request.directorName, StringComparison.Ordinal))
						InspectCinematicDirector(director, result);
				}
				result.evidence.Add("cinematic_operation:inspect");
				result.evidence.Add("timeline_evidence");
				return result;
			}

			if (normalized == "plan")
			{
				PlayableDirector director = FindDirector(request.directorName);
				if (director == null) return Error(result, "TIMELINE_DIRECTOR_NOT_FOUND", "An exact PlayableDirector target is required.");
				if (!ValidateCinematicRequest(request, result)) return result;
				string currentRevision = CurrentRevision();
				string newPlanId = "artist-cinematic-plan-" + Guid.NewGuid().ToString("N");
				result.planId = newPlanId;
				result.revision = currentRevision;
				result.baseRevision = currentRevision;
				result.approvalRequired = true;
				result.savePerformed = false;
				result.undoAvailable = true;
				result.exactDiff.Add(new ArtistChange { target = director.name, property = CinematicProperty(request), before = "observed", after = CinematicValue(request) });
				result.evidence.Add("cinematic_plan");
				result.evidence.Add("timeline_evidence");
				result.evidence.Add("exact_diff");
				result.evidence.Add("expected_revision");
				plans[newPlanId] = new StoredPlan { planId = newPlanId, baseRevision = currentRevision, cinematic = request, preview = result };
				history.Add(newPlanId);
				PersistState();
				return result;
			}

			if (!plans.TryGetValue(planId ?? string.Empty, out StoredPlan stored) || stored.cinematic == null)
				return Error(result, "PLAN_NOT_FOUND", "The cinematic plan is not present in this Editor session.");
			if (!string.IsNullOrWhiteSpace(expectedRevision) && !string.Equals(expectedRevision, stored.baseRevision, StringComparison.Ordinal))
				return Error(result, "STALE_REVISION", "The cinematic plan revision is stale.");
			if (normalized == "preview")
			{
				stored.preview.command = "artist.cinematic";
				return stored.preview;
			}
			if (string.IsNullOrWhiteSpace(approvalToken)) return Error(result, "APPROVAL_REQUIRED", "Cinematic apply requires an opaque approval token from UnityAgent.");
			if (!string.Equals(expectedRevision, CurrentRevision(), StringComparison.Ordinal)) return Error(result, "STALE_REVISION", "The Editor state changed after the cinematic plan was prepared.");
			if (!ApplyCinematic(stored.cinematic, result)) return result;
			result.planId = planId;
			result.revision = CurrentRevision();
			result.baseRevision = stored.baseRevision;
			result.approvalRequired = true;
			result.savePerformed = false;
			result.undoAvailable = true;
			result.evidence.Add("mutation_evidence");
			result.evidence.Add("undo_registration");
			result.evidence.Add("save_not_performed");
			plans.Remove(planId);
			history.Add("applied:" + planId);
			PersistState();
			return result;
		}

		public static ArtistResult History()
		{
			EnsurePersistentStateLoaded();
			ArtistResult result = Base("artist.history", Support());
			if (!result.support.supported) return Error(result, result.support.errorCode, result.support.reason);
			result.evidence.AddRange(history);
			result.verified = true;
			return result;
		}

		private static bool ApplyIntent(ArtistIntent intent, ArtistResult result)
		{
			if (intent.setFog)
			{
				if (DetectPipeline() == "hdrp")
				{
					if (!ApplyHdrpFog(intent, result)) return false;
				}
				else
				{
					Undo.IncrementCurrentGroup();
					RenderSettings.fog = true;
					RenderSettings.fogDensity = Mathf.Clamp(intent.fogDensity, 0.0f, 1.0f);
					MarkScenesDirty();
					result.exactDiff.Add(new ArtistChange { target = "RenderSettings", property = "fogDensity", before = "observed", after = RenderSettings.fogDensity.ToString("0.####") });
				}
			}
			if (intent.setVolumeLookDev)
			{
				if (DetectPipeline() != "urp")
				{
					Error(result, "URP_VOLUME_REQUIRED", "Volume LookDev intent requires a Unity 6 URP project.");
					return false;
				}
				if (!ApplyUrpVolumeLookDev(intent, result)) return false;
			}
			if (intent.setLightIntensity)
			{
				Light light = FindLight(intent.targetName);
				if (light == null)
				{
					Error(result, "TARGET_NOT_FOUND", "An exact light target is required for lightIntensity.");
					return false;
				}
				Undo.RecordObject(light, "UnityArtistCLI Light LookDev");
				float before = light.intensity;
				light.intensity = Mathf.Max(0.0f, intent.lightIntensity);
				result.exactDiff.Add(new ArtistChange { target = light.name, property = "intensity", before = before.ToString("0.####"), after = light.intensity.ToString("0.####") });
			}
			if (intent.setCameraFieldOfView)
			{
				Camera camera = FindCamera(intent.targetName, intent.targetGuid);
				if (camera == null)
				{
					Error(result, "TARGET_NOT_FOUND", "An exact camera target is required for cameraFieldOfView.");
					return false;
				}
				float minimum = string.Equals(intent.workflow, "camera_fov_reference", StringComparison.Ordinal) ? intent.cameraFovMinimum : 1.0f;
				float maximum = string.Equals(intent.workflow, "camera_fov_reference", StringComparison.Ordinal) ? intent.cameraFovMaximum : 179.0f;
				bool referenceWorkflow = string.Equals(intent.workflow, "camera_fov_reference", StringComparison.Ordinal);
				if (referenceWorkflow && (minimum <= 0.0f || maximum <= 0.0f))
				{
					minimum = 35.0f;
					maximum = 50.0f;
				}
				if (referenceWorkflow && (minimum != 35.0f || maximum != 50.0f))
				{
					Error(result, "CAMERA_FOV_OUTSIDE_APPROVAL", "camera_fov_reference requires the canonical 35..50 approval envelope.");
					return false;
				}
				float before;
				float after;
				string fovError;
				bool applied;
				if (referenceWorkflow)
					applied = UnityArtist.CameraFovWorkflowAdapter.TryApply(camera, intent.targetGuid, UnityArtist.CameraFovWorkflowAdapter.ComponentType, UnityArtist.CameraFovWorkflowAdapter.PropertyPath, intent.cameraFieldOfView, minimum, maximum, out before, out after, out fovError);
				else
					applied = UnityArtist.CameraFovWorkflowAdapter.TryApply(camera, intent.cameraFieldOfView, minimum, maximum, out before, out after, out fovError);
				if (!applied)
				{
					Error(result, "CAMERA_FOV_OUTSIDE_APPROVAL", fovError);
					return false;
				}
				result.exactDiff.Add(new ArtistChange { target = referenceWorkflow ? intent.targetGuid : camera.name, property = UnityArtist.CameraFovWorkflowAdapter.PropertyPath, before = before.ToString("0.####"), after = after.ToString("0.####") });
			}
			return result.errors.Count == 0;
		}

		private static bool ValidateCinematicRequest(CinematicRequest request, ArtistResult result)
		{
			string kind = (request.trackKind ?? string.Empty).Trim().ToLowerInvariant();
			string[] allowed = { "binding", "activation", "animation", "control", "signal", "marker", "cinemachine_shot", "shot" };
			if (!allowed.Contains(kind, StringComparer.Ordinal))
			{
				Error(result, "INVALID_CINEMATIC_REQUEST", "trackKind must be one of binding, activation, animation, control, signal, marker, cinemachine_shot, or shot.");
				return false;
			}
			if (kind != "marker" && string.IsNullOrWhiteSpace(request.trackName))
			{
				Error(result, "INVALID_CINEMATIC_REQUEST", "An exact trackName is required for cinematic mutation.");
				return false;
			}
			if ((kind == "cinemachine_shot" || kind == "shot") && string.IsNullOrWhiteSpace(request.bindingTargetName))
			{
				Error(result, "BINDING_TARGET_REQUIRED", "A Cinemachine shot requires an exact bindingTargetName for its virtual camera.");
				return false;
			}
			return true;
		}

		private static bool ApplyCinematic(CinematicRequest request, ArtistResult result)
		{
			PlayableDirector director = FindDirector(request.directorName);
			if (director == null)
			{
				Error(result, "TIMELINE_DIRECTOR_NOT_FOUND", "An exact PlayableDirector target is required.");
				return false;
			}
			Undo.RecordObject(director, "UnityArtistCLI Cinematic Binding");
			if (director.playableAsset != null) Undo.RecordObject(director.playableAsset, "UnityArtistCLI Timeline Artifact");
			string kind = (request.trackKind ?? string.Empty).Trim().ToLowerInvariant();
			if (kind == "binding")
			{
				if (string.IsNullOrWhiteSpace(request.bindingTargetName))
				{
					Error(result, "BINDING_TARGET_REQUIRED", "Binding mutation requires an exact bindingTargetName.");
					return false;
				}
				UnityEngine.Object bindingKey = FindOutputKey(director, request.trackName);
				GameObject target = FindGameObject(request.bindingTargetName);
				if (bindingKey == null || target == null)
				{
					Error(result, "CINEMATIC_TARGET_NOT_FOUND", "The exact Timeline binding or target GameObject was not found.");
					return false;
				}
				UnityEngine.Object binding = target;
				if (bindingKey.GetType().Name.IndexOf("CinemachineTrack", StringComparison.OrdinalIgnoreCase) >= 0)
				{
					Type brainType = FindType("Unity.Cinemachine.CinemachineBrain", "Unity.Cinemachine")
						?? FindType("Cinemachine.CinemachineBrain", "Cinemachine");
					Component brain = brainType == null ? null : target.GetComponent(brainType);
					if (brain == null)
					{
						Error(result, "CINEMATIC_TARGET_NOT_FOUND", "A CinemachineTrack requires a CinemachineBrain component on the binding target.");
						return false;
					}
					binding = brain;
				}
				director.SetGenericBinding(bindingKey, binding);
				result.exactDiff.Add(new ArtistChange { target = request.trackName, property = "genericBinding", before = "observed", after = binding.name });
				result.evidence.Add("camera_binding");
				return true;
			}

			if (!TryCreateTimelineArtifact(director, request, result)) return false;
			return true;
		}

		private static bool TryCreateTimelineArtifact(PlayableDirector director, CinematicRequest request, ArtistResult result)
		{
			if (director.playableAsset == null)
			{
				Error(result, "TIMELINE_ASSET_NOT_FOUND", "The exact PlayableDirector has no Timeline asset.");
				return false;
			}
			string kind = (request.trackKind ?? string.Empty).Trim().ToLowerInvariant();
			string typeName = kind switch
			{
				"activation" => "UnityEngine.Timeline.ActivationTrack, Unity.Timeline",
				"animation" => "UnityEngine.Timeline.AnimationTrack, Unity.Timeline",
				"control" => "UnityEngine.Timeline.ControlTrack, Unity.Timeline",
				"signal" => "UnityEngine.Timeline.SignalTrack, Unity.Timeline",
				"marker" => "UnityEngine.Timeline.SignalEmitter, Unity.Timeline",
				"cinemachine_shot" or "shot" => "Unity.Cinemachine.CinemachineTrack, Unity.Cinemachine.Runtime",
				_ => string.Empty
			};
			Type artifactType = ResolveCinematicArtifactType(kind, typeName);
			if (artifactType == null)
			{
				Error(result, "CAPABILITY_UNAVAILABLE", "The requested allowlisted Timeline or Cinemachine type is not installed in this Project.");
				return false;
			}
			if (kind == "cinemachine_shot" || kind == "shot")
				return TryCreateCinemachineShot(director, request, artifactType, result);
			if (kind == "marker")
			{
				MethodInfo createMarkerTrack = director.playableAsset.GetType().GetMethod("CreateMarkerTrack", BindingFlags.Instance | BindingFlags.Public);
				PropertyInfo markerTrackProperty = director.playableAsset.GetType().GetProperty("markerTrack", BindingFlags.Instance | BindingFlags.Public);
				if (createMarkerTrack == null || markerTrackProperty == null)
				{
					Error(result, "CAPABILITY_UNAVAILABLE", "The installed Timeline API does not expose marker-track creation.");
					return false;
				}
				try
				{
					createMarkerTrack.Invoke(director.playableAsset, null);
					object markerTrack = markerTrackProperty.GetValue(director.playableAsset, null);
					MethodInfo createMarker = markerTrack == null ? null : markerTrack.GetType().GetMethod("CreateMarker", BindingFlags.Instance | BindingFlags.Public, null, new[] { typeof(Type), typeof(double) }, null);
					object created = createMarker == null ? null : createMarker.Invoke(markerTrack, new object[] { artifactType, (double)request.markerTime });
					if (created == null)
					{
						Error(result, "CINEMATIC_CREATE_FAILED", "The Timeline API did not create the requested marker.");
						return false;
					}
					result.exactDiff.Add(new ArtistChange { target = director.name, property = kind, before = "absent", after = request.markerTime.ToString("0.###") });
					result.evidence.Add("timeline_evidence");
					result.evidence.Add("timeline_marker");
					return true;
				}
				catch (Exception exception)
				{
					Error(result, "CINEMATIC_CREATE_FAILED", exception.InnerException == null ? exception.Message : exception.InnerException.Message);
					return false;
				}
			}
			int expectedParameterCount = kind == "marker" ? 2 : 3;
			MethodInfo create = director.playableAsset.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public)
				.FirstOrDefault(method => method.Name == (kind == "marker" ? "CreateMarker" : "CreateTrack")
					&& method.GetParameters().Length == expectedParameterCount
					&& method.GetParameters()[0].ParameterType == typeof(Type));
			if (create == null)
			{
				Error(result, "CAPABILITY_UNAVAILABLE", "The installed Timeline API does not expose the required bounded creation method.");
				return false;
			}
			try
			{
				object created = kind == "marker"
					? create.Invoke(director.playableAsset, new object[] { artifactType, request.markerTime })
					: create.Invoke(director.playableAsset, new object[] { artifactType, null, request.trackName });
				if (created == null)
				{
					Error(result, "CINEMATIC_CREATE_FAILED", "The Timeline API did not create the requested bounded artifact.");
					return false;
				}
				result.exactDiff.Add(new ArtistChange { target = director.name, property = kind, before = "absent", after = request.trackName ?? request.markerTime.ToString("0.###") });
				result.evidence.Add("timeline_evidence");
				return true;
			}
			catch (Exception exception)
			{
				Error(result, "CINEMATIC_CREATE_FAILED", exception.InnerException == null ? exception.Message : exception.InnerException.Message);
				return false;
			}
		}

		private static bool TryCreateCinemachineShot(PlayableDirector director, CinematicRequest request, Type trackType, ArtistResult result)
		{
			Type shotType = FindType("Unity.Cinemachine.CinemachineShot", "Unity.Cinemachine")
				?? FindType("Cinemachine.CinemachineShot", "Cinemachine");
			if (shotType == null)
			{
				Error(result, "CAPABILITY_UNAVAILABLE", "The installed Cinemachine package does not expose a Timeline shot asset.");
				return false;
			}

			object track = FindTimelineTrack(director.playableAsset, request.trackName, trackType);
			if (track == null)
			{
				MethodInfo createTrack = director.playableAsset.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public)
					.FirstOrDefault(method => method.Name == "CreateTrack" && method.GetParameters().Length == 3 && method.GetParameters()[0].ParameterType == typeof(Type));
				if (createTrack == null)
				{
					Error(result, "CAPABILITY_UNAVAILABLE", "The installed Timeline API does not expose bounded track creation.");
					return false;
				}
				track = createTrack.Invoke(director.playableAsset, new object[] { trackType, null, request.trackName });
			}
			if (track == null)
			{
				Error(result, "CINEMATIC_CREATE_FAILED", "The Timeline API did not create the requested Cinemachine track.");
				return false;
			}

			GameObject cameraObject = FindGameObject(request.bindingTargetName);
			Type virtualCameraType = FindType("Unity.Cinemachine.CinemachineVirtualCameraBase", "Unity.Cinemachine")
				?? FindType("Cinemachine.CinemachineVirtualCameraBase", "Cinemachine");
			Component virtualCamera = virtualCameraType == null || cameraObject == null ? null : cameraObject.GetComponent(virtualCameraType);
			if (virtualCamera == null)
			{
				Error(result, "CINEMATIC_TARGET_NOT_FOUND", "A Cinemachine shot requires a target GameObject with a Cinemachine camera component.");
				return false;
			}

			object clip = FindTimelineClip(track, shotType, request.trackName);
			bool clipWasAbsent = clip == null;
			if (clip == null)
			{
				MethodInfo createClip = track.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public)
					.FirstOrDefault(method => method.Name == "CreateClip" && method.IsGenericMethodDefinition && method.GetGenericArguments().Length == 1 && method.GetParameters().Length == 0);
				if (createClip == null)
				{
					Error(result, "CAPABILITY_UNAVAILABLE", "The installed Timeline API does not expose generic clip creation.");
					return false;
				}
				try
				{
					clip = createClip.MakeGenericMethod(shotType).Invoke(track, null);
				}
				catch (Exception exception)
				{
					Error(result, "CINEMATIC_CREATE_FAILED", exception.InnerException == null ? exception.Message : exception.InnerException.Message);
					return false;
				}
			}
			if (clip == null)
			{
				Error(result, "CINEMATIC_CREATE_FAILED", "The Timeline API did not create the requested Cinemachine shot clip.");
				return false;
			}

			float start = Mathf.Max(0.0f, request.clipStart);
			float duration = request.clipDuration > 0.0f ? request.clipDuration : 0.5f;
			SetMemberValue(clip, "start", (double)start);
			SetMemberValue(clip, "duration", (double)duration);
			object clipAsset = GetMemberValue(clip, "asset");
			if (clipAsset != null)
			{
				SetMemberValue(clipAsset, "DisplayName", request.trackName);
				FieldInfo virtualCameraField = clipAsset.GetType().GetField("VirtualCamera", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
				if (virtualCameraField != null)
				{
					object exposedReference = virtualCameraField.GetValue(clipAsset);
					if (!SetMemberValue(exposedReference, "defaultValue", virtualCamera))
					{
						Error(result, "CINEMATIC_CREATE_FAILED", "The Cinemachine shot asset does not expose a writable virtual-camera reference.");
						return false;
					}
					virtualCameraField.SetValue(clipAsset, exposedReference);
				}
				else
				{
					Error(result, "CINEMATIC_CREATE_FAILED", "The installed Cinemachine shot asset does not expose VirtualCamera.");
					return false;
				}
				if (clipAsset is UnityEngine.Object clipObject) EditorUtility.SetDirty(clipObject);
			}
			result.exactDiff.Add(new ArtistChange
			{
				target = request.trackName,
				property = "cinemachineClip",
				before = clipWasAbsent ? "absent" : "observed",
				after = request.bindingTargetName + "@" + start.ToString("0.###") + "+" + duration.ToString("0.###")
			});
			result.evidence.Add("timeline_evidence");
			result.evidence.Add("cinemachine_shot");
			result.evidence.Add("cinemachine_clip");
			result.evidence.Add("camera_reference:" + request.trackName + "->" + virtualCamera.name);
			return true;
		}

		private static object FindTimelineTrack(UnityEngine.Object asset, string name, Type trackType)
		{
			if (asset == null || string.IsNullOrWhiteSpace(name)) return null;
			MethodInfo getRootTracks = asset.GetType().GetMethod("GetRootTracks", BindingFlags.Instance | BindingFlags.Public);
			if (getRootTracks == null) return null;
			if (!(getRootTracks.Invoke(asset, null) is System.Collections.IEnumerable tracks)) return null;
			foreach (object track in tracks)
			{
				if (track == null || !string.Equals(Convert.ToString(GetMemberValue(track, "name")), name, StringComparison.Ordinal)) continue;
				if (trackType == null || trackType.IsAssignableFrom(track.GetType())) return track;
			}
			return null;
		}

		private static object FindTimelineClip(object track, Type clipType, string displayName)
		{
			if (track == null) return null;
			MethodInfo getClips = track.GetType().GetMethod("GetClips", BindingFlags.Instance | BindingFlags.Public);
			if (getClips == null || !(getClips.Invoke(track, null) is System.Collections.IEnumerable clips)) return null;
			foreach (object clip in clips)
			{
				object asset = GetMemberValue(clip, "asset");
				if (asset != null && (clipType == null || clipType.IsInstanceOfType(asset)) && string.Equals(Convert.ToString(GetMemberValue(clip, "displayName")), displayName, StringComparison.Ordinal)) return clip;
			}
			return null;
		}

		private static Type ResolveCinematicArtifactType(string kind, string typeName)
		{
			if (string.IsNullOrEmpty(typeName)) return null;
			Type artifactType = Type.GetType(typeName, false);
			if (artifactType != null) return artifactType;
			if (kind == "cinemachine_shot" || kind == "shot")
			{
				// Cinemachine 3/6 moved the runtime assembly to Unity.Cinemachine;
				// retain the legacy assembly candidate for older supported projects.
				return FindType("Unity.Cinemachine.CinemachineTrack", "Unity.Cinemachine")
					?? FindType("Cinemachine.CinemachineTrack", "Cinemachine")
					?? FindType("Unity.Cinemachine.CinemachineTrack", "Unity.Cinemachine.Runtime");
			}
			return null;
		}

		private static void InspectCinematicDirector(PlayableDirector director, ArtistResult result)
		{
			result.targets.Add(Target("timeline_director", director, director.enabled));
			if (director.playableAsset == null) return;
			result.evidence.Add("playable_asset:" + director.playableAsset.name);
			foreach (PlayableBinding output in director.playableAsset.outputs)
			{
				UnityEngine.Object key = output.sourceObject;
				if (key == null) continue;
				string typeName = key.GetType().Name;
				result.evidence.Add("timeline_track:" + typeName + ":" + key.name);
				UnityEngine.Object binding = director.GetGenericBinding(key);
				if (binding != null) result.evidence.Add("binding:" + key.name + "->" + binding.name);
				string lower = typeName.ToLowerInvariant();
				if (lower.Contains("cinemachine"))
				{
					result.evidence.Add("cinemachine_shot");
					InspectCinemachineClips(key, result);
				}
				if (lower.Contains("activation")) result.evidence.Add("activation_track");
				if (lower.Contains("signal")) result.evidence.Add("signal_marker");
				if (lower.Contains("control")) result.evidence.Add("control_track");
				if (lower.Contains("animation")) result.evidence.Add("animation_track");
			}
		}

		private static void InspectCinemachineClips(UnityEngine.Object track, ArtistResult result)
		{
			if (track == null) return;
			MethodInfo getClips = track.GetType().GetMethod("GetClips", BindingFlags.Instance | BindingFlags.Public);
			if (getClips == null || !(getClips.Invoke(track, null) is System.Collections.IEnumerable clips)) return;
			foreach (object clip in clips)
			{
				object asset = GetMemberValue(clip, "asset");
				if (asset == null) continue;
				object start = GetMemberValue(clip, "start");
				object duration = GetMemberValue(clip, "duration");
				result.evidence.Add("cinemachine_clip:" + track.name + "@" + TimelineTimeText(start) + "+" + TimelineTimeText(duration));
				object exposedReference = GetMemberValue(asset, "VirtualCamera");
				UnityEngine.Object virtualCamera = GetMemberValue(exposedReference, "defaultValue") as UnityEngine.Object;
				if (virtualCamera != null) result.evidence.Add("camera_reference:" + track.name + "->" + virtualCamera.name);
			}
		}

		private static string CinematicProperty(CinematicRequest request) => (request.trackKind ?? "timeline").Trim().ToLowerInvariant();

		private static string CinematicValue(CinematicRequest request) => string.IsNullOrWhiteSpace(request.trackName) ? request.markerTime.ToString("0.###") : request.trackName;

		private static bool BuildDiff(ArtistResult result, ArtistIntent intent)
		{
			if (intent.setFog && DetectPipeline() == "hdrp")
			{
				if (!TryFindHdrpFog(false, out Component volume, out object fog, out string reason))
				{
					Error(result, "HDRP_VOLUME_FOG_REQUIRED", reason);
					return false;
				}
				object parameter = GetMemberValue(fog, "meanFreePath");
				object before = GetMemberValue(parameter, "value");
				result.exactDiff.Add(new ArtistChange
				{
					target = volume.gameObject.name,
					property = "HDRP.Fog.meanFreePath",
					before = ValueText(before),
					after = ValueText(HdrpMeanFreePath(intent.fogDensity))
				});
			}
			else if (intent.setFog)
			{
				result.exactDiff.Add(new ArtistChange { target = "RenderSettings", property = "fogDensity", before = RenderSettings.fogDensity.ToString("0.####"), after = Mathf.Clamp(intent.fogDensity, 0.0f, 1.0f).ToString("0.####") });
			}
			if (intent.setVolumeLookDev)
			{
				if (DetectPipeline() != "urp")
				{
					Error(result, "URP_VOLUME_REQUIRED", "Volume LookDev intent requires a Unity 6 URP project.");
					return false;
				}
				if (!TryFindUrpVolume(out Component volume, out object profile, out string reason))
				{
					Error(result, "URP_VOLUME_REQUIRED", reason);
					return false;
				}
				Type adjustmentType = FindType("UnityEngine.Rendering.Universal.ColorAdjustments", "Unity.RenderPipelines.Universal.Runtime");
				if (adjustmentType == null)
				{
					Error(result, "URP_VOLUME_API_UNAVAILABLE", "The active URP project does not expose ColorAdjustments.");
					return false;
				}
				object adjustment = FindVolumeComponent(profile, adjustmentType);
				object postExposure = adjustment == null ? null : GetMemberValue(adjustment, "postExposure");
				object contrast = adjustment == null ? null : GetMemberValue(adjustment, "contrast");
				result.exactDiff.Add(new ArtistChange
				{
					target = volume.gameObject.name,
					property = "URP.ColorAdjustments.postExposure",
					before = postExposure == null ? "absent" : ValueText(GetMemberValue(postExposure, "value")),
					after = Mathf.Clamp(intent.volumePostExposure, -10.0f, 10.0f).ToString("0.####")
				});
				result.exactDiff.Add(new ArtistChange
				{
					target = volume.gameObject.name,
					property = "URP.ColorAdjustments.contrast",
					before = contrast == null ? "absent" : ValueText(GetMemberValue(contrast, "value")),
					after = Mathf.Clamp(intent.volumeContrast, -100.0f, 100.0f).ToString("0.####")
				});
				result.evidence.Add("urp_volume_plan");
			}
			if (intent.setLightIntensity) result.exactDiff.Add(new ArtistChange { target = intent.targetName ?? string.Empty, property = "intensity", before = "observed", after = Mathf.Max(0.0f, intent.lightIntensity).ToString("0.####") });
			if (intent.setCameraFieldOfView)
			{
				Camera camera = FindCamera(intent.targetName, intent.targetGuid);
				if (camera == null)
				{
					Error(result, "TARGET_NOT_FOUND", "An exact camera target is required for cameraFieldOfView.");
					return false;
				}
				bool referenceWorkflow = string.Equals(intent.workflow, "camera_fov_reference", StringComparison.Ordinal);
				float minimum = referenceWorkflow ? intent.cameraFovMinimum : 1.0f;
				float maximum = referenceWorkflow ? intent.cameraFovMaximum : 179.0f;
				if (referenceWorkflow && (minimum <= 0.0f || maximum <= 0.0f)) { minimum = 35.0f; maximum = 50.0f; }
				if (referenceWorkflow && (minimum != 35.0f || maximum != 50.0f))
				{
					Error(result, "CAMERA_FOV_OUTSIDE_APPROVAL", "camera_fov_reference requires the canonical 35..50 approval envelope.");
					return false;
				}
				if (referenceWorkflow && !UnityArtist.CameraFovWorkflowAdapter.Validate(camera, intent.targetGuid, UnityArtist.CameraFovWorkflowAdapter.ComponentType, UnityArtist.CameraFovWorkflowAdapter.PropertyPath, minimum, maximum, out string bindingError))
				{
					Error(result, "CAMERA_FOV_TARGET_INVALID", bindingError);
					return false;
				}
				if (float.IsNaN(intent.cameraFieldOfView) || float.IsInfinity(intent.cameraFieldOfView) || intent.cameraFieldOfView < minimum || intent.cameraFieldOfView > maximum)
				{
					Error(result, "CAMERA_FOV_OUTSIDE_APPROVAL", "Camera FOV is outside the approved parameter envelope.");
					return false;
				}
				result.exactDiff.Add(new ArtistChange { target = referenceWorkflow ? intent.targetGuid : camera.name, property = UnityArtist.CameraFovWorkflowAdapter.PropertyPath, before = camera.fieldOfView.ToString("0.####"), after = intent.cameraFieldOfView.ToString("0.####") });
				result.evidence.Add("camera_binding");
			}
			return true;
		}

		private static bool HasChange(ArtistIntent intent)
		{
			return intent.setFog || intent.setVolumeLookDev || intent.setLightIntensity || intent.setCameraFieldOfView;
		}

		private static bool ApplyUrpVolumeLookDev(ArtistIntent intent, ArtistResult result)
		{
			if (!TryFindUrpVolume(out Component volume, out object profile, out string reason))
			{
				Error(result, "URP_VOLUME_REQUIRED", reason);
				return false;
			}
			Type adjustmentType = FindType("UnityEngine.Rendering.Universal.ColorAdjustments", "Unity.RenderPipelines.Universal.Runtime");
			if (adjustmentType == null)
			{
				Error(result, "URP_VOLUME_API_UNAVAILABLE", "The active URP project does not expose ColorAdjustments.");
				return false;
			}
			object adjustment = FindVolumeComponent(profile, adjustmentType) ?? AddVolumeComponent(profile, adjustmentType);
			if (adjustment == null)
			{
				Error(result, "URP_VOLUME_COMPONENT_UNAVAILABLE", "The URP VolumeProfile could not create ColorAdjustments.");
				return false;
			}
			object postExposure = GetMemberValue(adjustment, "postExposure");
			object contrast = GetMemberValue(adjustment, "contrast");
			if (postExposure == null || contrast == null)
			{
				Error(result, "URP_VOLUME_PARAMETER_UNAVAILABLE", "ColorAdjustments does not expose postExposure and contrast.");
				return false;
			}
			Undo.IncrementCurrentGroup();
			if (volume != null) Undo.RecordObject(volume, "UnityArtistCLI URP Volume LookDev");
			if (profile is UnityEngine.Object profileObject) Undo.RecordObject(profileObject, "UnityArtistCLI URP Volume LookDev");
			if (adjustment is UnityEngine.Object adjustmentObject) Undo.RecordObject(adjustmentObject, "UnityArtistCLI URP Volume LookDev");
			object beforeExposure = GetMemberValue(postExposure, "value");
			object beforeContrast = GetMemberValue(contrast, "value");
			float afterExposure = Mathf.Clamp(intent.volumePostExposure, -10.0f, 10.0f);
			float afterContrast = Mathf.Clamp(intent.volumeContrast, -100.0f, 100.0f);
			if (!SetMemberValue(postExposure, "overrideState", true) || !SetMemberValue(postExposure, "value", afterExposure)
				|| !SetMemberValue(contrast, "overrideState", true) || !SetMemberValue(contrast, "value", afterContrast))
			{
				Error(result, "URP_VOLUME_PARAMETER_UNAVAILABLE", "The URP ColorAdjustments parameters could not be overridden.");
				return false;
			}
			SetMemberValue(adjustment, "active", true);
			if (profile is UnityEngine.Object dirtyProfile) EditorUtility.SetDirty(dirtyProfile);
			if (adjustment is UnityEngine.Object dirtyAdjustment) EditorUtility.SetDirty(dirtyAdjustment);
			if (volume != null) EditorUtility.SetDirty(volume);
			MarkScenesDirty();
			result.exactDiff.Add(new ArtistChange { target = volume.gameObject.name, property = "URP.ColorAdjustments.postExposure", before = ValueText(beforeExposure), after = ValueText(afterExposure) });
			result.exactDiff.Add(new ArtistChange { target = volume.gameObject.name, property = "URP.ColorAdjustments.contrast", before = ValueText(beforeContrast), after = ValueText(afterContrast) });
			result.evidence.Add("urp_native_volume");
			result.evidence.Add("urp_color_adjustments");
			return true;
		}

		private static bool TryFindUrpVolume(out Component volume, out object profile, out string reason)
		{
			volume = null;
			profile = null;
			reason = string.Empty;
			Type volumeType = FindType("UnityEngine.Rendering.Volume", "Unity.RenderPipelines.Core.Runtime");
			if (volumeType == null)
			{
				reason = "The active URP project does not expose the Unity Volume type.";
				return false;
			}
			volume = SceneObjects(volumeType).OfType<Component>().OrderBy(value => value.gameObject.name).FirstOrDefault();
			if (volume == null)
			{
				reason = "An existing scene Volume is required for a scoped URP LookDev intent.";
				return false;
			}
			profile = GetMemberValue(volume, "sharedProfile");
			if (profile == null) profile = GetMemberValue(volume, "profile");
			if (profile == null)
			{
				reason = "The exact URP Volume has no profile; create and assign one before planning LookDev.";
				return false;
			}
			return true;
		}

		private static object FindVolumeComponent(object profile, Type componentType)
		{
			if (profile == null || componentType == null) return null;
			System.Collections.IEnumerable components = GetMemberValue(profile, "components") as System.Collections.IEnumerable;
			if (components == null) return null;
			foreach (object component in components)
			{
				if (component != null && componentType.IsInstanceOfType(component)) return component;
			}
			return null;
		}

		private static object AddVolumeComponent(object profile, Type componentType)
		{
			if (profile == null || componentType == null) return null;
			MethodInfo addGeneric = profile.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public)
				.FirstOrDefault(method => method.Name == "Add" && method.IsGenericMethodDefinition && method.GetGenericArguments().Length == 1 && method.GetParameters().Length == 1 && method.GetParameters()[0].ParameterType == typeof(bool));
			if (addGeneric != null)
			{
				try { return addGeneric.MakeGenericMethod(componentType).Invoke(profile, new object[] { true }); }
				catch (Exception) { return null; }
			}
			MethodInfo addType = profile.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public)
				.FirstOrDefault(method => method.Name == "Add" && !method.IsGenericMethod && method.GetParameters().Length == 2 && method.GetParameters()[0].ParameterType == typeof(Type) && method.GetParameters()[1].ParameterType == typeof(bool));
			if (addType == null) return null;
			try { return addType.Invoke(profile, new object[] { componentType, true }); }
			catch (Exception) { return null; }
		}

		private static bool ApplyHdrpFog(ArtistIntent intent, ArtistResult result)
		{
			if (!TryFindHdrpFog(true, out Component volume, out object fog, out string reason))
			{
				Error(result, "HDRP_VOLUME_FOG_REQUIRED", reason);
				return false;
			}

			UnityEngine.Object fogObject = fog as UnityEngine.Object;
			Undo.IncrementCurrentGroup();
			if (volume != null) Undo.RecordObject(volume, "UnityArtistCLI HDRP Volume Fog");
			if (fogObject != null) Undo.RecordObject(fogObject, "UnityArtistCLI HDRP Volume Fog");
			object parameter = GetMemberValue(fog, "meanFreePath");
			object before = GetMemberValue(parameter, "value");
			float after = HdrpMeanFreePath(intent.fogDensity);
			if (!SetMemberValue(parameter, "overrideState", true) || !SetMemberValue(parameter, "value", after))
			{
				Error(result, "HDRP_FOG_PARAMETER_UNAVAILABLE", "The HDRP Fog.meanFreePath parameter could not be overridden.");
				return false;
			}
			SetMemberValue(fog, "active", true);
			if (fogObject != null) EditorUtility.SetDirty(fogObject);
			if (volume != null) EditorUtility.SetDirty(volume);
			MarkScenesDirty();
			result.exactDiff.Add(new ArtistChange
			{
				target = volume.gameObject.name,
				property = "HDRP.Fog.meanFreePath",
				before = ValueText(before),
				after = ValueText(after)
			});
			result.evidence.Add("hdrp_native_volume");
			result.evidence.Add("hdrp_fog_mean_free_path");
			return true;
		}

		private static bool TryFindHdrpFog(bool forApply, out Component volume, out object fog, out string reason)
		{
			volume = null;
			fog = null;
			reason = string.Empty;
			Type volumeType = FindType("UnityEngine.Rendering.Volume", "Unity.RenderPipelines.Core.Runtime");
			Type fogType = FindType("UnityEngine.Rendering.HighDefinition.Fog", "Unity.RenderPipelines.HighDefinition.Runtime");
			if (volumeType == null || fogType == null)
			{
				reason = "The active HDRP project does not expose the Unity Volume and HDRP Fog types.";
				return false;
			}
			volume = SceneObjects(volumeType).OfType<Component>().OrderBy(value => value.gameObject.name).FirstOrDefault();
			if (volume == null)
			{
				reason = "An existing scene Volume with an HDRP Fog component is required for a scoped HDRP fog intent.";
				return false;
			}
			object profile = GetMemberValue(volume, forApply ? "profile" : "profileRef");
			if (profile == null) profile = GetMemberValue(volume, "sharedProfile");
			if (profile == null)
			{
				reason = "The exact HDRP Volume has no profile; create and assign one before planning fog.";
				return false;
			}
			System.Collections.IEnumerable components = GetMemberValue(profile, "components") as System.Collections.IEnumerable;
			if (components != null)
			{
				foreach (object component in components)
				{
					if (component != null && component.GetType() == fogType)
					{
						fog = component;
						break;
					}
				}
			}
			if (fog == null)
			{
				reason = "The exact HDRP Volume profile does not contain a Fog override.";
				return false;
			}
			if (GetMemberValue(fog, "meanFreePath") == null)
			{
				reason = "The installed HDRP Fog API does not expose meanFreePath.";
				return false;
			}
			return true;
		}

		private static Type FindType(string fullName, string assemblyName)
		{
			Type direct = Type.GetType(fullName + ", " + assemblyName, false);
			if (direct != null) return direct;
			return AppDomain.CurrentDomain.GetAssemblies().Select(assembly => assembly.GetType(fullName, false)).FirstOrDefault(type => type != null);
		}

		private static IEnumerable<UnityEngine.Object> SceneObjects(Type type)
		{
			if (type == null) return Enumerable.Empty<UnityEngine.Object>();
			return Resources.FindObjectsOfTypeAll(type).Where(value =>
			{
				Component component = value as Component;
				return component != null && component.gameObject.scene.IsValid() && !EditorUtility.IsPersistent(component);
			});
		}

		private static object GetMemberValue(object target, string name)
		{
			if (target == null) return null;
			Type type = target.GetType();
			PropertyInfo property = type.GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
			if (property != null && property.GetMethod != null) return property.GetValue(target, null);
			FieldInfo field = type.GetField(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
			return field == null ? null : field.GetValue(target);
		}

		private static bool SetMemberValue(object target, string name, object value)
		{
			if (target == null) return false;
			Type type = target.GetType();
			PropertyInfo property = type.GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
			if (property != null && property.SetMethod != null)
			{
				property.SetValue(target, value, null);
				return true;
			}
			FieldInfo field = type.GetField(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
			if (field == null || field.IsInitOnly) return false;
			field.SetValue(target, value);
			return true;
		}

		private static float HdrpMeanFreePath(float fogDensity)
		{
			return Mathf.Clamp(1.0f / Mathf.Max(0.0001f, fogDensity), 1.0f, 10000.0f);
		}

		private static string ValueText(object value)
		{
			if (value is float floatValue) return floatValue.ToString("0.####", System.Globalization.CultureInfo.InvariantCulture);
			return value == null ? string.Empty : Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture);
		}

		private static string TimelineTimeText(object value)
		{
			if (value == null) return string.Empty;
			try { return Convert.ToDouble(value, System.Globalization.CultureInfo.InvariantCulture).ToString("0.###", System.Globalization.CultureInfo.InvariantCulture); }
			catch (Exception) { return ValueText(value); }
		}

		private static ArtistResult Base(string command, ArtistSupport support)
		{
			EnsurePersistentStateLoaded();
			ArtistResult result = new ArtistResult { command = command, status = "passed", support = support, revision = CurrentRevision(), baseRevision = CurrentRevision(), savePerformed = false, undoAvailable = true };
			if (persistentBatchSession) result.evidence.Add("bounded_non_mcp_batch_fallback");
			return result;
		}

		private static ArtistResult Error(ArtistResult result, string code, string message)
		{
			result.status = "blocked";
			result.verified = false;
			result.errors.Add(new ArtistError { code = code, message = message });
			return result;
		}

		private static ArtistSupport Support()
		{
			string version = Application.unityVersion ?? string.Empty;
			string pipeline = DetectPipeline();
			bool supported = ArtistCompatibility.IsSupported(version, pipeline);
			return new ArtistSupport
			{
				supported = supported,
				supportTier = supported ? "primary" : "unsupported",
				unityVersion = version,
				renderPipeline = pipeline,
				compatibilityBackend = supported ? ArtistCompatibility.Backend(pipeline) : "none",
				transport = string.IsNullOrWhiteSpace(transportOverride) ? (persistentBatchSession ? "official_unity_cli_bounded_batch_fallback" : "official_unity_cli_pipeline") : transportOverride,
				errorCode = supported ? string.Empty : (version.StartsWith("2022.3.", StringComparison.Ordinal) ? "UNSUPPORTED_RENDER_PIPELINE_VERSION" : "UNSUPPORTED_UNITY_VERSION"),
				reason = supported ? string.Empty : "This Unity version and render pipeline are outside the formal UnityArtistCLI release matrix."
			};
		}

		private static string DetectPipeline()
		{
			RenderPipelineAsset asset = GraphicsSettings.currentRenderPipeline;
			if (asset == null) return "builtin";
			string typeName = asset.GetType().FullName ?? asset.GetType().Name;
			if (typeName.IndexOf("HDRenderPipeline", StringComparison.OrdinalIgnoreCase) >= 0 || typeName.IndexOf("HDRP", StringComparison.OrdinalIgnoreCase) >= 0) return "hdrp";
			if (typeName.IndexOf("Universal", StringComparison.OrdinalIgnoreCase) >= 0 || typeName.IndexOf("URP", StringComparison.OrdinalIgnoreCase) >= 0) return "urp";
			return "unknown";
		}

		private static IEnumerable<T> SceneObjects<T>() where T : Component
		{
			return Resources.FindObjectsOfTypeAll<T>().Where(value => value != null && value.gameObject.scene.IsValid() && !EditorUtility.IsPersistent(value));
		}

		private static ArtistTarget Target(string kind, Component component, bool enabled)
		{
			ArtistTarget target = new ArtistTarget { kind = kind, name = component.name, scenePath = component.gameObject.scene.path, hierarchyPath = HierarchyPath(component.transform), enabled = enabled };
			try { target.globalObjectId = GlobalObjectId.GetGlobalObjectIdSlow(component).ToString(); } catch (Exception) { target.globalObjectId = string.Empty; }
			if (component is Camera camera) target.fieldOfView = camera.fieldOfView;
			return target;
		}

		private static string HierarchyPath(Transform transform)
		{
			return transform.parent == null ? transform.name : HierarchyPath(transform.parent) + "/" + transform.name;
		}

		private static Light FindLight(string name)
		{
			return SceneObjects<Light>().FirstOrDefault(value => string.Equals(value.name, name, StringComparison.Ordinal));
		}

		private static Camera FindCamera(string name, string globalObjectId = null)
		{
			IEnumerable<Camera> cameras = SceneObjects<Camera>();
			if (!string.IsNullOrWhiteSpace(globalObjectId))
			{
				Camera exact = cameras.FirstOrDefault(value =>
				{
					try { return string.Equals(GlobalObjectId.GetGlobalObjectIdSlow(value).ToString(), globalObjectId, StringComparison.Ordinal); } catch (Exception) { return false; }
				});
				if (exact == null) return null;
				if (!string.IsNullOrWhiteSpace(name) && !string.Equals(exact.name, name, StringComparison.Ordinal)) return null;
				return exact;
			}
			if (!string.IsNullOrWhiteSpace(name)) return cameras.FirstOrDefault(value => string.Equals(value.name, name, StringComparison.Ordinal));
			return cameras.FirstOrDefault(value => value.CompareTag("MainCamera")) ?? cameras.FirstOrDefault();
		}

		private static PlayableDirector FindDirector(string name)
		{
			IEnumerable<PlayableDirector> directors = SceneObjects<PlayableDirector>();
			if (!string.IsNullOrWhiteSpace(name)) return directors.FirstOrDefault(value => string.Equals(value.name, name, StringComparison.Ordinal));
			return directors.FirstOrDefault();
		}

		private static GameObject FindGameObject(string name)
		{
			if (string.IsNullOrWhiteSpace(name)) return null;
			return SceneObjects<Transform>().FirstOrDefault(value => string.Equals(value.name, name, StringComparison.Ordinal))?.gameObject;
		}

		private static UnityEngine.Object FindOutputKey(PlayableDirector director, string name)
		{
			if (director == null || director.playableAsset == null || string.IsNullOrWhiteSpace(name)) return null;
			foreach (PlayableBinding output in director.playableAsset.outputs)
			{
				if (output.sourceObject != null && string.Equals(output.sourceObject.name, name, StringComparison.Ordinal)) return output.sourceObject;
			}
			return null;
		}

		private static string CurrentRevision()
		{
			StringBuilder material = new StringBuilder(Application.unityVersion);
			for (int index = 0; index < SceneManager.sceneCount; index++) material.Append('|').Append(SceneManager.GetSceneAt(index).path);
			foreach (Light light in SceneObjects<Light>().OrderBy(value => value.name)) material.Append('|').Append(light.name).Append(':').Append(light.intensity.ToString("R"));
			foreach (Camera camera in SceneObjects<Camera>().OrderBy(value => value.name)) material.Append('|').Append(camera.name).Append(':').Append(camera.fieldOfView.ToString("R"));
			if (DetectPipeline() == "hdrp" && TryFindHdrpFog(false, out Component volume, out object fog, out string reason))
			{
				object parameter = GetMemberValue(fog, "meanFreePath");
				material.Append("|hdrp:").Append(volume.gameObject.name).Append(':').Append(ValueText(GetMemberValue(parameter, "value")));
			}
			if (DetectPipeline() == "urp" && TryFindUrpVolume(out Component urpVolume, out object urpProfile, out string urpReason))
			{
				Type adjustmentType = FindType("UnityEngine.Rendering.Universal.ColorAdjustments", "Unity.RenderPipelines.Universal.Runtime");
				object adjustment = FindVolumeComponent(urpProfile, adjustmentType);
				material.Append("|urp-volume:").Append(urpVolume.gameObject.name);
				if (adjustment != null)
				{
					material.Append(':').Append(ValueText(GetMemberValue(GetMemberValue(adjustment, "postExposure"), "value")));
					material.Append(':').Append(ValueText(GetMemberValue(GetMemberValue(adjustment, "contrast"), "value")));
				}
				else material.Append(":absent");
			}
			using (SHA256 sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(material.ToString()))).Replace("-", string.Empty).ToLowerInvariant();
		}

		private static void MarkScenesDirty()
		{
			for (int index = 0; index < SceneManager.sceneCount; index++)
			{
				Scene scene = SceneManager.GetSceneAt(index);
				if (scene.IsValid() && scene.isLoaded) EditorSceneManager.MarkSceneDirty(scene);
			}
		}

		private static string Serialize(ArtistResult result) => JsonUtility.ToJson(result, true);

		private static string PersistentStatePath()
		{
			string projectRoot = Directory.GetParent(Application.dataPath).FullName;
			return Path.Combine(projectRoot, "Library", "UnityArtist", "BatchSession.json");
		}

		private static void EnsurePersistentStateLoaded()
		{
			if (!persistentBatchSession || persistentStateLoaded) return;
			persistentStateLoaded = true;
			try
			{
				string path = PersistentStatePath();
				if (!File.Exists(path)) return;
				PersistentState state = JsonUtility.FromJson<PersistentState>(File.ReadAllText(path));
				if (state == null) return;
				plans.Clear();
				foreach (StoredPlan plan in state.plans ?? new List<StoredPlan>())
					if (plan != null && !string.IsNullOrWhiteSpace(plan.planId)) plans[plan.planId] = plan;
				captures.Clear();
				foreach (StoredCapture capture in state.captures ?? new List<StoredCapture>())
					if (capture != null && !string.IsNullOrWhiteSpace(capture.captureId) && capture.result != null) captures[capture.captureId] = capture.result;
				history.Clear();
				if (state.history != null) history.AddRange(state.history);
			}
			catch (Exception exception)
			{
				Debug.LogWarning("UnityArtistCLI batch session state was not loaded: " + exception.Message);
			}
		}

		private static void PersistState()
		{
			if (!persistentBatchSession) return;
			try
			{
				string path = PersistentStatePath();
				Directory.CreateDirectory(Path.GetDirectoryName(path));
				PersistentState state = new PersistentState();
				state.plans.AddRange(plans.Values);
				foreach (KeyValuePair<string, ArtistResult> capture in captures)
					state.captures.Add(new StoredCapture { captureId = capture.Key, result = capture.Value });
				state.history.AddRange(history);
				File.WriteAllText(path, JsonUtility.ToJson(state, true));
			}
			catch (Exception exception)
			{
				Debug.LogWarning("UnityArtistCLI batch session state was not persisted: " + exception.Message);
			}
		}
	}

}

#endif
