using System;
using System.Reflection;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.PackageManager;
using UnityEngine;

namespace DarumaPPAP.UnityAgent.Tests
{
    public sealed class EditTests
    {
        [Test]
        public void ProductionPackageLoadsEditorWindow()
        {
            var assembly = Assembly.Load("DarumaPPAP.UnityAgent.Editor");
            var package = PackageInfo.FindForAssembly(assembly);
            Assert.That(package, Is.Not.Null);
            Assert.That(package.name, Is.EqualTo("com.darumappap.unity-agent"));
            var window = assembly.GetType("DarumaPPAP.UnityAgent.Editor.SetupWindow", true);
            Assert.That(typeof(EditorWindow).IsAssignableFrom(window), Is.True);
        }

        [Test]
        public void AssetDatabaseRoundTripsUrpMaterial()
        {
            string folder = "Assets/UnityAgentSmoke-" + Guid.NewGuid().ToString("N");
            string path = folder + "/Smoke.mat";
            try
            {
                Assert.That(AssetDatabase.CreateFolder("Assets", folder.Substring("Assets/".Length)), Is.Not.Empty);
                var shader = Shader.Find("Universal Render Pipeline/Lit");
                Assert.That(shader, Is.Not.Null, "URP 17.3.0のImportを確認してください。");
                AssetDatabase.CreateAsset(new Material(shader), path);
                AssetDatabase.SaveAssets();
                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
                var loaded = AssetDatabase.LoadAssetAtPath<Material>(path);
                Assert.That(loaded, Is.Not.Null);
                Assert.That(loaded.shader, Is.EqualTo(shader));
            }
            finally
            {
                // このテストが所有する一意な一時Folderだけを削除する。
                AssetDatabase.DeleteAsset(folder);
            }
        }
    }
}
