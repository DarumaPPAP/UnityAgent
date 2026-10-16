#if UNITY_EDITOR

using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace UnityArtistVerification2022
{
	public static class FixtureBootstrap
	{
		public static void Create()
		{
			Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

			GameObject cameraObject = new GameObject("Main Camera");
			cameraObject.tag = "MainCamera";
			Camera camera = cameraObject.AddComponent<Camera>();
			camera.transform.position = new Vector3(0.0f, 2.5f, -8.0f);
			camera.transform.rotation = Quaternion.Euler(12.0f, 0.0f, 0.0f);
			camera.fieldOfView = 40.0f;

			GameObject lightObject = new GameObject("Key Light");
			Light light = lightObject.AddComponent<Light>();
			light.type = LightType.Directional;
			light.intensity = 1.0f;
			light.transform.rotation = Quaternion.Euler(45.0f, -30.0f, 0.0f);

			GameObject floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
			floor.name = "Courtyard Floor";
			floor.transform.position = new Vector3(0.0f, -0.5f, 0.0f);
			floor.transform.localScale = new Vector3(8.0f, 1.0f, 8.0f);

			GameObject subject = GameObject.CreatePrimitive(PrimitiveType.Capsule);
			subject.name = "Artist Subject";
			subject.transform.position = new Vector3(-1.5f, 1.0f, 2.0f);

			GameObject goal = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
			goal.name = "Artist Goal";
			goal.transform.position = new Vector3(1.5f, 0.5f, 4.0f);

			RenderSettings.ambientLight = new Color(0.18f, 0.22f, 0.30f, 1.0f);
			RenderSettings.fog = true;
			RenderSettings.fogMode = FogMode.Exponential;
			RenderSettings.fogDensity = 0.015f;

			EditorSceneManager.MarkSceneDirty(scene);
			EditorSceneManager.SaveScene(scene, "Assets/Scenes/ArtistVerification.unity");
			EditorBuildSettings.scenes = new[]
			{
				new EditorBuildSettingsScene("Assets/Scenes/ArtistVerification.unity", true)
			};
			EditorApplication.Exit(0);
		}
	}
}

#endif
