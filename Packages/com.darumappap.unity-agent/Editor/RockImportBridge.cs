using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

namespace DarumaPPAP.UnityAgent.Editor
{
    /// <summary>
    /// 承認された固定Rock Fixtureのみ。任意のEditorコード実行経路ではない。
    /// Runtime側がProject Lease、Approval、Ticketのハッシュを検証する。
    /// このBridgeもファイルとScopeを確認し、保存結果をReceiptで返す。
    /// </summary>
    internal static class RockImportBridge
    {
        private const string Root = "Assets/UnityAgentRockG1";
        private const string ModelPath = Root + "/Rock.fbx";
        private const string MaterialPath = Root + "/Rock.mat";
        private const string PrefabPath = Root + "/Rock.prefab";
        private const string ScenePath = Root + "/Rock.unity";

        [Serializable]
        private sealed class Ticket
        {
            public string schema_version;
            public string project_root;
            public string action;
            public string source_sha256;
            public string receipt_path;
            public string receipt_sha256;
            public string result_path;
            public string state_root;
            public string plan_id;
            public string mutation_approval_ref;
            public string save_approval_ref;
            public string rollback_approval_ref;
        }

        [Serializable]
        private sealed class ApprovalDecision
        {
            public string approval_decision_id;
            public string operation;
            public string plan_id;
            public string project_root;
            public string status;
            public string human_review;
            public string expires_at;
            public int revocation_epoch;
        }

        [Serializable]
        private sealed class ApprovalRecord
        {
            public string schema_version;
            public ApprovalDecision decision;
            public int current_revocation_epoch;
        }

        [Serializable]
        private sealed class OwnedFile
        {
            public string path;
            public string sha256;
            public string guid;
        }

        [Serializable]
        private sealed class Receipt
        {
            public string schema_version = "1.0";
            public string project_root;
            public string source_sha256;
            public string unity_version;
            public string artifact_guid;
            public OwnedFile[] files;
            public string status;
        }

        private static string ProjectRoot
        {
            get { return Path.GetFullPath(Path.Combine(Application.dataPath, "..")).TrimEnd('\\', '/'); }
        }

        private static string Absolute(string relative)
        {
            return Path.Combine(ProjectRoot, relative.Replace('/', Path.DirectorySeparatorChar));
        }

        private static string Hash(string path)
        {
            using (var sha = SHA256.Create())
            using (var stream = File.OpenRead(path))
            {
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
            }
        }

