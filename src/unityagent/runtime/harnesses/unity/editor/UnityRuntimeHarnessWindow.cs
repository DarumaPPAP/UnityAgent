using System;
using UnityEditor;
using UnityEngine;

namespace UnityAgent.Runtime.Harnesses.Unity.Editor
{
    public sealed class UnityRuntimeHarnessWindow : EditorWindow
    {
        private DefaultAsset _rootFolder;
        private bool _includePackageDependencies = true;
        private string _outputPath = "RuntimeEvidence/artifact-graph.json";
        private UnityEngine.Object _impactTarget;
        private int _impactMaxDepth = 8;
        private Vector2 _scroll;
        private UnityArtifactGraph _graph;
        private UnityArtifactImpactResult _impact;
        private UnityArtifactGraphScanner _scanner;
        private UnityArtifactGraphExporter _exporter;
        private UnityArtifactImpactAnalyzer _analyzer;

        [MenuItem("Tools/UnityAgent/Runtime/Artifact Dependency Graph")]
        private static void Open() => GetWindow<UnityRuntimeHarnessWindow>("Runtime Artifact Graph");

        private void OnEnable()
        {
            _scanner = new UnityArtifactGraphScanner();
            _exporter = new UnityArtifactGraphExporter();
            _analyzer = new UnityArtifactImpactAnalyzer();
            _rootFolder = AssetDatabase.LoadAssetAtPath<DefaultAsset>("Assets");
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("Runtime Unity Artifact Dependency Harness", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox("Asset依存を観測するRuntime Harnessです。AgentのParentGraph/SubGraphではありません。", MessageType.Info);
            _rootFolder = (DefaultAsset)EditorGUILayout.ObjectField("走査対象", _rootFolder, typeof(DefaultAsset), false);
            _includePackageDependencies = EditorGUILayout.Toggle("Package依存", _includePackageDependencies);
            _outputPath = EditorGUILayout.TextField("JSON出力", _outputPath);
            var rootPath = _rootFolder == null ? string.Empty : AssetDatabase.GetAssetPath(_rootFolder);
            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUI.DisabledScope(string.IsNullOrEmpty(rootPath) || !AssetDatabase.IsValidFolder(rootPath))) if (GUILayout.Button("走査")) Run(() => { _graph = _scanner.Scan(rootPath, _includePackageDependencies); _impact = null; });
                using (new EditorGUI.DisabledScope(_graph == null)) if (GUILayout.Button("Evidence JSON出力")) Run(() => _exporter.Export(_graph, _outputPath));
            }
            _impactTarget = EditorGUILayout.ObjectField("変更対象Asset", _impactTarget, typeof(UnityEngine.Object), false);
            _impactMaxDepth = EditorGUILayout.IntSlider("最大Hop", _impactMaxDepth, 1, 32);
            var target = _impactTarget == null ? string.Empty : AssetDatabase.GetAssetPath(_impactTarget);
            using (new EditorGUI.DisabledScope(_graph == null || string.IsNullOrEmpty(target))) if (GUILayout.Button("影響範囲")) Run(() => _impact = _analyzer.FindImpactedArtifacts(_graph, target, _impactMaxDepth));
            if (_graph == null) return;
            EditorGUILayout.LabelField("Node / Edge", _graph.Nodes.Count + " / " + _graph.Edges.Count);
            if (_impact != null) EditorGUILayout.LabelField("Impact", _impact.Items.Count.ToString());
            _scroll = EditorGUILayout.BeginScrollView(_scroll, GUILayout.MinHeight(120));
            foreach (var node in _graph.Nodes) EditorGUILayout.LabelField(node.Kind, node.Path);
            EditorGUILayout.EndScrollView();
        }

        private static void Run(Action action)
        {
            try { action(); }
            catch (Exception exception) { Debug.LogException(exception); EditorUtility.DisplayDialog("Runtime Harness", exception.Message, "閉じる"); }
        }
    }
}
