using System;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace UnityAgent.Runtime.Harnesses.Unity.Editor
{
    public sealed class UnityArtifactGraphExporter
    {
        public string Serialize(UnityArtifactGraph graph, bool prettyPrint)
        {
            if (graph == null) throw new ArgumentNullException(nameof(graph));
            return JsonUtility.ToJson(graph, prettyPrint);
        }
        public string Export(UnityArtifactGraph graph, string projectRelativePath)
        {
            if (graph == null) throw new ArgumentNullException(nameof(graph));
            if (string.IsNullOrWhiteSpace(projectRelativePath)) throw new ArgumentException("出力先を指定してください。", nameof(projectRelativePath));
            var projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            var outputPath = Path.GetFullPath(Path.Combine(projectRoot, projectRelativePath));
            var prefix = projectRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!outputPath.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("出力先はUnity Project配下のファイルに限定されています。");
            var directory = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);
            File.WriteAllText(outputPath, Serialize(graph, true), new UTF8Encoding(false));
            if (projectRelativePath.Replace('\\', '/').StartsWith("Assets/", StringComparison.Ordinal)) AssetDatabase.Refresh();
            return outputPath;
        }
    }
}
