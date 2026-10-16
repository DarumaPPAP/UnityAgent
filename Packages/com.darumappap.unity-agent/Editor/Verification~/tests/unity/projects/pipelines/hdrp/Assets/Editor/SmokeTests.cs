using NUnit.Framework;
using System.Collections;
using System.IO;
using UnityEngine.TestTools;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityArtist;
using UnityEngine.Rendering.HighDefinition;
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
   PlayerSettings.colorSpace = ColorSpace.Linear;
   var asset = ScriptableObject.CreateInstance<HDRenderPipelineAsset>();
   AssetDatabase.CreateAsset(asset, "Assets/CiPipeline.asset");
   GraphicsSettings.defaultRenderPipeline = asset; QualitySettings.renderPipeline = asset;
  }
  [TearDown] public void RestorePipeline() {
   GraphicsSettings.defaultRenderPipeline = previousGraphics; QualitySettings.renderPipeline = previousQuality;
   AssetDatabase.DeleteAsset("Assets/CiPipeline.asset"); AssetDatabase.DeleteAsset("Assets/CiRenderer.asset");
  }
  [Test] public void SceneContainsCameraLightAndRenderableSubject() {
   Assert.IsNotNull(Camera.main); Assert.IsNotNull(Object.FindFirstObjectByType<Light>());
   var subject = GameObject.Find("FovSubject"); Assert.IsNotNull(subject);
   Assert.IsNotNull(subject.GetComponent<MeshRenderer>()); Assert.IsNotNull(subject.GetComponent<MeshFilter>().sharedMesh);
   Assert.IsTrue(ArtistCompatibility.IsSupported(Application.unityVersion, "hdrp"));
  }
  [Test] public void NativePipelineSettingsCanBeConfigured() { Assert.IsInstanceOf<HDRenderPipelineAsset>(GraphicsSettings.defaultRenderPipeline);
   Assert.AreEqual(ColorSpace.Linear, PlayerSettings.colorSpace);
   var volume = new GameObject("SmokeVolume").AddComponent<Volume>();
   volume.isGlobal = true; volume.sharedProfile = ScriptableObject.CreateInstance<VolumeProfile>();
   var fog = volume.sharedProfile.Add<Fog>(); fog.meanFreePath.Override(50f);
   Assert.AreEqual(50f, fog.meanFreePath.value); }

  [UnityTest] public IEnumerator CameraRendersConcreteSubjectAndReadbackHasSpatialVariation() {
   var camera = Camera.main; Assert.IsNotNull(camera);
   camera.clearFlags = CameraClearFlags.SolidColor; camera.backgroundColor = Color.green;
   var nativeCamera = camera.GetComponent<HDAdditionalCameraData>();
   if (nativeCamera == null) nativeCamera = camera.gameObject.AddComponent<HDAdditionalCameraData>();
   nativeCamera.clearColorMode = HDAdditionalCameraData.ClearColorMode.Color;
   nativeCamera.backgroundColorHDR = Color.green;
   var subject = GameObject.Find("FovSubject");
   var shader = Shader.Find("HDRP/Unlit");
   Assert.IsNotNull(shader); Assert.IsTrue(shader.isSupported, "Pipeline shader unsupported by measured graphics device");
   var material = new Material(shader); material.SetColor("_UnlitColor", Color.red);
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
    var request = new RenderPipeline.StandardRequest { destination = target };
    Assert.IsTrue(RenderPipeline.SupportsRenderRequest(camera, request), "Selected SRP does not support standard camera render requests");
    RenderPipeline.SubmitRenderRequest(camera, request);
    Assert.IsInstanceOf<HDRenderPipeline>(RenderPipelineManager.currentPipeline, "Selected SRP was configured but never activated");
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
