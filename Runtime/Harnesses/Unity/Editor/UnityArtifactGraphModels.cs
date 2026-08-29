using System;
using System.Collections.Generic;

namespace UnityAgent.Runtime.Harnesses.Unity.Editor
{
    public enum UnityArtifactKind
    {
        Unknown, Scene, Prefab, Material, Shader, HlslInclude, Script,
        AssemblyDefinition, ScriptableObjectAsset, Texture, Model, Audio,
        Animation, PackageAsset
    }

    public enum UnityArtifactDiagnosticSeverity { Info, Warning, Error }

    [Serializable] public sealed class UnityArtifactNode { public string Id; public string Guid; public string Path; public string Name; public string Kind; }
    [Serializable] public sealed class UnityArtifactEdge { public string SourceId; public string TargetId; public string Relation; public string Evidence; }
    [Serializable] public sealed class UnityArtifactScanDiagnostic { public string Code; public string Severity; public string Path; public string Message; }
    [Serializable]
    public sealed class UnityArtifactScanReport
    {
        public long DurationMilliseconds;
        public int RootAssetCount;
        public int ProcessedAssetCount;
        public int NodeCount;
        public int EdgeCount;
        public int MissingGuidCount;
        public int UnknownAssetKindCount;
        public int DuplicateEdgeCount;
        public int PackageDependencySkippedCount;
        public int UnsupportedDependencySkippedCount;
        public bool DiagnosticLimitReached;
        public List<UnityArtifactScanDiagnostic> Diagnostics = new List<UnityArtifactScanDiagnostic>();
    }
    [Serializable]
    public sealed class UnityArtifactGraph
    {
        public string SchemaVersion = "0.2.0";
        public string UnityVersion;
        public string GeneratedAtUtc;
        public string RootAssetPath;
        public UnityArtifactScanReport Report = new UnityArtifactScanReport();
        public List<UnityArtifactNode> Nodes = new List<UnityArtifactNode>();
        public List<UnityArtifactEdge> Edges = new List<UnityArtifactEdge>();
    }
    public sealed class UnityArtifactImpactItem { public UnityArtifactNode Node; public int Distance; }
    public sealed class UnityArtifactImpactResult { public UnityArtifactNode Target; public int MaxDepth; public List<UnityArtifactImpactItem> Items = new List<UnityArtifactImpactItem>(); }
}
