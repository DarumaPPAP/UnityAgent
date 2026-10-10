using System;
using System.Collections.Generic;
using System.Linq;

namespace UnityAgent.Runtime.Harnesses.Unity.Editor
{
    public sealed class UnityArtifactImpactAnalyzer
    {
        public UnityArtifactImpactResult FindImpactedArtifacts(UnityArtifactGraph graph, string targetAssetPath, int maxDepth)
        {
            if (graph == null) throw new ArgumentNullException(nameof(graph));
            if (string.IsNullOrWhiteSpace(targetAssetPath)) throw new ArgumentException("変更対象Assetを指定してください。", nameof(targetAssetPath));
            if (maxDepth < 1) throw new ArgumentOutOfRangeException(nameof(maxDepth));
            var targetPath = targetAssetPath.Replace('\\', '/').TrimEnd('/');
            var nodesById = graph.Nodes.Where(node => node != null && !string.IsNullOrEmpty(node.Id)).GroupBy(node => node.Id).ToDictionary(group => group.Key, group => group.First(), StringComparer.Ordinal);
            var target = graph.Nodes.FirstOrDefault(node => string.Equals(node.Path, targetPath, StringComparison.Ordinal));
            if (target == null) throw new InvalidOperationException("走査済みGraphに変更対象Assetが存在しません。");
            var reverse = new Dictionary<string, List<string>>(StringComparer.Ordinal);
            foreach (var edge in graph.Edges)
            {
                if (edge == null || edge.Relation != "DEPENDS_ON") continue;
                if (!reverse.TryGetValue(edge.TargetId, out var sources)) { sources = new List<string>(); reverse.Add(edge.TargetId, sources); }
                sources.Add(edge.SourceId);
            }
            var result = new UnityArtifactImpactResult { Target = target, MaxDepth = maxDepth };
            var visited = new HashSet<string>(StringComparer.Ordinal) { target.Id };
            var pending = new Queue<Tuple<string, int>>();
            pending.Enqueue(Tuple.Create(target.Id, 0));
            while (pending.Count > 0)
            {
                var current = pending.Dequeue();
                if (current.Item2 >= maxDepth || !reverse.TryGetValue(current.Item1, out var sources)) continue;
                foreach (var sourceId in sources.OrderBy(value => value, StringComparer.Ordinal))
                {
                    if (!visited.Add(sourceId) || !nodesById.TryGetValue(sourceId, out var node)) continue;
                    var distance = current.Item2 + 1;
                    result.Items.Add(new UnityArtifactImpactItem { Node = node, Distance = distance });
                    pending.Enqueue(Tuple.Create(sourceId, distance));
                }
            }
            result.Items = result.Items.OrderBy(item => item.Distance).ThenBy(item => item.Node.Path, StringComparer.Ordinal).ToList();
            return result;
        }
    }
}
