using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace UnityAgent.G1
{
    public sealed class RockProductionTests
    {
        private const string Root = "Assets/UnityAgentRockG1";
        private const string Model = Root + "/Rock.fbx";
        private SceneSetup[] previousScenes;
        private RenderPipelineAsset previousGraphics;
        private RenderPipelineAsset previousQuality;
        private string evidenceDirectory;
        private bool ownsRoot;

        [Serializable]
        private sealed class Artifact
        {
            public string sha256;
            public int vertices;
            public int triangles;
            public float[] scale;
            public float[] dimensions;
            public int uv_layers;
            public string[] texture_dependencies;
        }

        [Serializable]
        private sealed class Observation
        {
            public string schema_version = "1.0";
            public string gate;
            public string status;
            public string unity_version;
            public string graphics_api;
            public string source_sha256;
            public string artifact_guid;
            public string capture_sha256;
            public string source_revision;
            public string limitation = "Editor fixture only; not Production Runtime or Player/Device evidence";
        }

        [SetUp]
        public void RequireIndependentFixture()
        {
            Assert.AreEqual("6000.3.12f1", Application.unityVersion);
            Assert.IsFalse(EditorApplication.isPlayingOrWillChangePlaymode);
            Assert.IsFalse(EditorUtility.scriptCompilationFailed, "Editor compilation failed");
            Assert.IsFalse(Directory.Exists(Root) || File.Exists(Root + ".meta"), "Existing fixture output requires manual reconciliation");
            previousScenes = EditorSceneManager.GetSceneManagerSetup();
            for (int i = 0; i < UnityEngine.SceneManagement.SceneManager.sceneCount; i++)
                Assert.IsFalse(UnityEngine.SceneManagement.SceneManager.GetSceneAt(i).isDirty, "Unsaved scene must be saved before test");
            evidenceDirectory = Environment.GetEnvironmentVariable("UNITYAGENT_G1_EVIDENCE");
            Assert.IsNotEmpty(evidenceDirectory, "BLOCKED_NOT_RUN: evidence directory is required");
            Assert.IsFalse(Path.GetFullPath(evidenceDirectory).StartsWith(Path.GetFullPath(Application.dataPath), StringComparison.OrdinalIgnoreCase));
            Directory.CreateDirectory(evidenceDirectory);
            previousGraphics = GraphicsSettings.defaultRenderPipeline;
            previousQuality = QualitySettings.renderPipeline;
            AssetDatabase.CreateFolder("Assets", "UnityAgentRockG1");
            ownsRoot = true;
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [TearDown]
        public void RestoreFixture()
        {
            GraphicsSettings.defaultRenderPipeline = previousGraphics;
            QualitySettings.renderPipeline = previousQuality;
            if (previousScenes != null) EditorSceneManager.RestoreSceneManagerSetup(previousScenes);
            // 本Fixtureが生成した範囲だけを破棄する。実Project向けRollbackではない。
            if (ownsRoot) AssetDatabase.DeleteAsset(Root);
        }

        [UnityTest]
        public IEnumerator ImportPrefabSceneReimportRenderAndUndo()
        {
            string fbx = Environment.GetEnvironmentVariable("UNITYAGENT_G1_FBX");
            string manifest = Environment.GetEnvironmentVariable("UNITYAGENT_G1_ARTIFACT");
            Assert.IsTrue(File.Exists(fbx), "BLOCKED_NOT_RUN: Control Plane Staging FBX missing");
            Assert.IsTrue(File.Exists(manifest), "BLOCKED_NOT_RUN: Artifact manifest missing");
            var artifact = JsonUtility.FromJson<Artifact>(File.ReadAllText(manifest));
            Assert.AreEqual(artifact.sha256, Hash(fbx), "Staging hash differs");
            Assert.Greater(artifact.vertices, 0);
            Assert.Greater(artifact.triangles, 0);
            Assert.Greater(artifact.uv_layers, 0);
            CollectionAssert.AreEqual(new float[] { 1, 1, 1 }, artifact.scale);
            Assert.IsNotNull(artifact.texture_dependencies);
            Assert.IsEmpty(artifact.texture_dependencies);
            Assert.AreNotEqual(GraphicsDeviceType.Null, SystemInfo.graphicsDeviceType, "BLOCKED_NOT_RUN: real graphics required");

            var rendererData = ScriptableObject.CreateInstance<UniversalRendererData>();
            AssetDatabase.CreateAsset(rendererData, Root + "/Renderer.asset");
            var pipeline = UniversalRenderPipelineAsset.Create(rendererData);
            AssetDatabase.CreateAsset(pipeline, Root + "/Pipeline.asset");
            GraphicsSettings.defaultRenderPipeline = pipeline;
            QualitySettings.renderPipeline = pipeline;
            var renderGraph = GraphicsSettings.GetRenderPipelineSettings<RenderGraphSettings>();
            Assert.IsNotNull(renderGraph, "BLOCKED_NOT_RUN: URP global RenderGraph settings unavailable");
            Assert.IsFalse(renderGraph.enableRenderCompatibilityMode, "RenderGraph must be enabled");

            File.Copy(fbx, Model, false);
            AssetDatabase.ImportAsset(Model, ImportAssetOptions.ForceSynchronousImport);
            var importer = AssetImporter.GetAtPath(Model) as ModelImporter;
            Assert.IsNotNull(importer);
            importer.globalScale = 1;
            importer.materialImportMode = ModelImporterMaterialImportMode.None;
            importer.SaveAndReimport();
            string guid = AssetDatabase.AssetPathToGUID(Model);
            Assert.IsNotEmpty(guid);
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(Model);
            Assert.IsNotNull(model);
            var meshes = model.GetComponentsInChildren<MeshFilter>(true);
            Assert.IsNotEmpty(meshes);
            Assert.AreEqual(artifact.triangles, meshes.Sum(m => m.sharedMesh.triangles.Length / 3));
            Assert.IsTrue(meshes.All(m => m.sharedMesh != null));
            var shader = Shader.Find("Universal Render Pipeline/Lit");
            Assert.IsNotNull(shader);
            Assert.IsTrue(shader.isSupported);
            var material = new Material(shader);
            material.SetColor("_BaseColor", new Color(0.32f, 0.29f, 0.25f));
            AssetDatabase.CreateAsset(material, Root + "/Rock.mat");
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(model);
            foreach (var renderer in instance.GetComponentsInChildren<Renderer>(true)) renderer.sharedMaterial = material;
            var prefab = PrefabUtility.SaveAsPrefabAsset(instance, Root + "/Rock.prefab");
            Assert.IsNotNull(prefab);
            Object.DestroyImmediate(instance);
            instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            Assert.IsTrue(instance.GetComponentsInChildren<Transform>(true).All(
                t => GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(t.gameObject) == 0));
            Assert.IsTrue(instance.GetComponentsInChildren<Renderer>(true).All(
                r => r.sharedMaterials.All(m => m != null && m.shader != null && m.shader.isSupported)));
            Assert.IsTrue(EditorSceneManager.SaveScene(instance.scene, Root + "/Rock.unity"));

            string metaBefore = Hash(Model + ".meta");
            AssetDatabase.ImportAsset(Model, ImportAssetOptions.ForceUpdate | ImportAssetOptions.ForceSynchronousImport);
            Assert.AreEqual(guid, AssetDatabase.AssetPathToGUID(Model));
            Assert.AreEqual(metaBefore, Hash(Model + ".meta"));
            Assert.IsTrue(instance.GetComponentsInChildren<MeshFilter>(true).All(m => m.sharedMesh != null));
            var loadedPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(Root + "/Rock.prefab");
            Assert.IsTrue(loadedPrefab.GetComponentsInChildren<MeshFilter>(true).All(m => m.sharedMesh != null));
            Record("import_prefab_scene_guid", "passed", artifact.sha256, guid, null);

            var camera = new GameObject("RockCamera").AddComponent<Camera>();
            camera.gameObject.AddComponent<UniversalAdditionalCameraData>();
            camera.transform.position = new Vector3(0, 0.2f, -2.5f);
            camera.transform.LookAt(instance.transform.position);
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = Color.magenta;
            var light = new GameObject("RockLight").AddComponent<Light>();
            light.type = LightType.Directional;
            light.transform.rotation = Quaternion.Euler(40, -30, 0);
            var target = new RenderTexture(256, 256, 24);
            target.Create();
            var pixels = new Texture2D(256, 256, TextureFormat.RGB24, false);
            var previousActive = RenderTexture.active;
            try
            {
                camera.targetTexture = target;
                EditorApplication.QueuePlayerLoopUpdate();
                yield return null;
                var request = new RenderPipeline.StandardRequest { destination = target };
                Assert.IsTrue(RenderPipeline.SupportsRenderRequest(camera, request));
                RenderPipeline.SubmitRenderRequest(camera, request);
                RenderTexture.active = target;
                pixels.ReadPixels(new Rect(0, 0, 256, 256), 0, 0);
                pixels.Apply();
                var values = pixels.GetPixels32();
                Assert.IsTrue(values.Any(p => p.r != values[0].r || p.g != values[0].g || p.b != values[0].b), "Capture has no spatial variation");
                string capture = Path.Combine(evidenceDirectory, "Rock.png");
                File.WriteAllBytes(capture, pixels.EncodeToPNG());
                Record("render_capture", "passed", artifact.sha256, guid, Hash(capture));
                // 画像が存在しても品質を断定しない。QAのVisual reviewは別Gate。
                Record("visual_acceptance", "not_observed", artifact.sha256, guid, Hash(capture));
            }
            finally
            {
                camera.targetTexture = null;
                RenderTexture.active = previousActive;
                target.Release();
                Object.DestroyImmediate(target);
                Object.DestroyImmediate(pixels);
            }
            int group = Undo.GetCurrentGroup();
            Undo.IncrementCurrentGroup();
            group = Undo.GetCurrentGroup();
            var temporary = new GameObject("RollbackProbe");
            Undo.RegisterCreatedObjectUndo(temporary, "G1 bounded failure probe");
            Undo.RevertAllDownToGroup(group);
            Assert.IsTrue(temporary == null);
            Assert.IsNotNull(instance);
            Record("editor_undo_probe", "passed", artifact.sha256, guid, null);
        }

        private void Record(string gate, string status, string sourceHash, string guid, string captureHash)
        {
            var result = new Observation { gate = gate, status = status, unity_version = Application.unityVersion,
                graphics_api = SystemInfo.graphicsDeviceType.ToString(), source_sha256 = sourceHash,
                artifact_guid = guid, capture_sha256 = captureHash,
                source_revision = Environment.GetEnvironmentVariable("UNITYAGENT_SOURCE_REVISION") };
            File.WriteAllText(Path.Combine(evidenceDirectory, gate + ".json"), JsonUtility.ToJson(result, true));
        }

        private static string Hash(string path)
        {
            using var algorithm = SHA256.Create();
            using var stream = File.OpenRead(path);
            return BitConverter.ToString(algorithm.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
    }
}