        private static Ticket ReadTicket(string action)
        {
            string file = Environment.GetEnvironmentVariable("UNITYAGENT_ROCK_IMPORT_TICKET");
            if (string.IsNullOrEmpty(file) || !Path.IsPathRooted(file) || !File.Exists(file))
                throw new InvalidOperationException("Reviewed Rock ticket is missing");
            var ticket = JsonUtility.FromJson<Ticket>(File.ReadAllText(file));
            if (ticket == null || ticket.schema_version != "1.0" || ticket.action != action ||
                !string.Equals(Path.GetFullPath(ticket.project_root).TrimEnd('\\', '/'), ProjectRoot,
                    Path.DirectorySeparatorChar == '\\' ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal) ||
                string.IsNullOrEmpty(ticket.source_sha256) || ticket.source_sha256.Length != 64 ||
                string.IsNullOrEmpty(ticket.receipt_path) || string.IsNullOrEmpty(ticket.result_path) ||
                !Path.IsPathRooted(ticket.receipt_path) || !Path.IsPathRooted(ticket.result_path) ||
                ticket.receipt_path.StartsWith(Application.dataPath, StringComparison.OrdinalIgnoreCase) ||
                ticket.result_path.StartsWith(Application.dataPath, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Rock ticket scope or revision invalid");
            return ticket;
        }

        private static void RequireApproval(Ticket ticket, string approvalRef, string kind)
        {
            if (string.IsNullOrEmpty(approvalRef) || !System.Text.RegularExpressions.Regex.IsMatch(
                    approvalRef, @"^[A-Za-z0-9._-]+$") ||
                string.IsNullOrEmpty(ticket.state_root) || !Path.IsPathRooted(ticket.state_root) ||
                string.IsNullOrEmpty(ticket.plan_id))
                throw new InvalidOperationException("Rock Editor requires trusted Approval record");
            string file = Path.Combine(ticket.state_root, "approvals", "decisions", approvalRef + ".json");
            if (!File.Exists(file)) throw new InvalidOperationException("Rock Approval record unavailable");
            var record = JsonUtility.FromJson<ApprovalRecord>(File.ReadAllText(file));
            var decision = record == null ? null : record.decision;
            if (record == null || record.schema_version != "1.1" || decision == null ||
                decision.approval_decision_id != approvalRef ||
                decision.operation != "rock_import_" + kind ||
                decision.plan_id != ticket.plan_id || decision.project_root != ProjectRoot ||
                decision.status != "active" || decision.human_review != "approved" ||
                decision.revocation_epoch != record.current_revocation_epoch ||
                !DateTime.TryParse(decision.expires_at, null,
                    System.Globalization.DateTimeStyles.RoundtripKind, out var expiry) ||
                expiry.ToUniversalTime() <= DateTime.UtcNow)
                throw new InvalidOperationException("Rock Editor Approval expired or revoked");
        }

        private static string[] ExpectedFiles()
        {
            return new[]
            {
                Root + ".meta", ModelPath, ModelPath + ".meta",
                MaterialPath, MaterialPath + ".meta", PrefabPath, PrefabPath + ".meta",
                ScenePath, ScenePath + ".meta"
            };
        }

        private static Receipt Capture(Ticket ticket)
        {
            var files = new List<OwnedFile>();
            foreach (var relative in ExpectedFiles())
            {
                var full = Absolute(relative);
                if (!File.Exists(full))
                    throw new InvalidOperationException("Generated Rock output is missing: " + relative);
                var asset = relative.EndsWith(".meta", StringComparison.Ordinal) ?
                    relative.Substring(0, relative.Length - 5) : relative;
                files.Add(new OwnedFile { path = relative, sha256 = Hash(full),
                    guid = AssetDatabase.AssetPathToGUID(asset) });
            }
            return new Receipt { project_root = ProjectRoot, source_sha256 = ticket.source_sha256,
                unity_version = Application.unityVersion, artifact_guid = AssetDatabase.AssetPathToGUID(ModelPath),
                files = files.ToArray(), status = "applied" };
        }

        public static void ApplyApproved()
        {
            var ticket = ReadTicket("apply");
            RequireApproval(ticket, ticket.mutation_approval_ref, "mutation");
            RequireApproval(ticket, ticket.save_approval_ref, "save");
            // Unity can automatically create Rock.fbx.meta and the parent directory
            // .meta when it scans staged Assets BEFORE -executeMethod starts.
            // The host verified both absent under its Project Lease before staging.
            // Here allow only those two auto-import side effects; exact hashes/GUIDs
            // are fixed in the post-Editor ownership Receipt.
            if (File.Exists(Absolute(MaterialPath)) ||
                File.Exists(Absolute(PrefabPath)) || File.Exists(Absolute(ScenePath)) ||
                !File.Exists(Absolute(ModelPath)) || Hash(Absolute(ModelPath)) != ticket.source_sha256)
                throw new InvalidOperationException("Rock preimage or staged FBX hash changed");
            var existing = Directory.GetFiles(Absolute(Root), "*", SearchOption.AllDirectories)
                .Select(Path.GetFullPath).ToArray();
            var allowedPreimages = new[] { Absolute(ModelPath), Absolute(ModelPath + ".meta") }
                .Select(Path.GetFullPath).ToArray();
            if (!existing.Contains(Path.GetFullPath(Absolute(ModelPath))) ||
                existing.Any(path => !allowedPreimages.Contains(path)))
                throw new InvalidOperationException("Unowned file in Rock import scope");

            RequireApproval(ticket, ticket.mutation_approval_ref, "mutation");
            RequireApproval(ticket, ticket.save_approval_ref, "save");
            AssetDatabase.ImportAsset(ModelPath, ImportAssetOptions.ForceSynchronousImport);
            var importer = AssetImporter.GetAtPath(ModelPath) as ModelImporter;
            if (importer == null) throw new InvalidOperationException("FBX importer unavailable");
            importer.globalScale = 1;
            importer.materialImportMode = ModelImporterMaterialImportMode.None;
            importer.SaveAndReimport();
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(ModelPath);
            if (model == null || model.GetComponentsInChildren<MeshFilter>(true).Length == 0)
                throw new InvalidOperationException("Imported rock mesh unavailable");
            var shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null || !shader.isSupported)
                throw new InvalidOperationException("URP Lit shader not available");
            var material = new Material(shader);
            material.SetColor("_BaseColor", new Color(0.32f, 0.29f, 0.25f));
            AssetDatabase.CreateAsset(material, MaterialPath);
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var go = (GameObject)PrefabUtility.InstantiatePrefab(model);
            foreach (var renderer in go.GetComponentsInChildren<Renderer>(true))
                renderer.sharedMaterial = material;
            var prefab = PrefabUtility.SaveAsPrefabAsset(go, PrefabPath);
            if (prefab == null) throw new InvalidOperationException("Rock prefab creation failed");
            Object.DestroyImmediate(go);
            var placed = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            placed.name = "UnityAgentRock";
            var importedMesh = placed.GetComponentsInChildren<MeshFilter>(true);
            if (importedMesh.Length == 0 || importedMesh.Any(m => m.sharedMesh == null) ||
                placed.GetComponentsInChildren<Renderer>(true).Any(r =>
                    r.sharedMaterials.Any(m => m == null || m.shader == null || !m.shader.isSupported)) ||
                placed.GetComponentsInChildren<Transform>(true).Any(t =>
                    GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(t.gameObject) != 0))
                throw new InvalidOperationException("Rock prefab references/mesh/material failed QA");
            string guidBefore = AssetDatabase.AssetPathToGUID(ModelPath);
            AssetDatabase.ImportAsset(ModelPath, ImportAssetOptions.ForceSynchronousImport);
            if (guidBefore != AssetDatabase.AssetPathToGUID(ModelPath))
                throw new InvalidOperationException("Rock FBX GUID changed on re-import");
            if (!EditorSceneManager.SaveScene(scene, ScenePath))
                throw new InvalidOperationException("Rock Scene save failed");
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            var receipt = Capture(ticket);
            if (string.IsNullOrEmpty(receipt.artifact_guid))
                throw new InvalidOperationException("Model GUID missing");
            File.WriteAllText(ticket.receipt_path, JsonUtility.ToJson(receipt, true));
            File.WriteAllText(ticket.result_path, "{\"status\":\"applied\"}");
        }

        public static void RollbackApproved()
        {
            var ticket = ReadTicket("rollback");
            RequireApproval(ticket, ticket.rollback_approval_ref, "rollback");
            if (!File.Exists(ticket.receipt_path) || Hash(ticket.receipt_path) != ticket.receipt_sha256)
                throw new InvalidOperationException("Rock import Receipt changed; manual reconciliation required");
            var receipt = JsonUtility.FromJson<Receipt>(File.ReadAllText(ticket.receipt_path));
            if (receipt == null || receipt.status != "applied" ||
                receipt.project_root != ProjectRoot || receipt.source_sha256 != ticket.source_sha256 ||
                receipt.files == null || receipt.files.Length != ExpectedFiles().Length ||
                receipt.files.Select(f => f.path).OrderBy(x => x).SequenceEqual(ExpectedFiles().OrderBy(x => x)) == false)
                throw new InvalidOperationException("Rock import ownership Receipt invalid");
            foreach (var file in receipt.files)
            {
                if (!File.Exists(Absolute(file.path)) || Hash(Absolute(file.path)) != file.sha256)
                    throw new InvalidOperationException("Rock asset modified after import: " + file.path);
                var asset = file.path.EndsWith(".meta") ? file.path.Substring(0, file.path.Length - 5) : file.path;
                if (AssetDatabase.AssetPathToGUID(asset) != file.guid)
                    throw new InvalidOperationException("Rock GUID changed: " + asset);
            }
            var current = Directory.GetFiles(Absolute(Root), "*", SearchOption.AllDirectories)
                .Select(f => f.Substring(ProjectRoot.Length + 1).Replace('\\', '/')).ToArray();
            var allowed = ExpectedFiles().Where(p => p.StartsWith(Root + "/", StringComparison.Ordinal)).OrderBy(x => x);
            if (!current.OrderBy(x => x).SequenceEqual(allowed))
                throw new InvalidOperationException("Unowned file in Rock directory; refusing rollback");
            RequireApproval(ticket, ticket.rollback_approval_ref, "rollback");
            if (!AssetDatabase.DeleteAsset(Root) || Directory.Exists(Absolute(Root)) ||
                File.Exists(Absolute(Root + ".meta")))
                throw new InvalidOperationException("Editor rollback did not remove owned Rock assets");
            File.WriteAllText(ticket.result_path, "{\"status\":\"rolled_back\"}");
        }
    }
}
