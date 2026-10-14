#if UNITY_EDITOR

using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace UnityArtist.Tests
{
	/// <summary>
	/// Creates the disposable Built-in Camera FOV fixture through the Unity
	/// Editor API. The Golden Task never edits Unity YAML directly.
	/// </summary>
	public static class UnityArtistReferenceFixtureBootstrap
	{
		public static void Prepare()
		{
			Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
			GameObject cameraObject = new GameObject("Main Camera");
			cameraObject.tag = "MainCamera";
			cameraObject.transform.position = new Vector3(0.0f, 1.0f, -6.0f);
			cameraObject.transform.rotation = Quaternion.identity;
			Camera camera = cameraObject.AddComponent<Camera>();
			camera.fieldOfView = 40.0f;
			camera.clearFlags = CameraClearFlags.SolidColor;
			camera.backgroundColor = new Color(0.08f, 0.10f, 0.14f, 1.0f);

			GameObject subject = GameObject.CreatePrimitive(PrimitiveType.Cube);
			subject.name = "FovSubject";
			subject.transform.position = new Vector3(0.0f, 0.0f, 4.0f);

			GameObject lightObject = new GameObject("Key Light");
			Light light = lightObject.AddComponent<Light>();
			light.type = LightType.Directional;
			light.intensity = 1.0f;
			light.transform.rotation = Quaternion.Euler(35.0f, -25.0f, 0.0f);

			string scenePath = "Assets/ReferenceCameraFovGolden.unity";
			Directory.CreateDirectory(Path.Combine(Application.dataPath, "Editor"));
			EditorSceneManager.SaveScene(scene, scenePath, true);
			EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(scenePath, true) };
			AssetDatabase.SaveAssets();
			EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
			EditorApplication.Exit(0);
		}
	}
}

#endif
