using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace UnityAgent.Runtime.Harnesses.Unity.Editor
{
    public sealed class UnityArtifactGraphScanner
    {
        private const int MAX_DIAGNOSTIC_COUNT = 100;

        public UnityArtifactGraph Scan(string rootAssetPath, bool includePackageDependencies)
        {
            var root = Normalize(rootAssetPath);
            if (string.IsNullOrWhiteSpace(root) || !AssetDatabase.IsValidFolder(root))
                throw new ArgumentException("有効なUnity Assetフォルダを指定してください。", nameof(rootAssetPath));
            var stopwatch = Stopwatch.StartNew();
            var report = new UnityArtifactScanReport();
            var graph = new UnityArtifactGraph { UnityVersion = Application.unityVersion, GeneratedAtUtc = DateTime.UtcNow.ToString("O"), RootAssetPath = root, Report = report };
            var nodes = new Dictionary<string, UnityArtifactNode>(StringComparer.Ordinal);
            var edgeKeys = new HashSet<string>(StringComparer.Ordinal);
            var scheduled = new HashSet<string>(StringComparer.Ordinal);
            var pending = new Queue<string>();
            var roots = AssetDatabase.FindAssets(string.Empty, new[] { root }).Select(AssetDatabase.GUIDToAssetPath).Select(Normalize).Where(path => !string.IsNullOrEmpty(path) && !AssetDatabase.IsValidFolder(path)).Distinct(StringComparer.Ordinal).OrderBy(path => path, StringComparer.Ordinal).ToArray();
            report.RootAssetCount = roots.Length;
            foreach (var path in roots) if (scheduled.Add(path)) pending.Enqueue(path);
            while (pending.Count > 0)
            {
                var sourcePath = pending.Dequeue();
                if (!Accept(sourcePath, includePackageDependencies, report)) continue;
                report.ProcessedAssetCount++;
                var source = Node(sourcePath, nodes, report);
                var dependencies = AssetDatabase.GetDependencies(sourcePath, false).Select(Normalize).Where(path => !string.IsNullOrEmpty(path)).Distinct(StringComparer.Ordinal).OrderBy(path => path, StringComparer.Ordinal);
                foreach (var dependencyPath in dependencies)
                {
                    if (string.Equals(sourcePath, dependencyPath, StringComparison.Ordinal) || AssetDatabase.IsValidFolder(dependencyPath)) continue;
                    if (!Accept(dependencyPath, includePackageDependencies, report)) continue;
                    var target = Node(dependencyPath, nodes, report);
                    var edgeKey = source.Id + "|DEPENDS_ON|" + target.Id;
                    if (edgeKeys.Add(edgeKey)) graph.Edges.Add(new UnityArtifactEdge { SourceId = source.Id, TargetId = target.Id, Relation = "DEPENDS_ON", Evidence = "AssetDatabase.GetDependencies(path, false)" });
                    else report.DuplicateEdgeCount++;
                    if (scheduled.Add(dependencyPath)) pending.Enqueue(dependencyPath);
                }
            }
            graph.Nodes = nodes.Values.OrderBy(node => node.Path, StringComparer.Ordinal).ToList();
            graph.Edges = graph.Edges.OrderBy(edge => edge.SourceId, StringComparer.Ordinal).ThenBy(edge => edge.TargetId, StringComparer.Ordinal).ThenBy(edge => edge.Relation, StringComparer.Ordinal).ToList();
            stopwatch.Stop();
            report.DurationMilliseconds = stopwatch.ElapsedMilliseconds;
            report.NodeCount = graph.Nodes.Count;
            report.EdgeCount = graph.Edges.Count;
            return graph;
        }

        private UnityArtifactNode Node(string path, IDictionary<string, UnityArtifactNode> nodes, UnityArtifactScanReport report)
        {
            if (nodes.TryGetValue(path, out var existing)) return existing;
            var guid = AssetDatabase.AssetPathToGUID(path);
            var kind = Classify(path);
            if (string.IsNullOrEmpty(guid)) { report.MissingGuidCount++; Diagnostic(report, "MISSING_GUID", UnityArtifactDiagnosticSeverity.Warning, path, "AssetDatabaseからGUIDを取得できませんでした。PathをNode IDとして使用します。"); }
            if (kind == UnityArtifactKind.Unknown) { report.UnknownAssetKindCount++; Diagnostic(report, "UNKNOWN_ASSET_KIND", UnityArtifactDiagnosticSeverity.Info, path, "拡張子に対応するArtifact種別が未定義です。"); }
            var node = new UnityArtifactNode { Id = string.IsNullOrEmpty(guid) ? "path:" + path : guid, Guid = guid, Path = path, Name = Path.GetFileNameWithoutExtension(path), Kind = kind.ToString() };
            nodes.Add(path, node);
            return node;
        }

        private bool Accept(string path, bool includePackages, UnityArtifactScanReport report)
        {
            if (path.StartsWith("Assets/", StringComparison.Ordinal) || path == "Assets") return true;
            if (path.StartsWith("Packages/", StringComparison.Ordinal)) { if (includePackages) return true; report.PackageDependencySkippedCount++; return false; }
            report.UnsupportedDependencySkippedCount++;
            return false;
        }

        private void Diagnostic(UnityArtifactScanReport report, string code, UnityArtifactDiagnosticSeverity severity, string path, string message)
        {
            if (report.Diagnostics.Count >= MAX_DIAGNOSTIC_COUNT) { report.DiagnosticLimitReached = true; return; }
            report.Diagnostics.Add(new UnityArtifactScanDiagnostic { Code = code, Severity = severity.ToString(), Path = path, Message = message });
        }

        private static string Normalize(string path) => string.IsNullOrEmpty(path) ? string.Empty : path.Replace('\\', '/').TrimEnd('/');
        private static UnityArtifactKind Classify(string path)
        {
            switch (Path.GetExtension(path).ToLowerInvariant())
            {
                case ".unity": return UnityArtifactKind.Scene;
                case ".prefab": return UnityArtifactKind.Prefab;
                case ".mat": return UnityArtifactKind.Material;
                case ".shader": case ".shadergraph": case ".shadersubgraph": case ".compute": return UnityArtifactKind.Shader;
                case ".hlsl": case ".cginc": return UnityArtifactKind.HlslInclude;
                case ".cs": return UnityArtifactKind.Script;
                case ".asmdef": return UnityArtifactKind.AssemblyDefinition;
                case ".asset": return UnityArtifactKind.ScriptableObjectAsset;
                case ".png": case ".jpg": case ".jpeg": case ".tga": case ".psd": case ".exr": return UnityArtifactKind.Texture;
                case ".fbx": case ".obj": case ".dae": return UnityArtifactKind.Model;
                case ".wav": case ".mp3": case ".ogg": return UnityArtifactKind.Audio;
                case ".anim": case ".controller": return UnityArtifactKind.Animation;
                default: return path.StartsWith("Packages/", StringComparison.Ordinal) ? UnityArtifactKind.PackageAsset : UnityArtifactKind.Unknown;
            }
        }
    }
}
