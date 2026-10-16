using System;
using System.Collections;
using System.IO;
using System.Linq;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace UnityAgent.Production
{
    // G1のRock生成・承認・Rollbackは実行しない。独立したP9の実Editor検証。
    public sealed class LtsPreflightTests
    {
        private const string TemporaryRoot = "Assets/UnityAgentP9Preflight";

        [Serializable]
        private sealed class GraphicsObservation
        {
            public string editorVersion;
            public string deviceType;
            public float pixelVariation;
        }

        [UnityTest]
        public IEnumerator UrpRenderGraphCapture()
        {
            Assert.AreEqual("6000.3.12f1", Application.unityVersion);
            Assert.IsFalse(EditorApplication.isPlayingOrWillChangePlaymode);
            Assert.IsFalse(EditorUtility.scriptCompilationFailed);
            Assert.IsFalse(AssetDatabase.IsValidFolder(TemporaryRoot), "P9 fixture output already exists");
            Assert.AreNotEqual(GraphicsDeviceType.Null, SystemInfo.graphicsDeviceType,
                "UNITY_CI_GRAPHICS_UNAVAILABLE: real GPU required");

            string evidence = Environment.GetEnvironmentVariable("UNITY_CI_ARTIFACTS");
            Assert.IsNotEmpty(evidence, "P9 evidence directory is required");
            Assert.IsFalse(Path.GetFullPath(evidence).StartsWith(
                Path.GetFullPath(Application.dataPath), StringComparison.OrdinalIgnoreCase));
            Directory.CreateDirectory(evidence);

            var previousScenes = EditorSceneManager.GetSceneManagerSetup();
            var previousGraphics = GraphicsSettings.defaultRenderPipeline;
            var previousQuality = QualitySettings.renderPipeline;
            var previousActive = RenderTexture.active;
            GameObject subject = null;
            GameObject cameraObject = null;
            GameObject lightObject = null;
            RenderTexture target = null;
            Texture2D pixels = null;
            bool ownsAssets = false;
            try
            {
                AssetDatabase.CreateFolder("Assets", "UnityAgentP9Preflight");
                ownsAssets = true;
                var rendererData = ScriptableObject.CreateInstance<UniversalRendererData>();
                AssetDatabase.CreateAsset(rendererData, TemporaryRoot + "/Renderer.asset");
                var pipeline = UniversalRenderPipelineAsset.Create(rendererData);
                AssetDatabase.CreateAsset(pipeline, TemporaryRoot + "/Pipeline.asset");
                GraphicsSettings.defaultRenderPipeline = pipeline;
                QualitySettings.renderPipeline = pipeline;
                var renderGraph = GraphicsSettings.GetRenderPipelineSettings<RenderGraphSettings>();
                Assert.IsNotNull(renderGraph);
                Assert.IsFalse(renderGraph.enableRenderCompatibilityMode, "RenderGraph must be enabled");

                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                subject = GameObject.CreatePrimitive(PrimitiveType.Cube);
                subject.transform.position = Vector3.zero;
                var shader = Shader.Find("Universal Render Pipeline/Lit");
                Assert.IsNotNull(shader);
                Assert.IsTrue(shader.isSupported);
                var material = new Material(shader);
                AssetDatabase.CreateAsset(material, TemporaryRoot + "/Subject.mat");
                subject.GetComponent<Renderer>().sharedMaterial = material;
                cameraObject = new GameObject("P9Camera");
                var camera = cameraObject.AddComponent<Camera>();
                cameraObject.AddComponent<UniversalAdditionalCameraData>();
                camera.transform.position = new Vector3(0f, 0f, -3f);
                camera.transform.LookAt(Vector3.zero);
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = Color.magenta;
                lightObject = new GameObject("P9Light");
                var light = lightObject.AddComponent<Light>();
                light.type = LightType.Directional;
                light.transform.rotation = Quaternion.Euler(35f, -20f, 0f);

                target = new RenderTexture(128, 128, 24);
                target.Create();
                pixels = new Texture2D(128, 128, TextureFormat.RGB24, false);
                camera.targetTexture = target;
                EditorApplication.QueuePlayerLoopUpdate();
                yield return null;
                var request = new RenderPipeline.StandardRequest { destination = target };
                Assert.IsTrue(RenderPipeline.SupportsRenderRequest(camera, request));
                RenderPipeline.SubmitRenderRequest(camera, request);
                RenderTexture.active = target;
                pixels.ReadPixels(new Rect(0, 0, 128, 128), 0, 0);
                pixels.Apply();
                var colors = pixels.GetPixels32();
                bool varied = colors.Any(p => p.r != colors[0].r || p.g != colors[0].g || p.b != colors[0].b);
                Assert.IsTrue(varied, "URP capture has no spatial variation");
                File.WriteAllBytes(Path.Combine(evidence, "pipeline-smoke.png"), pixels.EncodeToPNG());
                File.WriteAllText(Path.Combine(evidence, "graphics-device.json"),
                    JsonUtility.ToJson(new GraphicsObservation
                    {
                        editorVersion = Application.unityVersion,
                        deviceType = SystemInfo.graphicsDeviceType.ToString(),
                        pixelVariation = 1f
                    }, true));
            }
            finally
            {
                RenderTexture.active = previousActive;
                if (cameraObject != null)
                {
                    var camera = cameraObject.GetComponent<Camera>();
                    if (camera != null) camera.targetTexture = null;
                    Object.DestroyImmediate(cameraObject);
                }
                if (subject != null) Object.DestroyImmediate(subject);
                if (lightObject != null) Object.DestroyImmediate(lightObject);
                if (target != null)
                {
                    target.Release();
                    Object.DestroyImmediate(target);
                }
                if (pixels != null) Object.DestroyImmediate(pixels);
                GraphicsSettings.defaultRenderPipeline = previousGraphics;
                QualitySettings.renderPipeline = previousQuality;
                if (previousScenes != null) EditorSceneManager.RestoreSceneManagerSetup(previousScenes);
                if (ownsAssets) AssetDatabase.DeleteAsset(TemporaryRoot);
            }
        }
    }
}
