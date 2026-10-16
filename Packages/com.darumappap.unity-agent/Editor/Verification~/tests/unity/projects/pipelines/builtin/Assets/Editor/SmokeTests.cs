using NUnit.Framework;
using System.Collections;
using System.IO;
using UnityEngine.TestTools;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityArtist;

namespace UnityCi {
 public class PipelineSmokeTests {
  RenderPipelineAsset previousGraphics, previousQuality;
  [SetUp] public void OpenConcreteSceneAndConfigurePipeline() {
   if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null) {
    Debug.LogError("UNITY_CI_GRAPHICS_UNAVAILABLE: graphicsDeviceType=Null");
    Assert.Fail("Real graphics device required for pipeline smoke");
   }
   previousGraphics = GraphicsSettings.defaultRenderPipeline; previousQuality = QualitySettings.renderPipeline;
   EditorSceneManager.OpenScene("Assets/Scenes/PipelineSmoke.unity");
   GraphicsSettings.defaultRenderPipeline = null; QualitySettings.renderPipeline = null;
  }
  [TearDown] public void RestorePipeline() {
   GraphicsSettings.defaultRenderPipeline = previousGraphics; QualitySettings.renderPipeline = previousQuality;
   AssetDatabase.DeleteAsset("Assets/CiPipeline.asset"); AssetDatabase.DeleteAsset("Assets/CiRenderer.asset");
  }
  [Test] public void SceneContainsCameraLightAndRenderableSubject() {
   Assert.IsNotNull(Camera.main); Assert.IsNotNull(Object.FindFirstObjectByType<Light>());
   var subject = GameObject.Find("FovSubject"); Assert.IsNotNull(subject);
   Assert.IsNotNull(subject.GetComponent<MeshRenderer>()); Assert.IsNotNull(subject.GetComponent<MeshFilter>().sharedMesh);
   Assert.IsTrue(ArtistCompatibility.IsSupported(Application.unityVersion, "builtin"));
  }
  [Test] public void NativePipelineSettingsCanBeConfigured() { Assert.IsNull(GraphicsSettings.defaultRenderPipeline); RenderSettings.fog = true; RenderSettings.fogDensity = 0.03f; Assert.AreEqual(0.03f, RenderSettings.fogDensity); }

  [UnityTest] public IEnumerator CameraRendersConcreteSubjectAndReadbackHasSpatialVariation() {
   var camera = Camera.main; Assert.IsNotNull(camera);
   camera.clearFlags = CameraClearFlags.SolidColor; camera.backgroundColor = Color.green;

   var subject = GameObject.Find("FovSubject");
   var shader = Shader.Find("Unlit/Color");
   Assert.IsNotNull(shader); Assert.IsTrue(shader.isSupported, "Pipeline shader unsupported by measured graphics device");
   var material = new Material(shader); material.SetColor("_Color", Color.red);
   subject.GetComponent<MeshRenderer>().sharedMaterial = material;
   // Aim at the actual geometry instead of relying on a scene's historical camera pose.
   camera.transform.position = subject.transform.position + new Vector3(0, 0, -5);
   camera.transform.LookAt(subject.transform.position); camera.fieldOfView = 40f;
   var target = new RenderTexture(128, 128, 24); target.Create();
   var pixels = new Texture2D(128, 128, TextureFormat.RGB24, false);
   var previousTarget = camera.targetTexture; var previousActive = RenderTexture.active;
   try {
    camera.targetTexture = target;
    EditorApplication.QueuePlayerLoopUpdate(); yield return null;
    camera.Render();
    RenderTexture.active = target; pixels.ReadPixels(new Rect(0, 0, 128, 128), 0, 0); pixels.Apply();
    var samples = pixels.GetPixels(); float minimum = float.MaxValue, maximum = float.MinValue;
    foreach (var pixel in samples) { var value = pixel.r - pixel.g; minimum = Mathf.Min(minimum, value); maximum = Mathf.Max(maximum, value); }
    Assert.Greater(maximum - minimum, 0.1f, "Camera output lacks geometry/background variation");
    var artifacts = System.Environment.GetEnvironmentVariable("UNITY_CI_ARTIFACTS");
    Assert.IsFalse(string.IsNullOrEmpty(artifacts));
    File.WriteAllBytes(Path.Combine(artifacts, "pipeline-smoke.png"), pixels.EncodeToPNG());
    File.WriteAllText(Path.Combine(artifacts, "graphics-device.json"), JsonUtility.ToJson(new GraphicsObservation {
     editorVersion = Application.unityVersion, deviceType = SystemInfo.graphicsDeviceType.ToString(),
     deviceName = SystemInfo.graphicsDeviceName, pixelVariation = maximum - minimum }));
   } finally {
    camera.targetTexture = previousTarget; RenderTexture.active = previousActive;
    target.Release(); Object.DestroyImmediate(target); Object.DestroyImmediate(pixels); Object.DestroyImmediate(material);
   }
  }
  [System.Serializable] public class GraphicsObservation { public string editorVersion, deviceType, deviceName; public float pixelVariation; }
 }
}
